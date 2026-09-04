"""
toolkit.py -- a small procedural watercolour painting toolkit
(ROI-scoped, record-then-execute, 4-core parallel compositing).

Everything is float32 RGB in [0,1].  The Canvas holds the accumulated image
as three planar float32 channels.  Every primitive builds its alpha layer
inside a padded bounding box (ROI) instead of a full-canvas buffer, and
blurs / granulation / edge darkening / compositing all run on that ROI only.
Compositing is a fused two-op OpenCV blend on the target sub-view:
    glaze:  plane += plane * (a * s * (color-1))  ==  plane*(1-a') + plane*color*a'
    over:   plane += (color - plane) * (a * s)    ==  plane*(1-a') + color*a'

Record / execute split
----------------------
A primitive call does the *geometry* work in the calling process (polygon
deformation, path resampling and jitter, spray dot sampling, ROI bounding
boxes, noise-crop offset draws -- i.e. everything that consumes a random
stream, in the original order) and appends a small raster/composite *op*
(kind, bbox, geometry arrays, texture params, tint) to `Canvas.ops`.  Nothing
touches pixels until the ops are flushed (`Canvas.to_uint8` / `flush`).

Because every op is either a multiplicative glaze or an alpha-over, a
consecutive run of ops is an *affine* per-pixel map  canvas -> canvas*M + B.
While recording, `_StreamExec` cuts the op sequence into contiguous chunks of
~equal estimated cost and streams them to a pool of 3 spawned worker
processes; each worker executes its chunk onto one of its two (M, B)
accumulator maps held in shared memory, and this process applies the finished
maps to the canvas strictly in op order (freeing the slot) while it keeps
recording.  At flush time the still-queued suffix chunks plus the final
partial chunk are executed here into a local map (a fair share of the
remaining backlog) and applied last, so recording, worker execution and
merging all overlap.  The maps commute the work but not the arithmetic order
that matters, so the result equals the sequential render up to float32
rounding.  The pool, its map buffers and each process's noise bank are
process-lifetime state (created lazily on the first render) -- there is no
per-scene cache anywhere: chunk cuts are recomputed each render from a generic
per-op cost estimate (ROI area / segment / dot counts), and workers only ever
see the op parameters they are handed.  Any worker or pipe failure falls
back to executing the not-yet-applied ops sequentially in this process.

Random streams
--------------
* `Canvas.rng` (seeded from the scene seed) drives GEOMETRY only: polygon
  deformation, ellipse jitter, wash-boundary wobble, spray dot positions and
  whatever the scene itself draws (tower sizes, tuft positions, ...).
* Granulation / pigment grain / paper texture come from a SCENE-INDEPENDENT
  noise bank: a few large value-noise and gaussian-grain textures generated
  once per (canvas size, primitive parameters) from a FIXED internal seed,
  kept in a module-level dict, and sliced at random offsets so every layer
  gets a different patch of the same *style* of noise.  The bank is keyed
  only on generic parameters (size, base cells, octaves, grain sigma) --
  nothing about the scene, its seed or its draw order -- so it is equally
  valid for any scene.  Crop offsets and stroke-path jitter values come from
  private generators drawn during recording, so noise never perturbs layout
  and workers reproduce the recorded crops exactly.

Watercolour "glazes" are composited multiplicatively (pigment darkens the
paper); opaque marks use ordinary alpha-over.
"""

import math
import os
import time

import numpy as np
import cv2

# ROI-sized OpenCV ops gain nothing from its internal thread pool (measured
# slower with 4 threads); the parallelism comes from the worker processes.
try:
    cv2.setNumThreads(1)
except Exception:
    pass


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def hex_rgb(h):
    """'#a3c2ff' -> np.float32 array (r,g,b) in [0,1]."""
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def clamp01(a):
    return np.clip(a, 0.0, 1.0)


def clamp01_(a):
    """In-place clamp for temporaries we own."""
    if a.size:
        np.clip(a, 0.0, 1.0, out=a)
    return a


def soft_blur(layer, sigma):
    """Gaussian blur; large sigmas run on a downsampled copy and are bilinearly
    upsampled back (visually identical for sigma >> 1, up to ~20x cheaper)."""
    if sigma <= 0 or layer.size == 0:
        return layer
    h, w = layer.shape[:2]
    if sigma >= 5.0 and h >= 16 and w >= 16:
        k = 4 if sigma >= 12.0 else 2
        small = cv2.resize(layer, (max(1, w // k), max(1, h // k)),
                           interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), sigma / k)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(layer, (0, 0), sigma)


# --------------------------------------------------------------------------
# scene-independent noise bank
# --------------------------------------------------------------------------

_BANK_SEED = 977123    # fixed internal seed: the bank never depends on the scene
_GRAIN_PAD = 384      # extra rows/cols of grain texture -> random crop offsets
_FRACTAL = {}         # (cw, ch, base, octaves, persistence) -> (2ch, 2cw) field
_GRAIN = {}           # (cw, ch, sigma) -> (ch+PAD, cw+PAD) grain field


def _fractal_field(cw, ch, base, octaves, persistence):
    """Extended fractal value-noise texture for a cw x ch canvas.

    Same construction as the original per-call field (sum of bicubic-resized
    random grids, feature scale `cw/base` pixels, amplitude falling off by
    `persistence` per octave, normalised by the amplitude sum) but built once
    over a 2x-canvas extent from the fixed bank seed, so per-call crops at
    random offsets are decorrelated samples of the same style of mottling.
    """
    key = (cw, ch, float(base), int(octaves), float(persistence))
    f = _FRACTAL.get(key)
    if f is not None:
        return f
    ew, eh = 2 * cw, 2 * ch
    rng = np.random.default_rng([_BANK_SEED, ew, eh, int(round(base * 1000)),
                                 int(octaves), int(round(persistence * 1000))])
    out = np.zeros((eh, ew), dtype=np.float32)
    amp, total = 1.0, 0.0
    cells = base * (ew / float(cw))          # keep feature scale = cw/base px
    for _ in range(octaves):
        c = max(1, int(round(cells)))
        grid = rng.random((c + 2, c + 2)).astype(np.float32) * 2.0 - 1.0
        out += cv2.resize(grid, (ew, eh), interpolation=cv2.INTER_CUBIC) * amp
        total += amp
        amp *= persistence
        cells *= 2
    out /= total
    _FRACTAL[key] = out
    return out


def _grain_field(cw, ch, sigma):
    """Padded gaussian pigment-grain texture (std-normalised) for a cw x ch
    canvas: same recipe as the original full-frame grain (white noise, gaussian
    blur `sigma`, / std), generated once from the fixed bank seed."""
    key = (cw, ch, float(sigma))
    g = _GRAIN.get(key)
    if g is not None:
        return g
    rng = np.random.default_rng([_BANK_SEED, cw, ch, int(round(sigma * 1000)), 7])
    g = rng.standard_normal((ch + _GRAIN_PAD, cw + _GRAIN_PAD)).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), sigma)
    g /= (float(np.std(g)) + 1e-6)
    _GRAIN[key] = g
    return g


