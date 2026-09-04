"""
full_scene.py -- one fixed, seeded reference scene.

A landscape band: a graded watercolour sky with mottled clouds and a red
comms line weaving through them, two soft-sprayed sky whales, distant hill
washes, an aqueduct carrying a monorail with a little train, a cluster of city
blocks shaded with purple, foreground washes, hard-outlined rocks, foliage
strokes, a lone traveller and scattered loose accents.

render() is deterministic (fixed seed) and returns a WxH (1600x900) uint8 RGB
frame.

Layout is authored in a fixed 2560x1440 *design* coordinate space (DW x DH);
the output canvas is W x H and every geometric quantity (points, radii,
stroke widths, blur softness, dot sizes, ...) is scaled by S = W / DW on the
way into the toolkit, so the composition is resolution independent and the
whole scene rescales from the single output-size constant below.
"""

import math
import numpy as np

from paintkit import Canvas, hex_rgb

# design (layout) space -- element code below is written in these units
DW, DH = 2560, 1440
# output resolution (the single knob) and the design->output scale
W, H = 1600, 900
S = W / DW
SEED = 20260720


class ScaledCanvas(Canvas):
    """Canvas that accepts geometry in design units and renders at W x H.

    Positions, sizes, widths, blur sigmas and dot radii scale by S; spray dot
    counts scale by S*S so airbrush density per output pixel is unchanged."""

    def __init__(self, seed=1, paper="#f4eee0"):
        super().__init__(W, H, seed=seed, paper=paper)

    @staticmethod
    def _pts(pts):
        return np.asarray(pts, dtype=np.float32) * S

    def watercolor_blob(self, pts, color, layers=6, alpha=0.10, softness=3.0,
                        depth=4, variance=0.3, granulation=0.35, edge=0.55,
                        mode="glaze"):
        super().watercolor_blob(self._pts(pts), color, layers=layers,
                                 alpha=alpha, softness=softness * S, depth=depth,
                                 variance=variance, granulation=granulation,
                                 edge=edge, mode=mode)

    def wash(self, y0, y1, color_top, color_bot, alpha=0.85, x0=0, x1=None,
             mottling=0.45, wobble=18.0, softness=10.0, glazes=3, feather=60.0):
        x1s = None if x1 is None else int(round(x1 * S))
        super().wash(int(round(y0 * S)), int(round(y1 * S)), color_top,
                     color_bot, alpha=alpha, x0=int(round(x0 * S)), x1=x1s,
                     mottling=mottling, wobble=wobble * S,
                     softness=softness * S, glazes=glazes, feather=feather * S)

    def stroke(self, pts, color, width=6.0, taper=(0.3, 1.0, 0.2), alpha=0.85,
               softness=1.2, wobble=1.5, texture=0.25, mode="glaze"):
        super().stroke(self._pts(pts), color, width=width * S, taper=taper,
                       alpha=alpha, softness=softness * S, wobble=wobble * S,
                       texture=texture, mode=mode)

    def strokes(self, paths, color, width=4.0, taper=(1.0, 0.2), alpha=0.7,
                softness=0.8, wobble=1.0, texture=0.2, mode="glaze"):
        super().strokes([self._pts(p) for p in paths], color,
                        width=width * S, taper=taper, alpha=alpha,
                        softness=softness * S, wobble=wobble * S,
                        texture=texture, mode=mode)

    def dabs(self, rects, color, alpha=0.8, softness=0.7, granulation=0.2,
             mode="glaze"):
        rects = [(x * S, y * S, w * S, h * S) for (x, y, w, h) in rects]
        super().dabs(rects, color, alpha=alpha, softness=softness * S,
                     granulation=granulation, mode=mode)

    def scatter(self, xs, ys, radii, color, alpha=0.6, softness=0.7,
                mode="glaze"):
        super().scatter(np.asarray(xs) * S, np.asarray(ys) * S,
                        np.asarray(radii) * S, color, alpha=alpha,
                        softness=softness * S, mode=mode)

    def spray(self, cx, cy, rx, ry, color, count=6000, dot=1.2, alpha=0.6,
              falloff=1.6, softness=1.0, mode="glaze"):
        super().spray(cx * S, cy * S, rx * S, ry * S, color,
                      count=max(1, int(round(count * S * S))), dot=dot * S,
                      alpha=alpha, falloff=falloff, softness=softness * S,
                      mode=mode)

    def outline(self, pts, color=(1, 1, 1), width=3, softness=0.6,
                alpha=0.95, closed=True):
        super().outline(self._pts(pts), color, width=max(1, int(round(width * S))),
                        softness=softness * S, alpha=alpha, closed=closed)

    def flat_shape(self, pts, color, alpha=0.9, softness=1.5,
                   granulation=0.25, edge=0.3, mode="glaze"):
        super().flat_shape(self._pts(pts), color, alpha=alpha,
                           softness=softness * S, granulation=granulation,
                           edge=edge, mode=mode)

# --------------------------------------------------------------------------
# palette
# --------------------------------------------------------------------------
SKY_TOP = hex_rgb("#4f83c9")
SKY_MID = hex_rgb("#9fbde0")
SKY_BOT = hex_rgb("#f3dcae")
CLOUD_SHADE = hex_rgb("#a49bc4")     # cool violet shadow inside clouds
CLOUD_WARM = hex_rgb("#e4b98d")
HILL_FAR = hex_rgb("#8b98c0")
HILL_MID = hex_rgb("#6f8c7e")
HILL_NEAR = hex_rgb("#7d9560")
GROUND = hex_rgb("#c4b783")
GROUND2 = hex_rgb("#a3915f")
STONE = hex_rgb("#c9b190")
STONE_SHADE = hex_rgb("#71589a")     # purple used as shading
CITY_LIGHT = hex_rgb("#ddc9b1")
CITY_WARM = hex_rgb("#dc9a6a")
CITY_PURPLE = hex_rgb("#7d5aa8")
WHALE = hex_rgb("#7797c2")
WHALE_DARK = hex_rgb("#3f5a86")
ROCK = hex_rgb("#8c7c69")
ROCK_DARK = hex_rgb("#463a34")
FOLIAGE = hex_rgb("#4b7838")
FOLIAGE2 = hex_rgb("#8fac4a")
INK = hex_rgb("#37324a")
LINE_RED = hex_rgb("#c34e34")
WHITE = np.array([1.0, 1.0, 0.985], dtype=np.float32)


# --------------------------------------------------------------------------
# elements
# --------------------------------------------------------------------------

def sky_wash(cv):
    """Two graded washes: cool blue high sky fading into a warm horizon glow."""
    cv.wash(-160, 470, SKY_TOP, SKY_MID, alpha=0.92, glazes=3, mottling=0.4,
            wobble=30, softness=40)
    cv.wash(380, 780, SKY_MID, SKY_BOT, alpha=0.75, glazes=2, mottling=0.35,
            wobble=25, softness=45)


def sun_glow(cv):
    """Warm bloom low on the horizon behind the city."""
    cv.spray(1900, 700, 620, 240, hex_rgb("#f5be7a"), count=12000, dot=4,
             alpha=0.45, falloff=1.4, softness=22)
    cv.spray(1900, 720, 260, 110, hex_rgb("#fbe6b3"), count=6000, dot=3,
             alpha=0.55, falloff=1.4, softness=16, mode="over")


def _cloud(cv, cx, cy, w, h, puffs, warm_side=1):
    """A cloud: violet wash shadow tucked under the belly, a warm blush on the
    sunward side, and bright airbrushed white body puffs on top."""
    rng = cv.rng
    # violet shadow under the belly
    for i in range(3):
        px = cx + rng.uniform(-w * 0.35, w * 0.35)
        py = cy + h * 0.30 + rng.uniform(-h * 0.05, h * 0.10)
        pts = cv.ellipse_points(px, py, w * rng.uniform(0.3, 0.45),
                                h * rng.uniform(0.25, 0.35), n=12, jitter=0.08)
        cv.watercolor_blob(pts, CLOUD_SHADE, layers=2, alpha=0.07, softness=12,
                           granulation=0.5, edge=0.2)
    # warm blush on the sun side
    pts = cv.ellipse_points(cx + warm_side * w * 0.25, cy + h * 0.05,
                            w * 0.3, h * 0.35, n=12, jitter=0.1)
    cv.watercolor_blob(pts, CLOUD_WARM, layers=3, alpha=0.06, softness=10,
                       granulation=0.4, edge=0.15)
    # bright body puffs: soft opaque white blobs
    for i in range(puffs):
        px = cx + rng.uniform(-w * 0.42, w * 0.42)
        py = cy + rng.uniform(-h * 0.32, h * 0.05)
        pts = cv.ellipse_points(px, py, w * rng.uniform(0.24, 0.34),
                                h * rng.uniform(0.32, 0.5), n=12, jitter=0.10)
        cv.watercolor_blob(pts, WHITE, layers=3, alpha=0.33, softness=14,
                           depth=3, variance=0.12, granulation=0.25, edge=0.0,
                           mode="over")
    # a little sprayed sparkle along the top
    cv.spray(cx, cy - h * 0.15, w * 0.42, h * 0.28, WHITE, count=4500, dot=3,
             alpha=0.4, falloff=1.6, softness=8, mode="over")