class Noise:
    """Per-canvas view onto the scene-independent noise bank.

    During recording only crop *offsets* are drawn (`frac_off`, `grain_off`)
    -- the crops themselves are sliced by whichever process executes the op.
    Offsets and the 1-D path jitter come from private generators derived
    from the canvas seed but separate from the geometry stream.
    """

    def __init__(self, cw, ch, seed):
        self.cw, self.ch = cw, ch
        self._off = np.random.default_rng([int(seed), 0xA11CE])   # crop offsets
        self._jit = np.random.default_rng([int(seed), 0x71773])   # path jitter

    def frac_off(self, w, h):
        """Random top-left offset for an (h, w) crop of the fractal field."""
        fh, fw = 2 * self.ch, 2 * self.cw
        oy = int(self._off.integers(0, fh - h + 1))
        ox = int(self._off.integers(0, fw - w + 1))
        return (oy, ox)

    def grain_off(self, w, h):
        """Random top-left offset for an (h, w) crop of a grain field."""
        gh, gw = self.ch + _GRAIN_PAD, self.cw + _GRAIN_PAD
        oy = int(self._off.integers(0, gh - h + 1))
        ox = int(self._off.integers(0, gw - w + 1))
        return (oy, ox)

    def grain1d(self, n, sigma):
        """Smooth 1-D gaussian jitter for stroke paths (private stream)."""
        g = self._jit.standard_normal((1, n)).astype(np.float32)
        g = cv2.GaussianBlur(g, (0, 0), sigma)
        g = g / (float(np.std(g)) + 1e-6)
        return g.reshape(-1)

    def grain1d_batch(self, lengths, sigma):
        """Smooth 1-D jitter for several paths at once: one contiguous draw
        from the private stream (same values as consecutive per-path draws)
        blurred row-wise -- paths of equal length share one GaussianBlur.
        Returns a list of 1-D float32 arrays in path order."""
        lengths = [int(n) for n in lengths]
        total = int(sum(lengths))
        out = [None] * len(lengths)
        if total == 0:
            return out
        raw = self._jit.standard_normal((1, total)).astype(np.float32).ravel()
        pos = 0
        groups = {}
        for i, n in enumerate(lengths):
            groups.setdefault(n, []).append((i, pos))
            pos += n
        for n, items in groups.items():
            mat = np.stack([raw[p:p + n] for _, p in items], axis=0)
            # sigmaY -> 1-tap column kernel: rows are blurred independently,
            # exactly like a (1, n) input
            mat = cv2.GaussianBlur(mat, (0, 0), sigma, sigmaY=1e-6)
            std = np.std(mat, axis=1)
            for r, (i, _) in enumerate(items):
                out[i] = mat[r] / (float(std[r]) + 1e-6)
        return out


def prime_noise_bank(cw, ch, params=None):
    """Optionally pre-build bank textures for a canvas size (warmup helper).

    `params` is a list of ('fractal', base, octaves) / ('grain', sigma) tuples;
    with None the textures are simply built lazily on first use."""
    for p in (params or ()):
        if p[0] == "fractal":
            _fractal_field(cw, ch, p[1], p[2], 0.55)
        else:
            _grain_field(cw, ch, p[1])


# --------------------------------------------------------------------------
# pure raster helpers (used by whichever process executes an op)
# --------------------------------------------------------------------------

def _bbox_of(pts, pad, cw, ch):
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    mn = pts.min(axis=0)
    mx = pts.max(axis=0)
    x0 = max(0, int(math.floor(float(mn[0]) - pad)))
    y0 = max(0, int(math.floor(float(mn[1]) - pad)))
    x1 = min(cw, int(math.ceil(float(mx[0]) + pad)) + 1)
    y1 = min(ch, int(math.ceil(float(mx[1]) + pad)) + 1)
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def _poly_layer(pts, softness, pad, cw, ch):
    """Rasterise a polygon into a soft-edged alpha layer inside its bbox.
    Returns (layer, x0, y0); layer may be empty (fully off-canvas).

    Very soft polygons (softness >= 5) are rasterised (subpixel-accurate)
    and blurred at 1/2 or 1/4 resolution and bilinearly upsampled -- the
    soft edge is band-limited so this is visually identical and skips a
    full-resolution fill + big-kernel blur."""
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    x0, y0, w, h = _bbox_of(pts, pad, cw, ch)
    if w <= 0 or h <= 0:
        return np.zeros((h, w), dtype=np.float32), x0, y0
    if softness >= 5.0 and w >= 32 and h >= 32:
        k = 4 if softness >= 12.0 else 2
        sw, sh = (w + k - 1) // k, (h + k - 1) // k
        small = np.zeros((sh, sw), dtype=np.float32)
        off = (k - 1.0) / (2.0 * k)
        fp = np.round((pts - np.array([x0, y0], np.float32)) * (256.0 / k)
                      - off * 256.0).astype(np.int32)
        cv2.fillPoly(small, [fp], 1.0, lineType=cv2.LINE_AA, shift=8)
        small = cv2.GaussianBlur(small, (0, 0), softness / k)
        M = np.array([[1.0 / k, 0.0, -off], [0.0, 1.0 / k, -off]], np.float64)
        layer = cv2.warpAffine(small, M, (w, h),
                               flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                               borderMode=cv2.BORDER_REPLICATE)
        return layer, x0, y0
    layer = np.zeros((h, w), dtype=np.float32)
    ip = np.round(pts).astype(np.int32)
    ip[:, 0] -= x0
    ip[:, 1] -= y0
    cv2.fillPoly(layer, [ip], 1.0, lineType=cv2.LINE_AA)
    if softness > 0:
        layer = soft_blur(layer, softness)
    return layer, x0, y0


def _granulate(alpha, gran, cw, ch):
    """Mottle an alpha layer the way pigment pools and granulates:
    alpha * (1 + amount*fractal + grain*grain_noise), clamped to [0,1].
    `gran` = (amount, base, octaves, grain, frac_off, grain_off, sigma)."""
    h, w = alpha.shape[:2]
    if h == 0 or w == 0:
        return alpha
    amount, base, octaves, grain, foff, goff, gsig = gran
    f = _fractal_field(cw, ch, base, octaves, 0.55)
    n = f[foff[0]:foff[0] + h, foff[1]:foff[1] + w]
    gf = _grain_field(cw, ch, gsig)
    g = gf[goff[0]:goff[0] + h, goff[1]:goff[1] + w]
    t = cv2.addWeighted(n, float(amount), g, float(grain), 1.0)
    cv2.multiply(t, np.ascontiguousarray(alpha), dst=t)
    return clamp01_(t)


def _edge_darken(alpha, strength=0.6, radius=6):
    """Watercolour edge darkening on an alpha field (any shape)."""
    if alpha.size == 0:
        return alpha
    blur = soft_blur(alpha, radius)
    rim = np.subtract(alpha, blur, out=blur)   # reuse the blur buffer
    clamp01_(rim)
    rim *= strength * 3.0
    rim += alpha
    return clamp01_(rim)


def _grain_texture(layer, texture, goff, cw, ch):
    """Multiplicative dry-brush texture on a stroke layer (grain sigma 0.9)."""
    h, w = layer.shape
    gf = _grain_field(cw, ch, 0.9)
    g = gf[goff[0]:goff[0] + h, goff[1]:goff[1] + w]
    f = np.multiply(g, np.float32(-0.5 * texture), dtype=np.float32)
    f += np.float32(1.0 - 0.5 * texture)
    layer *= f
    return layer


# --------------------------------------------------------------------------
# op cost model (chunk balancing only -- generic, keyed on op parameters)
# --------------------------------------------------------------------------

# per-pixel costs in ns for the ROI area of each op kind (rough, machine-
# calibrated); dots/segments add a per-item term.  These only steer the
# chunk cut points; correctness never depends on them.
_COST_NS = {          # ns per ROI pixel (single-thread, affine target)
    "poly": 19.0, "wash": 17.0, "strokes": 12.0, "dabs": 17.0,
    "scatter": 8.5, "spray": 14.5, "outline": 7.0, "paper": 5.0,
}
_COST_FIXED_NS = {    # ns of fixed per-op overhead (many small cv2/np calls)
    "poly": 180e3, "wash": 300e3, "strokes": 220e3, "dabs": 85e3,
    "scatter": 200e3, "spray": 250e3, "outline": 125e3, "paper": 0.0,
}
_COST_ITEM_NS = {"strokes": 700.0, "spray": 5.0, "scatter": 1000.0, "dabs": 2300.0}


def _op_cost(op):
    kind = op[0]
    w, h = op[3], op[4]
    c = _COST_FIXED_NS.get(kind, 200e3) + w * h * _COST_NS.get(kind, 12.0)
    it = _COST_ITEM_NS.get(kind)
    if it is not None:
        c += len(op[5]) * it
    return c


# --------------------------------------------------------------------------
# op execution targets
# --------------------------------------------------------------------------