def clouds(cv):
    _cloud(cv, 480, 250, 640, 230, puffs=5, warm_side=1)
    _cloud(cv, 1290, 180, 760, 250, puffs=6, warm_side=1)
    _cloud(cv, 2230, 300, 600, 210, puffs=5, warm_side=-1)


def comms_line(cv):
    """Thin red comms cable weaving through the clouds, with node beads."""
    xs = np.linspace(-20, DW + 20, 30)
    ys = 300 + 95 * np.sin(xs / 270.0) + 42 * np.sin(xs / 101.0 + 1.3)
    pts = np.stack([xs, ys], axis=1)
    cv.stroke(pts, LINE_RED, width=2.6, taper=(0.9, 1.0, 1.0, 0.9), alpha=0.75,
              softness=0.7, wobble=1.0, texture=0.3)
    # node beads and their little antennae
    ticks = []
    for i in range(2, 28, 4):
        x, y = pts[i]
        cv.spray(x, y, 6, 6, LINE_RED, count=180, dot=2, alpha=0.9, falloff=2.4,
                 softness=0.9)
        ticks.append([(x, y), (x + 6, y - 24)])
    cv.strokes(ticks, LINE_RED, width=1.5, taper=(1.0, 0.4), alpha=0.5,
               softness=0.5, wobble=0.4, texture=0.2)


def _whale(cv, cx, cy, length, flip=1):
    """Soft-sprayed sky whale: watercolour body silhouette, airbrushed shading,
    pale belly highlight, flukes, fin and a tiny dark eye."""
    L = length
    prof = [  # (dx, dy) profile from nose (front, x negative) round to nose
        (-0.50, -0.02), (-0.47, -0.13), (-0.36, -0.21), (-0.18, -0.23),
        (0.05, -0.19), (0.28, -0.11), (0.46, -0.03), (0.56, 0.00),
        (0.46, 0.05), (0.28, 0.11), (0.05, 0.16), (-0.20, 0.14),
        (-0.40, 0.07), (-0.49, 0.02),
    ]
    body = [(cx + dx * L * flip, cy + dy * L) for dx, dy in prof]
    cv.watercolor_blob(body, WHALE, layers=4, alpha=0.14, softness=7,
                       depth=3, variance=0.10, granulation=0.45, edge=0.55)
    # darker airbrushed back
    cv.spray(cx + 0.02 * L * flip, cy - 0.10 * L, 0.42 * L, 0.09 * L, WHALE_DARK,
             count=5200, dot=3, alpha=0.30, falloff=1.5, softness=9)
    # pale sprayed belly
    cv.spray(cx - 0.05 * L * flip, cy + 0.08 * L, 0.36 * L, 0.05 * L,
             hex_rgb("#dfe6ee"), count=3500, dot=3, alpha=0.35, falloff=1.5,
             softness=8, mode="over")
    # tail flukes
    tx, ty = cx + 0.56 * L * flip, cy
    fluke = [(tx - 0.03 * L * flip, ty - 0.03 * L),
             (tx + 0.14 * L * flip, ty - 0.16 * L),
             (tx + 0.08 * L * flip, ty - 0.01 * L),
             (tx + 0.15 * L * flip, ty + 0.14 * L),
             (tx - 0.03 * L * flip, ty + 0.03 * L)]
    cv.watercolor_blob(fluke, WHALE, layers=4, alpha=0.12, softness=5,
                       depth=3, variance=0.10, granulation=0.4, edge=0.45)
    # pectoral fin
    fx, fy = cx - 0.20 * L * flip, cy + 0.10 * L
    fin = [(fx, fy), (fx - 0.10 * L * flip, fy + 0.12 * L), (fx + 0.06 * L * flip, fy + 0.06 * L)]
    cv.watercolor_blob(fin, WHALE_DARK, layers=3, alpha=0.10, softness=4,
                       depth=3, variance=0.12, granulation=0.4, edge=0.3)
    # eye and mouth crease
    cv.spray(cx - 0.40 * L * flip, cy - 0.04 * L, 4, 4, ROCK_DARK, count=140,
             dot=1, alpha=0.95, falloff=3, softness=0.7)
    cv.stroke([(cx - 0.49 * L * flip, cy + 0.02 * L),
               (cx - 0.36 * L * flip, cy + 0.05 * L)], WHALE_DARK, width=3,
              taper=(1.0, 0.3), alpha=0.5, softness=1.0, wobble=0.8)