class PixelTarget:
    """Composites ops straight onto the canvas colour planes."""

    def __init__(self, planes):
        self.planes = planes

    def tint(self, a, x0, y0, color, mode, s, clamped=True):
        h, w = a.shape[:2]
        if h == 0 or w == 0 or s == 0.0:
            return
        a2 = a if clamped else clamp01(a)
        t = np.empty((h, w), dtype=np.float32)
        if mode == "glaze":
            for c in range(3):
                p = self.planes[c][y0:y0 + h, x0:x0 + w]
                cv2.multiply(p, a2, dst=t, scale=float(s) * (float(color[c]) - 1.0))
                cv2.add(p, t, dst=p)
        else:
            for c in range(3):
                p = self.planes[c][y0:y0 + h, x0:x0 + w]
                cv2.subtract(float(color[c]), p, dst=t)
                cv2.multiply(t, a2, dst=t, scale=float(s))
                cv2.add(p, t, dst=p)

    def glaze_field(self, a, x0, y0, grad, s):
        h, w = a.shape[:2]
        if h == 0 or w == 0 or s == 0.0:
            return
        t = np.empty((h, w), dtype=np.float32)
        s = np.float32(s)
        for c in range(3):
            fcol = (grad[:, :, c] - np.float32(1.0)) * s     # (h,1)
            np.multiply(a, fcol, out=t)                        # a'*(c-1)
            p = self.planes[c][y0:y0 + h, x0:x0 + w]
            cv2.multiply(p, t, dst=t)
            cv2.add(p, t, dst=p)

    def paper(self, tex):
        for p in self.planes:
            cv2.multiply(p, tex, dst=p)
            np.clip(p, 0.0, 1.0, out=p)


class AffineTarget:
    """Composites ops onto an affine map canvas -> canvas*M + B (three planes
    each), which can later be applied to any canvas that had the earlier ops.

    B stays untouched (implicitly zero over `union`) until the first alpha-over
    op: chunks of purely multiplicative glazes cost only the M passes and their
    merge skips the additive term (`b_dirty` tells the merger)."""

    def __init__(self, M, B, union=None):
        self.M, self.B = M, B          # each: 3 planes (h, w)
        self.union = union             # (x0, y0, x1, y1) region B may cover
        self.b_dirty = False

    def _touch_b(self):
        if not self.b_dirty:
            if self.union is not None:
                x0, y0, x1, y1 = self.union
                self.B[:, y0:y1, x0:x1] = 0.0
            self.b_dirty = True

    def tint(self, a, x0, y0, color, mode, s, clamped=True):
        h, w = a.shape[:2]
        if h == 0 or w == 0 or s == 0.0:
            return
        a2 = a if clamped else clamp01(a)
        t = np.empty((h, w), dtype=np.float32)
        if mode == "glaze":
            # M' = M*(1+f), B' = B*(1+f),  f = a'*(c-1)   (B part only if B != 0)
            for c in range(3):
                sc = float(s) * (float(color[c]) - 1.0)
                pm = self.M[c][y0:y0 + h, x0:x0 + w]
                cv2.multiply(pm, a2, dst=t, scale=sc)
                cv2.add(pm, t, dst=pm)
                if self.b_dirty:
                    pb = self.B[c][y0:y0 + h, x0:x0 + w]
                    cv2.multiply(pb, a2, dst=t, scale=sc)
                    cv2.add(pb, t, dst=pb)
        else:
            # M' = M*(1-a'),  B' = B + (c-B)*a'
            self._touch_b()
            for c in range(3):
                pm = self.M[c][y0:y0 + h, x0:x0 + w]
                cv2.multiply(pm, a2, dst=t, scale=-float(s))
                cv2.add(pm, t, dst=pm)
                pb = self.B[c][y0:y0 + h, x0:x0 + w]
                cv2.subtract(float(color[c]), pb, dst=t)
                cv2.multiply(t, a2, dst=t, scale=float(s))
                cv2.add(pb, t, dst=pb)

    def glaze_field(self, a, x0, y0, grad, s):
        h, w = a.shape[:2]
        if h == 0 or w == 0 or s == 0.0:
            return
        t = np.empty((h, w), dtype=np.float32)
        u = np.empty((h, w), dtype=np.float32)
        s = np.float32(s)
        for c in range(3):
            fcol = (grad[:, :, c] - np.float32(1.0)) * s
            np.multiply(a, fcol, out=t)                        # f = a'*(c-1)
            pm = self.M[c][y0:y0 + h, x0:x0 + w]
            cv2.multiply(pm, t, dst=u)
            cv2.add(pm, u, dst=pm)
            if self.b_dirty:
                pb = self.B[c][y0:y0 + h, x0:x0 + w]
                cv2.multiply(pb, t, dst=u)
                cv2.add(pb, u, dst=pb)

    def paper(self, tex):
        for c in range(3):
            cv2.multiply(self.M[c], tex, dst=self.M[c])
            if self.b_dirty:
                cv2.multiply(self.B[c], tex, dst=self.B[c])


def _exec_op(op, target, cw, ch):
    """Execute one recorded raster/composite op onto `target`."""
    kind = op[0]
    x0, y0, w, h = op[1], op[2], op[3], op[4]
    if kind == "poly":
        _, _, _, _, _, poly, softness, pad, gran, edge, tint = op
        a, ax0, ay0 = _poly_layer(poly, softness, pad, cw, ch)
        if a.size == 0:
            return
        if gran is not None:
            a = _granulate(a, gran, cw, ch)
        else:
            a = clamp01_(a)
        if edge is not None:
            a = _edge_darken(a, strength=edge[0], radius=edge[1])
        target.tint(a, ax0, ay0, tint[0], tint[1], tint[2], clamped=True)
    elif kind == "wash":
        _, _, _, _, _, poly, softness, pad, ramp, gran, grad, s = op
        a, ax0, ay0 = _poly_layer(poly, softness, pad, cw, ch)
        if a.size == 0:
            return
        a = a * ramp
        a = _granulate(a, gran, cw, ch)
        target.glaze_field(a, ax0, ay0, grad, s)
    elif kind == "strokes":
        _, _, _, _, _, pairs, th, softness, texture, goff, tint = op
        layer = np.zeros((h, w), dtype=np.float32)
        if w > 0 and h > 0 and len(pairs):
            for t in np.unique(th):
                cv2.polylines(layer, list(pairs[th == t]), False, 1.0,
                              thickness=int(t), lineType=cv2.LINE_AA)
            if softness > 0:
                layer = soft_blur(layer, softness)
            if texture > 0:
                layer = _grain_texture(layer, texture, goff, cw, ch)
        target.tint(layer, x0, y0, tint[0], tint[1], tint[2], clamped=True)
    elif kind == "dabs":
        _, _, _, _, _, rects, softness, gran, tint = op
        layer = np.zeros((h, w), dtype=np.float32)
        if w > 0 and h > 0:
            for (rx0, ry0, rx1, ry1) in rects:
                cv2.rectangle(layer, (rx0, ry0), (rx1, ry1), 1.0, -1)
            if softness > 0:
                layer = soft_blur(layer, softness)
            if gran is not None:
                layer = _granulate(layer, gran, cw, ch)
        target.tint(layer, x0, y0, tint[0], tint[1], tint[2], clamped=True)
    elif kind == "scatter":
        _, _, _, _, _, dots, softness, tint = op
        layer = np.zeros((h, w), dtype=np.float32)
        if w > 0 and h > 0:
            for (cx, cy, r) in dots:
                cv2.circle(layer, (cx, cy), r, 1.0, -1, lineType=cv2.LINE_AA)
            if softness > 0:
                layer = soft_blur(layer, softness)
        target.tint(layer, x0, y0, tint[0], tint[1], tint[2], clamped=True)
    elif kind == "spray":
        _, _, _, _, _, xs, ys, rad, softness, tint = op
        layer = np.zeros((h, w), dtype=np.float32)
        if w > 0 and h > 0 and len(xs):
            if softness >= 3.0:
                # dots melt under a wide blur: stamp the centres and dilate
                # them into hard disks (the LINE_AA fringe is invisible)
                layer[ys, xs] = 1.0
                se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                               (2 * rad + 1, 2 * rad + 1))
                layer = cv2.dilate(layer, se)
            else:
                pts = np.unique(np.stack([xs, ys], axis=1), axis=0)
                for xi, yi in pts.tolist():
                    cv2.circle(layer, (xi, yi), rad, 1.0, -1, lineType=cv2.LINE_AA)
            if softness > 0:
                layer = soft_blur(layer, softness)
        target.tint(layer, x0, y0, tint[0], tint[1], tint[2], clamped=True)
    elif kind == "outline":
        _, _, _, _, _, ip, closed, width, softness, tint = op
        layer = np.zeros((h, w), dtype=np.float32)
        if w > 0 and h > 0:
            cv2.polylines(layer, [ip], closed, 1.0, thickness=width,
                          lineType=cv2.LINE_AA)
            if softness > 0:
                layer = soft_blur(layer, softness)
        target.tint(layer, x0, y0, tint[0], "over", tint[2], clamped=True)
    elif kind == "paper":
        _, _, _, _, _, goff, gsig, foff, fbase, foct, strength = op
        gf = _grain_field(cw, ch, gsig)
        fine = gf[goff[0]:goff[0] + h, goff[1]:goff[1] + w]
        ff = _fractal_field(cw, ch, fbase, foct, 0.55)
        coarse = ff[foff[0]:foff[0] + h, foff[1]:foff[1] + w]
        tex = cv2.addWeighted(fine, -0.4 * strength, coarse, -0.9 * strength, 1.0)
        target.paper(tex)