def whale_big(cv):
    _whale(cv, 780, 480, 560, flip=1)


def whale_small(cv):
    _whale(cv, 2050, 540, 300, flip=-1)


def distant_hills(cv):
    """Three overlapping soft hill washes near the horizon (aerial perspective)."""
    rng = cv.rng
    layers = [(700, 60, HILL_FAR, 0.45), (760, 80, HILL_MID, 0.5),
              (830, 60, HILL_NEAR, 0.5)]
    for band, (base_y, amp, col, a) in enumerate(layers):
        xs = np.linspace(-100, DW + 100, 16)
        ys = base_y - amp * (0.5 + 0.5 * np.sin(xs / (330 + 80 * band) + band * 1.7))
        ys = ys + rng.normal(0, 10, xs.shape)
        top = list(zip(xs, ys))
        pts = top + [(DW + 100, base_y + 240), (-100, base_y + 240)]
        cv.watercolor_blob(pts, col, layers=4, alpha=a * 0.28, softness=8,
                           depth=3, variance=0.04, granulation=0.55, edge=0.35)


def midground_wash(cv):
    cv.wash(880, 1200, HILL_NEAR, GROUND, alpha=0.7, glazes=3, mottling=0.55,
            wobble=16, softness=12)
    cv.wash(1000, 1240, GROUND, GROUND2, alpha=0.6, glazes=2, mottling=0.5,
            wobble=14, softness=12)


def aqueduct(cv):
    """Stone aqueduct: deck, tapering piers with purple shaded sides, arched
    spandrels and shadowed soffits."""
    y_top, y_deck = 852, 884
    x0, x1 = 40, 1490
    cv.flat_shape([(x0, y_top), (x1 + 8, y_top), (x1 + 8, y_deck), (x0, y_deck)],
                  STONE, alpha=0.92, granulation=0.35, edge=0.5)
    # a shading band under the deck lip
    cv.flat_shape([(x0, y_deck - 6), (x1 + 8, y_deck - 6), (x1 + 8, y_deck + 4),
                   (x0, y_deck + 4)], STONE_SHADE, alpha=0.3, granulation=0.3,
                  edge=0.1, softness=2)
    n = 8
    span = (x1 - x0) / n
    ground = 1090
    for i in range(n + 1):
        px = x0 + i * span
        pw_top, pw_bot = 24, 42
        pier = [(px - pw_top / 2, y_deck), (px + pw_top / 2, y_deck),
                (px + pw_bot / 2, ground), (px - pw_bot / 2, ground)]
        cv.flat_shape(pier, STONE, alpha=0.9, granulation=0.4, edge=0.45)
        shade = [(px - pw_top / 2, y_deck), (px - pw_top / 2 + 10, y_deck),
                 (px - pw_bot / 2 + 14, ground), (px - pw_bot / 2, ground)]
        cv.flat_shape(shade, STONE_SHADE, alpha=0.38, granulation=0.3, edge=0.1)
    for i in range(n):
        ax0 = x0 + i * span + 18
        ax1 = x0 + (i + 1) * span - 18
        crown = y_deck + 78
        xs = np.linspace(ax0, ax1, 16)
        ys = y_deck + (crown - y_deck) * (1 - np.sin(np.linspace(0, math.pi, 16)))
        pts = [(ax0, y_deck)] + list(zip(xs, ys)) + [(ax1, y_deck)]
        cv.flat_shape(pts, STONE, alpha=0.85, granulation=0.3, edge=0.4)
        soff = list(zip(xs, ys + 3)) + list(zip(xs[::-1], ys[::-1] + 24))
        cv.flat_shape(soff, STONE_SHADE, alpha=0.4, granulation=0.3, edge=0.0,
                      softness=3)