# --------------------------------------------------------------------------
# parallel executor: worker processes owning shared (M,B) map buffers
# --------------------------------------------------------------------------

_SLOTS = 2   # (M,B) map buffers per worker: run a chunk while the previous
             # one's map still waits to be merged in op order


def _grow_pipe(conn):
    """Best-effort: enlarge a one-way Connection's pipe buffer (Linux
    F_SETPIPE_SZ, up to 1 MiB) so sending a whole pickled chunk (~0.1-0.3 MB)
    never blocks the recording process on a busy worker."""
    try:
        import fcntl
        fcntl.fcntl(conn.fileno(), getattr(fcntl, "F_SETPIPE_SZ", 1031), 1 << 20)
    except Exception:
        pass


def _worker_main(cmd, res, shname, cw, ch):
    """Worker loop: execute op chunks onto one of this worker's (M,B) maps."""
    from multiprocessing import shared_memory
    try:
        cv2.setNumThreads(1)
    except Exception:
        pass
    shm = shared_memory.SharedMemory(name=shname)
    maps = np.ndarray((_SLOTS, 2, 3, ch, cw), dtype=np.float32, buffer=shm.buf)
    while True:
        try:
            msg = cmd.recv()
        except EOFError:
            break
        if msg is None:
            break
        if msg[0] == "prime":
            # pre-build noise-bank fields (generic keys) so no timed chunk
            # ever pays a first-use texture build
            for key in msg[1]:
                if key[0] == "f":
                    _fractal_field(cw, ch, key[1], key[2], key[3])
                else:
                    _grain_field(cw, ch, key[1])
            continue
        _, ops, (ux0, uy0, ux1, uy1), slot = msg
        t0 = time.perf_counter()
        # reset the union bbox of this chunk to the identity map (B lazily)
        maps[slot, 0, :, uy0:uy1, ux0:ux1] = 1.0
        tgt = AffineTarget(maps[slot][0], maps[slot][1], (ux0, uy0, ux1, uy1))
        for op in ops:
            _exec_op(op, tgt, cw, ch)
        res.send((slot, (time.perf_counter() - t0) * 1000.0, tgt.b_dirty))
    del maps
    shm.close()


class _WorkerPool:
    """A fixed set of spawned worker processes, each owning _SLOTS shared
    (M,B) affine-map buffers.  Process-lifetime; independent of any scene."""

    def __init__(self, n, cw, ch):
        import multiprocessing as mp
        from multiprocessing import shared_memory
        self.cw, self.ch, self.n = cw, ch, n
        ctx = mp.get_context("spawn")
        self.shms = []
        self.procs = []
        self.cmds = []      # main -> worker  (real pipes, buffer grown to 1 MiB)
        self.ress = []      # worker -> main
        self.maps = []
        nbytes = _SLOTS * 2 * 3 * cw * ch * 4
        for i in range(n):
            sh = shared_memory.SharedMemory(create=True, size=nbytes)
            self.shms.append(sh)
            self.maps.append(np.ndarray((_SLOTS, 2, 3, ch, cw), dtype=np.float32,
                                        buffer=sh.buf))
            cmd_r, cmd_w = ctx.Pipe(duplex=False)      # os.pipe(): resizable
            res_r, res_w = ctx.Pipe(duplex=False)
            _grow_pipe(cmd_w)
            p = ctx.Process(target=_worker_main,
                            args=(cmd_r, res_w, sh.name, cw, ch), daemon=True)
            p.start()
            cmd_r.close()
            res_w.close()
            self.procs.append(p)
            self.cmds.append(cmd_w)
            self.ress.append(res_r)
        self.primed = set()          # bank keys already broadcast to workers
        # bank fields this process already holds: workers get them up front
        self.prime([("f", k[2], k[3], k[4]) for k in _FRACTAL] +
                   [("g", k[2]) for k in _GRAIN])

    def prime(self, keys):
        """Broadcast noise-bank keys every worker must have built (each key
        is sent once per pool; workers build them ahead of any chunk)."""
        new = [k for k in keys if k not in self.primed]
        if not new:
            return
        self.primed.update(new)
        for c in self.cmds:
            c.send(("prime", new))

    def submit(self, i, ops, union, slot):
        self.cmds[i].send(("run", ops, union, slot))

    def close(self):
        for c in self.cmds:
            try:
                c.send(None)
            except Exception:
                pass
        for p in self.procs:
            p.join(timeout=2)
        for s in self.shms:
            try:
                s.close()
                s.unlink()
            except Exception:
                pass


_POOL = None
_LOCAL_MAPS = {}                 # (cw, ch) -> (M, B) buffers for main's chunk


def _get_pool(cw, ch):
    global _POOL
    if _POOL is None or _POOL.cw != cw or _POOL.ch != ch:
        if _POOL is not None:
            _POOL.close()
        nw = _num_workers()
        _POOL = _WorkerPool(nw, cw, ch)
        import atexit
        atexit.register(_POOL.close)
    return _POOL


def _local_maps(cw, ch):
    m = _LOCAL_MAPS.get((cw, ch))
    if m is None:
        m = (np.empty((3, ch, cw), np.float32), np.empty((3, ch, cw), np.float32))
        _LOCAL_MAPS[(cw, ch)] = m
    return m


class _StreamExec:
    """Streaming scheduler: cuts the recorded op sequence into contiguous
    chunks of ~T estimated cost while recording, feeds them to the worker
    pool (a worker holds up to _SLOTS unmerged chunk maps), and merges the
    finished (M,B) maps onto the canvas strictly in op order.  The final
    partial chunk is executed by this process (as its own map) so recording,
    execution and merging all overlap."""

    T_NS = 70e6     # target chunk size, in estimated nanoseconds of work

    def __init__(self, canvas, pool):
        self.cv = canvas
        self.pool = pool
        self.nw = pool.n
        self.chunks = []            # dicts, in cut (== op) order
        self.pending = []
        self.pcost = 0.0
        self.queue = []             # queued chunk indices (FIFO)
        self.next_merge = 0
        self.wstate = [[None] * _SLOTS for _ in range(self.nw)]   # slot -> chunk
        self.n_out = 0              # chunks running or done-but-unmerged
        self.stats = []

    # -- recording side --

    def add(self, op):
        self.pending.append(op)
        self.pcost += _op_cost(op)
        if self.pcost >= self.T_NS:
            self.cut()

    def cut(self):
        if not self.pending:
            return
        cw, ch = self.cv.w, self.cv.h
        k = len(self.chunks)
        self.chunks.append({"ops": self.pending, "est": self.pcost,
                            "union": _union_bbox(self.pending, cw, ch),
                            "state": "queued", "worker": None, "slot": None})
        self.queue.append(k)
        self.pending = []
        self.pcost = 0.0
        self.poll(block=False)      # merge anything ready, free slots
        self.dispatch()

    # -- scheduling --

    def dispatch(self):
        while self.queue:
            best = None
            for w in range(self.nw):
                occ = sum(1 for s in self.wstate[w] if s is not None)
                if occ < _SLOTS and (best is None or occ < best[1]):
                    best = (w, occ)
            if best is None:
                return
            w = best[0]
            slot = self.wstate[w].index(None)
            k = self.queue.pop(0)
            chn = self.chunks[k]
            chn["state"] = "run"
            chn["worker"] = w
            chn["slot"] = slot
            self.wstate[w][slot] = k
            self.n_out += 1
            self.pool.submit(w, chn["ops"], chn["union"], slot)

    def poll(self, block=False):
        """Collect finished chunks (optionally waiting for one), then merge
        every chunk that is now next in op order and dispatch queued ones."""
        from multiprocessing.connection import wait as mp_wait
        active = [self.pool.ress[w] for w in range(self.nw)
                  if any(k is not None and self.chunks[k]["state"] == "run"
                         for k in self.wstate[w])]
        if active:
            for conn in mp_wait(active, timeout=None if block else 0):
                w = self.pool.ress.index(conn)
                slot, wms, b_dirty = conn.recv()
                k = self.wstate[w][slot]
                self.chunks[k]["state"] = "done"
                self.chunks[k]["wms"] = wms
                self.chunks[k]["b"] = b_dirty
        self.merge_ready()

    def merge_ready(self):
        planes = self.cv.planes
        while self.next_merge < len(self.chunks) and \
                self.chunks[self.next_merge]["state"] == "done":
            chn = self.chunks[self.next_merge]
            ux0, uy0, ux1, uy1 = chn["union"]
            if ux1 > ux0 and uy1 > uy0:
                M, B = self.pool.maps[chn["worker"]][chn["slot"]]
                for c in range(3):
                    p = planes[c][uy0:uy1, ux0:ux1]
                    cv2.multiply(p, M[c][uy0:uy1, ux0:ux1], dst=p)
                    if chn["b"]:
                        cv2.add(p, B[c][uy0:uy1, ux0:ux1], dst=p)
            chn["state"] = "merged"
            self.wstate[chn["worker"]][chn["slot"]] = None
            self.n_out -= 1
            self.stats.append((self.next_merge, len(chn["ops"]), round(chn["est"] * 1e-6, 1),
                               chn["worker"], round(chn.get("wms", -1), 1)))
            chn["ops"] = None                              # release memory
            self.next_merge += 1
        self.dispatch()

    # -- flush --

    def finish(self):
        cw, ch = self.cv.w, self.cv.h
        tail = self.pending
        tail_est = self.pcost
        self.pending = []
        self.pcost = 0.0
        self.tail_ops = tail        # kept for the sequential fallback
        if not self.chunks:
            # nothing was ever dispatched: draw straight onto the canvas
            tgt = PixelTarget(self.cv.planes)
            for op in tail:
                _exec_op(op, tgt, cw, ch)
            self.stats.append(("tail-pixel", len(tail), round(tail_est * 1e-6, 1)))
            return
        self.poll(block=False)
        # main's own block: the still-queued chunks at the END of the op
        # sequence (up to a fair share of the remaining backlog) plus the
        # tail, executed here into a local (M,B) map while the workers drain
        # the queue -- applied last, since it is last in op order.
        backlog = sum(self.chunks[k]["est"] for k in self.queue)
        running = sum(self.chunks[k]["est"] for w in range(self.nw)
                      for k in self.wstate[w]
                      if k is not None and self.chunks[k]["state"] == "run")
        # main starts its block only now and must also merge every worker map:
        # solve  (B - X)/nw == k*X + m  for main's block estimate X
        B = backlog + 0.5 * running + tail_est
        k_main, m_merge = 1.35, 20e6
        share = max(tail_est, (B - self.nw * m_merge) / (1.0 + self.nw * k_main))
        block = []
        best = tail_est
        while self.queue:
            k = self.queue[-1]
            if block and best + self.chunks[k]["est"] > share:
                break
            self.queue.pop()
            block.insert(0, k)
            best += self.chunks[k]["est"]
        ops = []
        for k in block:
            chn = self.chunks[k]
            ops.extend(chn["ops"])          # kept until applied (fallback)
            chn["state"] = "local"           # merged as part of main's map
        ops.extend(tail)
        t0 = time.perf_counter()
        if ops:
            M, B = _local_maps(cw, ch)
            lux0, luy0, lux1, luy1 = _union_bbox(ops, cw, ch)
            M[:, luy0:luy1, lux0:lux1] = 1.0
            tgt = AffineTarget(M, B, (lux0, luy0, lux1, luy1))
            for i, op in enumerate(ops):
                _exec_op(op, tgt, cw, ch)
                if (i & 7) == 7:                    # keep the workers fed
                    self.poll(block=False)
        lms = (time.perf_counter() - t0) * 1000.0
        # wait for every worker chunk before main's block, merging in order
        first_local = block[0] if block else len(self.chunks)
        while self.next_merge < first_local:
            self.dispatch()
            self.poll(block=True)
        # remaining chunk entries (if any) are all in main's local block
        if ops:
            planes = self.cv.planes
            for c in range(3):
                p = planes[c][luy0:luy1, lux0:lux1]
                cv2.multiply(p, M[c][luy0:luy1, lux0:lux1], dst=p)
                if tgt.b_dirty:
                    cv2.add(p, B[c][luy0:luy1, lux0:lux1], dst=p)
            self.stats.append(("main", len(ops), round(best * 1e-6, 1), -1,
                               round(lms, 1)))
        for k in block:
            self.chunks[k]["ops"] = None
            self.chunks[k]["state"] = "merged"
        self.tail_ops = []
        self.next_merge = len(self.chunks)

    def all_ops(self):
        """Every op recorded but not yet applied to the canvas, in order (for
        the sequential fallback; merged chunks are already on the canvas)."""
        ops = []
        for chn in self.chunks:
            if chn["state"] != "merged" and chn["ops"] is not None:
                ops.extend(chn["ops"])
        return ops + self.pending + list(getattr(self, "tail_ops", []))

    def kill(self):
        global _POOL
        try:
            self.pool.close()
        except Exception:
            pass
        _POOL = None


def _num_workers():
    """Number of *worker* processes (the caller renders one chunk itself).
    CANVAS_WORKERS overrides; 0 => fully sequential in-process rendering."""
    env = os.environ.get("CANVAS_WORKERS")
    if env is not None:
        try:
            return max(0, int(env))
        except ValueError:
            pass
    cores = os.cpu_count() or 1
    return max(0, min(cores, 4) - 1)


# --------------------------------------------------------------------------
# canvas
# --------------------------------------------------------------------------