def monorail(cv):
    """Rail on top of the aqueduct + a small streamlined train."""
    y = 845
    cv.stroke([(30, y), (1510, y)], ROCK_DARK, width=3, taper=(1, 1, 1),
              alpha=0.7, softness=0.6, wobble=0.6, texture=0.3)
    ticks = [[(x, y), (x, y + 9)] for x in range(110, 1500, 90)]
    cv.strokes(ticks, ROCK_DARK, width=2, taper=(1, 1), alpha=0.6,
               softness=0.5, wobble=0.2)
    # train: three rounded cars with a red stripe
    tx, ty = 930, y - 27
    windows = []
    for i in range(3):
        cx = tx + i * 80
        car = cv.ellipse_points(cx, ty + 12, 41, 14, n=16, jitter=0.03)
        cv.flat_shape(car, hex_rgb("#ece5d7"), alpha=0.9, granulation=0.2,
                      edge=0.55, softness=1.0)
        cv.flat_shape(cv.ellipse_points(cx, ty + 17, 37, 6, n=12),
                      LINE_RED, alpha=0.75, granulation=0.2, edge=0.3, softness=0.8)
        for w in range(-2, 3):
            windows.append((cx + w * 12 - 3, ty + 5, 5, 6))
    cv.dabs(windows, INK, alpha=0.75, softness=0.6, granulation=0.15)
    # nose cone
    cv.flat_shape([(tx - 40, ty + 4), (tx - 80, ty + 18), (tx - 40, ty + 22)],
                  hex_rgb("#ece5d7"), alpha=0.9, granulation=0.2, edge=0.55,
                  softness=1.0)


def city_blocks(cv):
    """Cluster of tower blocks: light faces, purple shaded sides, roof caps,
    grids of window dabs, and a pooled violet ground shadow."""
    rng = cv.rng
    base_y = 1020
    x = 1560
    towers = []
    while x < 2500:
        w = rng.uniform(70, 130)
        h = rng.uniform(150, 430)
        towers.append((x, w, h))
        x += w * rng.uniform(0.55, 0.9)
    towers.sort(key=lambda t: t[1] * 0.4 - t[2])   # tall, thin ones behind
    for (tx, tw, th) in towers:
        top = base_y - th
        face_col = CITY_LIGHT if rng.random() < 0.6 else CITY_WARM
        cv.flat_shape([(tx, top), (tx + tw, top), (tx + tw, base_y), (tx, base_y)],
                      face_col, alpha=0.85, granulation=0.35, edge=0.5)
        sw = tw * 0.28
        cv.flat_shape([(tx + tw - sw, top), (tx + tw, top), (tx + tw, base_y),
                       (tx + tw - sw, base_y)], CITY_PURPLE, alpha=0.55,
                      granulation=0.3, edge=0.2)
        cv.flat_shape([(tx - 4, top), (tx + tw + 4, top), (tx + tw + 4, top + 10),
                       (tx - 4, top + 10)], CITY_PURPLE, alpha=0.5,
                      granulation=0.2, edge=0.2)
        # windows -- little dabs in a loose grid, all in one pass per tower
        wins, warm_wins = [], []
        for wy in np.arange(top + 26, base_y - 22, 28):
            for wx in np.arange(tx + 12, tx + tw - sw - 10, 21):
                if rng.random() < 0.72:
                    (warm_wins if rng.random() < 0.15 else wins).append(
                        (wx + rng.uniform(-1, 1), wy + rng.uniform(-1, 1), 8, 12))
        cv.dabs(wins, INK, alpha=0.7, softness=0.7, granulation=0.15)
        if warm_wins:
            cv.dabs(warm_wins, hex_rgb("#f0b060"), alpha=0.8, softness=0.7,
                    granulation=0.1, mode="over")
    # pooled violet shadow at the feet of the city
    cv.wash(base_y - 8, base_y + 110, STONE_SHADE, STONE_SHADE, alpha=0.35,
            x0=1520, x1=DW, glazes=2, mottling=0.5, wobble=6, softness=12)


def foreground_wash(cv):
    cv.wash(1150, 1470, GROUND2, hex_rgb("#7d6a45"), alpha=0.85, glazes=3,
            mottling=0.6, wobble=22, softness=12)


def path_stroke(cv):
    """A pale winding path leading toward the aqueduct."""
    xs = np.linspace(320, 940, 14)
    ys = 1450 - (xs - 320) * 0.48 + 32 * np.sin(xs / 85.0)
    cv.stroke(np.stack([xs, ys], 1), hex_rgb("#efe4c6"), width=52,
              taper=(1.5, 0.9, 0.35), alpha=0.7, softness=5, wobble=6,
              texture=0.4, mode="over")
    cv.stroke(np.stack([xs, ys - 4], 1), hex_rgb("#b09a70"), width=18,
              taper=(1.2, 0.8, 0.3), alpha=0.28, softness=3, wobble=5)


def rocks(cv):
    """Foreground rocks: mottled body, shadow lobe, ink cracks, hard white outline."""
    rng = cv.rng
    anchors = [(230, 1265, 92), (430, 1300, 60), (630, 1245, 108),
               (880, 1310, 68), (1130, 1272, 96), (1420, 1320, 54),
               (2170, 1280, 100), (2385, 1330, 66)]
    for (rx, ry, rr) in anchors:
        pts = cv.ellipse_points(rx, ry, rr, rr * 0.72, n=9, jitter=0.16,
                                angle=rng.uniform(-0.3, 0.3))
        base = cv.deform_polygon(pts, depth=3, variance=0.10)
        cv.watercolor_blob(base, ROCK, layers=4, alpha=0.2, softness=2.5,
                           depth=2, variance=0.07, granulation=0.5, edge=0.6)
        shade = cv.ellipse_points(rx + rr * 0.25, ry + rr * 0.18, rr * 0.7,
                                  rr * 0.48, n=8, jitter=0.14)
        cv.watercolor_blob(shade, ROCK_DARK, layers=3, alpha=0.15, softness=3,
                           depth=2, variance=0.1, granulation=0.4, edge=0.3)
        cv.stroke([(rx - rr * 0.4, ry - rr * 0.1), (rx + rr * 0.1, ry + rr * 0.05),
                   (rx + rr * 0.35, ry - rr * 0.05)], ROCK_DARK, width=2,
                  taper=(0.4, 1, 0.3), alpha=0.55, softness=0.6, wobble=1.0)
        cv.outline(base, WHITE, width=5, softness=0.9, alpha=0.92)


def foliage(cv):
    """Loose brushy grass tufts along the foreground plus two shrubs."""
    rng = cv.rng
    tufts = 34
    dark_blades, light_blades = [], []
    for _ in range(tufts):
        bx = rng.uniform(0, DW)
        by = rng.uniform(1160, 1425)
        for _ in range(int(rng.integers(3, 7))):
            length = rng.uniform(28, 78)
            ang = rng.uniform(-0.65, 0.65)
            mid = (bx + math.sin(ang) * length * 0.5 + rng.uniform(-4, 4),
                   by - math.cos(ang) * length * 0.5)
            tip = (bx + math.sin(ang) * length, by - math.cos(ang) * length)
            (dark_blades if rng.random() < 0.6 else light_blades).append(
                [(bx, by), mid, tip])
    cv.strokes(dark_blades, FOLIAGE, width=5, taper=(1.0, 0.7, 0.1), alpha=0.7,
               softness=0.9, wobble=1.2, texture=0.3)
    cv.strokes(light_blades, FOLIAGE2, width=5, taper=(1.0, 0.7, 0.1), alpha=0.6,
               softness=0.9, wobble=1.2, texture=0.3)
    # two shrubs: overlapping green watercolour blobs
    for sx, sy, sr in [(1770, 1180, 74), (190, 1190, 56)]:
        for _ in range(6):
            pts = cv.ellipse_points(sx + rng.uniform(-sr, sr) * 0.6,
                                    sy + rng.uniform(-sr, sr) * 0.4,
                                    sr * rng.uniform(0.5, 0.8),
                                    sr * rng.uniform(0.4, 0.7), n=10, jitter=0.15)
            cv.watercolor_blob(pts, FOLIAGE if rng.random() < 0.5 else FOLIAGE2,
                               layers=3, alpha=0.13, softness=3, depth=3,
                               variance=0.15, granulation=0.5, edge=0.4)