class Canvas:
    def __init__(self, w, h, seed=1, paper="#f4eee0"):
        self.w, self.h = w, h
        self.rng = np.random.default_rng(seed)      # geometry stream
        self.noise = Noise(w, h, seed)               # noise: private streams
        # planar float32 canvas: per-channel blends are contiguous 2-D ops
        col = hex_rgb(paper)
        self._paper = [float(col[k]) for k in range(3)]
        self.planes = [np.full((h, w), self._paper[k], dtype=np.float32) for k in range(3)]
        self.ops = []                                # recorded raster ops (sequential mode)
        self._stream = None                          # _StreamExec in parallel mode
        self._nw = _num_workers()
        self.last_chunk_stats = None

    # ---------------- ROI helpers ----------------

    def _bbox(self, pts, pad):
        return _bbox_of(pts, pad, self.w, self.h)

    def _polygon_roi(self, pts, softness, pad):
        return _poly_layer(pts, softness, pad, self.w, self.h)

    # ---------------- execution ----------------

    def _emit(self, op):
        """Record one raster/composite op (streamed to the worker pool when
        parallel execution is on)."""
        if self._nw <= 0:
            self.ops.append(op)
            return
        st = self._stream
        if st is None:
            try:
                st = self._stream = _StreamExec(self, _get_pool(self.w, self.h))
            except Exception:
                self._nw = 0                          # no pool: stay sequential
                self.ops.append(op)
                return
        try:
            st.add(op)                 # (records op first; may then dispatch)
        except Exception:
            self._parallel_failed()    # op is already in the stream's records

    def _parallel_failed(self):
        """A worker/pipe died mid-render: rebuild the pixel canvas
        sequentially from the ops that were not yet merged (merged chunks are
        already on the canvas, in order) and continue in sequential mode."""
        st = self._stream
        self._stream = None
        self._nw = 0
        remaining = st.all_ops() if st is not None else []
        if st is not None:
            st.kill()
        self.ops = remaining + self.ops

    def flush(self):
        """Execute (or finish) all recorded ops onto the pixel canvas."""
        st = self._stream
        if st is not None:
            try:
                st.finish()
                self.last_chunk_stats = st.stats
                self._stream = None
                return
            except Exception:
                self._parallel_failed()
        ops, self.ops = self.ops, []
        if ops:
            self._exec_seq(ops)

    def _exec_seq(self, ops):
        tgt = PixelTarget(self.planes)
        for op in ops:
            _exec_op(op, tgt, self.w, self.h)

    # ---------------- compositing (API compatibility) ----------------

    def glaze(self, alpha, color):
        """Multiplicative glaze (full-frame alpha; API compatibility)."""
        self.flush()
        PixelTarget(self.planes).tint(alpha, 0, 0, color, "glaze", 1.0, clamped=False)

    def over(self, alpha, color):
        """Ordinary alpha-over (full-frame alpha; API compatibility)."""
        self.flush()
        PixelTarget(self.planes).tint(alpha, 0, 0, color, "over", 1.0, clamped=False)

    def tint(self, alpha, color, mode="glaze"):
        self.flush()
        PixelTarget(self.planes).tint(alpha, 0, 0, color, mode, 1.0, clamped=False)

    def to_uint8(self):
        self.flush()
        planes = []
        for c in range(3):
            q = self.planes[c] * 255.0
            q += 0.5
            np.clip(q, 0.5, 255.5, out=q)
            planes.append(q.astype(np.uint8))
        return cv2.merge(planes)

    # ---------------- op recording helpers ----------------

    def _bank_keys(self, keys):
        """A primitive is about to use these noise-bank keys: build them here
        (this process executes ops too) and broadcast them to the pool once,
        so no worker ever pays a first-use texture build inside a timed render.
        Keys are generic (feature scale / grain sigma), never scene data."""
        for key in keys:
            if key[0] == "f":
                _fractal_field(self.w, self.h, key[1], key[2], key[3])
            else:
                _grain_field(self.w, self.h, key[1])
        if self._stream is not None:
            try:
                self._stream.pool.prime(keys)
            except Exception:
                pass                   # a dead pipe surfaces on the next dispatch

    def _gran(self, w, h, amount, base, octaves=4, grain=0.03, sigma=0.6):
        """Granulation parameters for a (h,w) layer; draws the two noise-crop
        offsets NOW (in stream order) so execution is a pure function."""
        self._bank_keys([("f", float(base), int(octaves), 0.55), ("g", float(sigma))])
        foff = self.noise.frac_off(w, h)
        goff = self.noise.grain_off(w, h)
        return (float(amount), float(base), int(octaves), float(grain), foff, goff,
                float(sigma))

    def _emit_poly(self, poly, softness, pad, gran_params, edge, color, mode, s):
        x0, y0, w, h = self._bbox(poly, pad)
        if w <= 0 or h <= 0:
            return
        gran = None
        if gran_params is not None:
            gran = self._gran(w, h, *gran_params)
        col = tuple(float(v) for v in np.asarray(color, np.float32))
        self._emit(("poly", x0, y0, w, h, np.asarray(poly, np.float32),
                         float(softness), float(pad), gran, edge,
                         (col, mode, float(s))))

    # ---------------- textures (immediate-mode compatibility) ----------------

    def granulate(self, alpha, amount=0.35, base=24, octaves=4, grain=0.03):
        h, w = alpha.shape[:2]
        if h == 0 or w == 0:
            return alpha
        gran = self._gran(w, h, amount, base, octaves, grain)
        return _granulate(alpha, gran, self.w, self.h)

    def edge_darken(self, alpha, strength=0.6, radius=6):
        return _edge_darken(alpha, strength=strength, radius=radius)

    def paper_texture(self, strength=0.05, seed_offset=0):
        """Multiply a warm fibrous paper texture into the whole canvas."""
        self._bank_keys([("g", 1.0), ("f", 6.0, 3, 0.55)])
        goff = self.noise.grain_off(self.w, self.h)
        foff = self.noise.frac_off(self.w, self.h)
        self._emit(("paper", 0, 0, self.w, self.h, goff, 1.0, foff, 6.0, 3,
                         float(strength)))

    # ---------------- shape building ----------------

    def deform_polygon(self, pts, depth=4, variance=0.35):
        """Recursive midpoint displacement of a polygon (watercolour blob edges).
        Vectorised: one normal draw per edge per level from the geometry
        stream, in edge order."""
        pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
        for _ in range(depth):
            n = len(pts)
            nxt = np.empty_like(pts)                 # == np.roll(pts, -1, 0)
            nxt[:-1] = pts[1:]
            nxt[-1] = pts[0]
            edge = nxt - pts
            length = np.hypot(edge[:, 0], edge[:, 1]).astype(np.float64)
            z = self.rng.standard_normal(n)
            offset = z * (variance * length)
            nlen = length + 1e-6            # |normal| == |edge|
            k = (offset / nlen).astype(np.float32)
            out = np.empty((2 * n, 2), dtype=np.float32)
            out[0::2] = pts
            mid = out[1::2]                           # midpoints, in place
            np.add(pts, nxt, out=mid)
            mid *= 0.5
            mid[:, 0] -= edge[:, 1] * k
            mid[:, 1] += edge[:, 0] * k
            pts = out
        return pts

    def polygon_alpha(self, pts, softness=4.0):
        """Full-frame soft-edged polygon alpha (API compatibility helper)."""
        layer = np.zeros((self.h, self.w), dtype=np.float32)
        a, x0, y0 = self._polygon_roi(pts, softness, 3.0 * softness + 2)
        layer[y0:y0 + a.shape[0], x0:x0 + a.shape[1]] = a
        return layer

    def ellipse_points(self, cx, cy, rx, ry, n=14, jitter=0.0, angle=0.0):
        t = np.linspace(0, 2 * math.pi, n, endpoint=False)
        ca, sa = math.cos(angle), math.sin(angle)
        # vectorised; a size-n normal draw yields the same stream values as n
        # scalar draws, so the geometry stream is unchanged
        if jitter:
            r_j = 1.0 + self.rng.normal(0, jitter, n)
        else:
            r_j = 1.0
        x = np.cos(t) * rx * r_j
        y = np.sin(t) * ry * r_j
        pts = np.empty((n, 2), dtype=np.float64)
        pts[:, 0] = cx + x * ca - y * sa
        pts[:, 1] = cy + x * sa + y * ca
        return pts

    # ---------------- primitives ----------------

    def watercolor_blob(self, pts, color, layers=6, alpha=0.10, softness=3.0,
                        depth=4, variance=0.3, granulation=0.35, edge=0.55,
                        mode="glaze"):
        """Stack several slightly different deformed polygons -> translucent blob
        with characteristic uneven, darker edge."""
        base = self.deform_polygon(pts, depth=max(1, depth - 2), variance=variance)
        radius = max(2, int(softness * 2))
        # the edge-darkening blur needs no extra padding: alpha is exactly 0
        # outside the poly's 3-sigma soft edge, so its rim term is 0 there.
        pad = 3.0 * softness + 2
        edge_p = (float(edge), radius) if edge > 0 else None
        for _ in range(layers):
            poly = self.deform_polygon(base, depth=2, variance=variance * 0.6)
            self._emit_poly(poly, softness, pad, (granulation, 20), edge_p,
                            color, mode, alpha)

    def wash(self, y0, y1, color_top, color_bot, alpha=0.85, x0=0, x1=None,
             mottling=0.45, wobble=18.0, softness=10.0, glazes=3, feather=60.0):
        """A big graded wash between two rows: colour gradient + mottling,
        laid down as several translucent glazes with wobbly, feathered edges
        (a wet-in-wet band rather than a hard-edged stripe)."""
        x1 = self.w if x1 is None else x1
        c0, c1 = np.asarray(color_top, np.float32), np.asarray(color_bot, np.float32)
        yy = np.linspace(0, 1, max(2, y1 - y0), dtype=np.float32)
        # vertical feathering ramp shared by all glazes of this wash
        rows_all = np.arange(self.h, dtype=np.float32)[:, None]
        f = max(1.0, feather)
        ramp = np.clip((rows_all - (y0 - f)) / (2 * f), 0, 1) * \
            np.clip(((y1 + f) - rows_all) / (2 * f), 0, 1)
        ramp = ramp * ramp * (3 - 2 * ramp)   # smoothstep
        # vertical gradient of the tint itself: c0 above y0 -> c1 below y1
        grad = np.zeros((self.h, 1, 3), dtype=np.float32)
        grad[:, 0, :] = c0
        grad[min(self.h, max(0, y1)):, 0, :] = c1
        rows = slice(max(0, y0), min(self.h, y1))
        span = yy[max(0, y0) - y0: min(self.h, y1) - y0, None]
        grad[rows, 0, :] = c0[None, :] * (1 - span) + c1[None, :] * span
        pad = 3.0 * softness + 2
        for g in range(glazes):
            # wobbly boundary polygon (extends past the feather so only the ramp fades)
            # (a size-9 normal draw yields the same values as 9 scalar draws)
            edge_pts = np.empty((18, 2), dtype=np.float64)
            edge_pts[:9, 0] = np.linspace(x0 - f, x1 + f, 9)
            edge_pts[:9, 1] = y0 - f + self.rng.normal(0, wobble * 0.3, 9)
            edge_pts[9:, 0] = np.linspace(x1 + f, x0 - f, 9)
            edge_pts[9:, 1] = y1 + f + self.rng.normal(0, wobble, 9)
            poly = self.deform_polygon(edge_pts, depth=3, variance=0.08)
            bx0, by0, bw, bh = self._bbox(poly, pad)
            if bw <= 0 or bh <= 0:
                continue
            gran = self._gran(bw, bh, mottling, 10, 4, 0.05)
            s = alpha / glazes * (1.2 - 0.2 * g)
            self._emit(("wash", bx0, by0, bw, bh, poly.astype(np.float32),
                             float(softness), float(pad),
                             ramp[by0:by0 + bh].astype(np.float32), gran,
                             grad[by0:by0 + bh].astype(np.float32), float(s)))

    @staticmethod
    def _resample_path(pts):
        """Resample a polyline to ~3 px spacing (vectorised; identical values
        to the per-segment linspace loop, incl. float64 interpolation)."""
        pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
        if len(pts) < 2:
            return pts.copy()
        d = pts[1:] - pts[:-1]                                 # float32 edges
        dl = np.hypot(d[:, 0], d[:, 1]).astype(np.float64)
        n = np.maximum(2, (dl / 3.0).astype(np.int64))         # points per edge
        total = int(n.sum())
        seg_i = np.repeat(np.arange(len(n)), n)                 # edge index/pt
        first = np.zeros(len(n), dtype=np.int64)
        np.cumsum(n[:-1], out=first[1:])
        j = np.arange(total) - first[seg_i]                     # index in edge
        t = j.astype(np.float64) * (1.0 / n[seg_i].astype(np.float64))
        a = pts[:-1][seg_i].astype(np.float64)
        e = d[seg_i].astype(np.float64)
        out = np.empty((total + 1, 2), dtype=np.float32)
        out[:total] = a + e * t[:, None]
        out[total] = pts[-1]
        return out

    @staticmethod
    def _tangent_normals(seg):
        """np.gradient-equivalent unit normals for one path."""
        norm = np.gradient(seg, axis=0)
        norm = np.stack([-norm[:, 1], norm[:, 0]], axis=1)
        norm /= (np.linalg.norm(norm, axis=1, keepdims=True) + 1e-6)
        return norm

    def _emit_strokes(self, segs, tapers, width, color, mode, alpha, softness,
                      texture, pad_extra):
        """Shared tail for stroke/strokes: bbox, segment/thickness batches, and
        the texture-grain offset draw (only when the layer exists)."""
        allpts = np.concatenate(segs, axis=0) if segs else np.zeros((1, 2), np.float32)
        x0, y0, w, h = self._bbox(allpts, pad_extra)
        all_pairs, all_th = [], []
        goff = (0, 0)
        if w > 0 and h > 0:
            for seg, tap in zip(segs, tapers):
                iseg = np.round(seg).astype(np.int32)
                iseg[:, 0] -= x0
                iseg[:, 1] -= y0
                n = len(iseg) - 1
                if n <= 0:
                    continue
                all_pairs.append(np.stack([iseg[:-1], iseg[1:]], axis=1))
                all_th.append(np.round(np.maximum(1.0, width * tap[:n])).astype(np.int32))
            if texture > 0:
                self._bank_keys([("g", 0.9)])
                goff = self.noise.grain_off(w, h)
        if all_pairs:
            pairs = np.concatenate(all_pairs, axis=0)
            th = np.concatenate(all_th, axis=0)
        else:
            pairs = np.zeros((0, 2, 2), np.int32)
            th = np.zeros((0,), np.int32)
        col = tuple(float(v) for v in np.asarray(color, np.float32))
        self._emit(("strokes", x0, y0, w, h, pairs, th, float(softness),
                         float(texture), goff, (col, mode, float(alpha))))

    def stroke(self, pts, color, width=6.0, taper=(0.3, 1.0, 0.2), alpha=0.85,
               softness=1.2, wobble=1.5, texture=0.25, mode="glaze"):
        """Loose brush stroke along a polyline with a tapered width profile."""
        seg = self._resample_path(pts)
        # smooth jitter along the path
        jit = self.noise.grain1d(len(seg), sigma=6.0) * wobble
        norm = self._tangent_normals(seg)
        seg = seg + norm * jit[:, None]
        tap = np.interp(np.linspace(0, 1, len(seg)), np.linspace(0, 1, len(taper)), taper)
        wmax = max(1.0, width * float(np.max(tap)))
        pad = wmax / 2.0 + 3.0 * softness + 3
        self._emit_strokes([seg], [tap], width, color, mode, alpha, softness,
                           texture, pad)

    def strokes(self, paths, color, width=4.0, taper=(1.0, 0.2), alpha=0.7,
                softness=0.8, wobble=1.0, texture=0.2, mode="glaze"):
        """Many small strokes (grass blades, ticks, hatching) sharing one layer
        and one glaze."""
        allp = [np.asarray(p, dtype=np.float32).reshape(-1, 2) for p in paths]
        singles = [p for p in allp if len(p) == 1]        # dots: bbox only
        paths = [p for p in allp if len(p) >= 2]
        col = tuple(float(v) for v in np.asarray(color, np.float32))
        wmax = max(1.0, width * float(np.max(taper)))
        pad = wmax / 2.0 + 3.0 * softness + 3
        if not paths:
            bpts = np.concatenate(singles, axis=0) if singles else \
                np.zeros((1, 2), np.float32)
            x0, y0, w, h = self._bbox(bpts, pad)
            goff = (0, 0)
            if w > 0 and h > 0 and texture > 0:
                self._bank_keys([("g", 0.9)])
                goff = self.noise.grain_off(w, h)
            self._emit(("strokes", x0, y0, w, h, np.zeros((0, 2, 2), np.int32),
                        np.zeros((0,), np.int32), float(softness), float(texture),
                        goff, (col, mode, float(alpha))))
            return
        # ---- batched resample of all paths (~3 px spacing), same values as
        #      the per-segment linspace loop: float64 interpolation, int trunc.
        lens = np.array([len(p) for p in paths], dtype=np.int64)
        pts = np.concatenate(paths, axis=0)                    # (N, 2) float32
        ends = np.cumsum(lens) - 1                              # last row per path
        is_end = np.zeros(len(pts), dtype=bool)
        is_end[ends] = True
        seg_a = pts[:-1][~is_end[:-1]]                            # segment starts
        seg_b = pts[1:][~is_end[:-1]]
        d = seg_b - seg_a                                         # float32 edges
        dl = np.hypot(d[:, 0], d[:, 1]).astype(np.float64)
        nseg = np.maximum(2, (dl / 3.0).astype(np.int64))        # points per edge
        # path index of each segment
        seg_path = np.repeat(np.arange(len(paths)), lens - 1)
        nsum = int(nseg.sum())
        gexcl = np.cumsum(nseg) - nseg                            # exclusive prefix
        base_pos = gexcl + seg_path                               # +1 per prev path end
        # per-path output length: sum of its segment points + final point
        segsum = np.add.reduceat(nseg, np.concatenate(([0], np.cumsum(lens - 1)[:-1])))
        out_len = segsum + 1
        out_start = np.concatenate(([0], np.cumsum(out_len)[:-1]))
        total = int(out_len.sum())
        out = np.empty((total, 2), dtype=np.float32)
        # interpolated points
        gi = np.repeat(np.arange(len(nseg)), nseg)                # segment per point
        j = np.arange(nsum) - gexcl[gi]                            # index inside edge
        t = j.astype(np.float64) * (1.0 / nseg[gi].astype(np.float64))
        pos = base_pos[gi] + j
        out[pos] = seg_a[gi].astype(np.float64) + d[gi].astype(np.float64) * t[:, None]
        # final point of every path
        out[out_start + segsum] = pts[ends]
        # ---- one contiguous jitter draw for all wobbling paths (same stream
        #      values and order as per-path draws) + batched np.gradient tangents
        jit_all = np.zeros(total, dtype=np.float32)
        wob = out_len > 3
        if wobble > 0 and wob.any():
            jits = self.noise.grain1d_batch(out_len[wob], sigma=4.0)
            for st, jl in zip(out_start[wob], jits):
                jit_all[st:st + len(jl)] = jl
            g = np.empty_like(out)
            g[1:-1] = (out[2:] - out[:-2]) / 2.0                  # central diffs
            fs, ls = out_start, out_start + out_len - 1           # path first/last
            g[fs] = out[fs + 1] - out[fs]                         # one-sided ends
            g[ls] = out[ls] - out[ls - 1]
            norm = np.stack([-g[:, 1], g[:, 0]], axis=1)
            norm /= (np.linalg.norm(norm, axis=1, keepdims=True) + 1e-6)
            out = out + norm * (jit_all * wobble)[:, None]
        # ---- batched taper interpolation over each path's own [0,1] ramp
        rel = np.arange(total) - np.repeat(out_start, out_len)
        q = rel.astype(np.float64) * np.repeat(1.0 / (out_len - 1), out_len)
        q[out_start + out_len - 1] = 1.0                        # exact endpoints
        tap = np.interp(q, np.linspace(0, 1, len(taper)), taper)
        # ---- integer segment pairs + rounded thickness, all paths at once
        bpts = np.concatenate([out] + singles, axis=0) if singles else out
        x0, y0, w, h = self._bbox(bpts, pad)
        goff = (0, 0)
        if w > 0 and h > 0:
            iseg = np.round(out).astype(np.int32)
            iseg[:, 0] -= x0
            iseg[:, 1] -= y0
            starts = np.ones(total, dtype=bool)
            starts[out_start + out_len - 1] = False               # not path ends
            si = np.flatnonzero(starts)
            pairs = np.stack([iseg[si], iseg[si + 1]], axis=1)
            th = np.round(np.maximum(1.0, width * tap[si])).astype(np.int32)
            if texture > 0:
                self._bank_keys([("g", 0.9)])
                goff = self.noise.grain_off(w, h)
        else:
            pairs = np.zeros((0, 2, 2), np.int32)
            th = np.zeros((0,), np.int32)
        self._emit(("strokes", x0, y0, w, h, pairs, th, float(softness),
                    float(texture), goff, (col, mode, float(alpha))))

    def dabs(self, rects, color, alpha=0.8, softness=0.7, granulation=0.2, mode="glaze"):
        """A batch of little rectangular dabs (windows, bricks, tesserae)."""
        rects = list(rects)
        pts = []
        for (x, y, w, h) in rects:
            pts.append((x, y))
            pts.append((x + w, y + h))
        if not pts:
            pts = [(0, 0)]
        rx0, ry0, w, h = self._bbox(pts, 3.0 * softness + 3)
        gran = None
        if w > 0 and h > 0 and granulation > 0:
            gran = self._gran(w, h, granulation, 40, 3)
        irects = [(int(round(x)) - rx0, int(round(y)) - ry0,
                   int(round(x + rw)) - rx0, int(round(y + rh)) - ry0)
                  for (x, y, rw, rh) in rects]
        col = tuple(float(v) for v in np.asarray(color, np.float32))
        self._emit(("dabs", rx0, ry0, w, h, irects, float(softness), gran,
                         (col, mode, float(alpha))))

    def scatter(self, xs, ys, radii, color, alpha=0.6, softness=0.7, mode="glaze"):
        """Splatter: a batch of round dots of varying radius in one layer."""
        xs = np.asarray(xs, np.float32)
        ys = np.asarray(ys, np.float32)
        radii = np.asarray(radii, np.float32)
        if len(xs) == 0:
            return
        rmax = float(np.max(radii))
        pts = np.stack([xs, ys], axis=1)
        x0, y0, w, h = self._bbox(pts, rmax + 3.0 * softness + 3)
        dots = [(int(round(x)) - x0, int(round(y)) - y0, max(1, int(round(r))))
                for x, y, r in zip(xs.tolist(), ys.tolist(), radii.tolist())]
        col = tuple(float(v) for v in np.asarray(color, np.float32))
        self._emit(("scatter", x0, y0, w, h, dots, float(softness),
                         (col, mode, float(alpha))))

    def spray(self, cx, cy, rx, ry, color, count=6000, dot=1.2, alpha=0.6,
              falloff=1.6, softness=1.0, mode="glaze"):
        """Airbrushed / stippled cloud of dots with a gaussian falloff from centre."""
        r = np.abs(self.rng.normal(0, 1.0 / falloff, count))
        theta = self.rng.uniform(0, 2 * math.pi, count)
        xs = np.round(cx + np.cos(theta) * r * rx).astype(np.int64)
        ys = np.round(cy + np.sin(theta) * r * ry).astype(np.int64)
        keep = (xs >= 0) & (xs < self.w) & (ys >= 0) & (ys < self.h)
        xs, ys = xs[keep], ys[keep]
        rad = max(1, int(round(dot)))
        if len(xs) == 0:
            return
        pad = rad + 3.0 * softness + 3
        x0 = max(0, int(math.floor(float(xs.min()) - pad)))
        y0 = max(0, int(math.floor(float(ys.min()) - pad)))
        x1 = min(self.w, int(math.ceil(float(xs.max()) + pad)) + 1)
        y1 = min(self.h, int(math.ceil(float(ys.max()) + pad)) + 1)
        col = tuple(float(v) for v in np.asarray(color, np.float32))
        self._emit(("spray", x0, y0, x1 - x0, y1 - y0,
                         (xs - x0).astype(np.int32), (ys - y0).astype(np.int32),
                         rad, float(softness), (col, mode, float(alpha))))

    def outline(self, pts, color=(1, 1, 1), width=3, softness=0.6, alpha=0.95, closed=True):
        """Hard opaque outline (the white halo around rocks / small props)."""
        pts = np.asarray(pts, np.float32).reshape(-1, 2)
        x0, y0, w, h = self._bbox(pts, width + 3.0 * softness + 3)
        ip = np.round(pts).astype(np.int32)
        ip[:, 0] -= x0
        ip[:, 1] -= y0
        col = tuple(float(v) for v in np.asarray(color, np.float32))
        self._emit(("outline", x0, y0, w, h, ip, bool(closed), int(width),
                         float(softness), (col, "over", float(alpha))))

    def flat_shape(self, pts, color, alpha=0.9, softness=1.5, granulation=0.25,
                   edge=0.3, mode="glaze"):
        """Single flat-ish fill with subtle mottling -- for buildings, hulls, etc."""
        pad = 3.0 * softness + 2
        pts = np.asarray(pts, np.float32)
        gran_p = (granulation, 30) if granulation > 0 else None
        edge_p = (float(edge), 3) if edge > 0 else None
        self._emit_poly(pts, softness, pad, gran_p, edge_p, color, mode, alpha)


def _union_bbox(ops, cw, ch):
    """Union of the ROIs an op chunk touches: (x0, y0, x1, y1)."""
    ux0 = min(op[1] for op in ops)
    uy0 = min(op[2] for op in ops)
    ux1 = max(op[1] + op[3] for op in ops)
    uy1 = max(op[2] + op[4] for op in ops)
    for op in ops:
        if op[0] == "paper":
            return 0, 0, cw, ch
    return max(0, ux0), max(0, uy0), min(cw, ux1), min(ch, uy1)