def traveller(cv):
    """Tiny figure on the path: red coat, dot head, stick legs, staff, cast shadow."""
    x, y = 720, 1205
    cv.stroke([(x - 2, y + 26), (x + 40, y + 34)], STONE_SHADE, width=9,
              taper=(1, 0.3), alpha=0.35, softness=2.5)
    cv.flat_shape([(x - 8, y - 10), (x + 8, y - 10), (x + 10, y + 14),
                   (x - 10, y + 14)], LINE_RED, alpha=0.9, granulation=0.2,
                  edge=0.4, softness=1)
    cv.spray(x, y - 18, 7, 7, ROCK_DARK, count=260, dot=2, alpha=0.9,
             falloff=3, softness=0.9)
    cv.strokes([[(x - 4, y + 14), (x - 7, y + 32)],
                [(x + 4, y + 14), (x + 8, y + 32)],
                [(x + 9, y - 2), (x + 24, y + 30)]], ROCK_DARK, width=3,
               taper=(1, 0.7), alpha=0.85, softness=0.5, wobble=0.3)


def accents(cv):
    """Scattered loose marks: distant birds, wind dashes, pigment splatters."""
    rng = cv.rng
    birds = []
    for _ in range(12):
        bx, by = rng.uniform(150, 2450), rng.uniform(70, 640)
        s = rng.uniform(9, 20)
        birds.append([(bx - s, by + s * 0.45), (bx, by), (bx + s, by + s * 0.5)])
    cv.strokes(birds, INK, width=2, taper=(0.5, 1.0, 0.5), alpha=0.6,
               softness=0.6, wobble=0.8)
    for _ in range(8):
        wx, wy = rng.uniform(0, DW - 200), rng.uniform(110, 690)
        l = rng.uniform(70, 190)
        cv.stroke([(wx, wy), (wx + l, wy + rng.uniform(-9, 9))], WHITE,
                  width=3, taper=(0.2, 1, 0.2), alpha=0.55, softness=1.2,
                  wobble=1.5, mode="over")
    # pigment splatters flicked across the foreground
    n = 90
    xs, ys = rng.uniform(0, DW, n), rng.uniform(1140, 1440, n)
    rs = rng.uniform(1.5, 6.5, n)
    dark = rng.random(n) < 0.5
    cv.scatter(xs[dark], ys[dark], rs[dark], ROCK_DARK, alpha=0.55, softness=0.7)
    cv.scatter(xs[~dark], ys[~dark], rs[~dark], FOLIAGE, alpha=0.5, softness=0.7)


def paper(cv):
    cv.paper_texture(strength=0.045)


# --------------------------------------------------------------------------
# scene registry (draw order matters)
# --------------------------------------------------------------------------

ELEMENTS = [
    ("sky_wash", sky_wash),
    ("sun_glow", sun_glow),
    ("distant_hills", distant_hills),
    ("clouds", clouds),
    ("comms_line", comms_line),
    ("whale_big", whale_big),
    ("whale_small", whale_small),
    ("midground_wash", midground_wash),
    ("aqueduct", aqueduct),
    ("monorail", monorail),
    ("city_blocks", city_blocks),
    ("foreground_wash", foreground_wash),
    ("path_stroke", path_stroke),
    ("rocks", rocks),
    ("foliage", foliage),
    ("traveller", traveller),
    ("accents", accents),
    ("paper", paper),
]


def render(timing=None):
    """Render the fixed scene; returns (h, w, 3) uint8 RGB.

    If `timing` is a dict, per-element wall times (ms) are accumulated into it.
    """
    import time
    cv = ScaledCanvas(seed=SEED, paper="#f4eee0")
    for name, fn in ELEMENTS:
        t0 = time.perf_counter()
        fn(cv)
        if timing is not None:
            timing[name] = timing.get(name, 0.0) + (time.perf_counter() - t0) * 1000.0
    return cv.to_uint8()


if __name__ == "__main__":
    import cv2
    img = render()
    cv2.imwrite("render.png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    print("wrote render.png")
