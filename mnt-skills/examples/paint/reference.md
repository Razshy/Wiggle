# paintkit reference

`Canvas` is an imperative watercolor surface. Primitives are ROI-scoped and
composite as multiplicative glazes (pigment darkens paper) or alpha-over
(opaque marks). Colors are RGB in [0,1]; `hex_rgb("#rrggbb")` converts.

```python
from paintkit import Canvas, hex_rgb

def paint(cv: Canvas):
    cv.paper_texture(strength=0.05)
    cv.wash(0, 400, hex_rgb("#a7c4d8"), hex_rgb("#e8d7b8"))
    cv.watercolor_blob(cv.ellipse_points(800, 200, 220, 90),
                       hex_rgb("#ffffff"), layers=5, alpha=0.12)
    # ... more primitives
```

`render.py` calls `paint(cv)` on a fresh `Canvas(width, height, seed)` and
writes the result. All geometry randomness derives from the seed, so a
re-render with the same seed reproduces the same painting.

## Primitives

| method | args | for |
|---|---|---|
| `paper_texture` | `strength` | fibrous cold-press grain over the whole sheet |
| `wash` | `y0, y1, top, bot, alpha, x0, x1, mottling, wobble, softness, glazes, feather` | graded background wash between two colors |
| `watercolor_blob` | `pts, color, layers, alpha, softness, depth, variance, granulation, edge, mode` | the core wet shape: deformed polygon, layered, granulated, dark-edged |
| `stroke` | `pts, color, width, taper, alpha, softness, wobble, texture, mode` | one loaded-brush line |
| `strokes` | `paths, color, width, taper, alpha, softness, wobble, texture, mode` | many strokes in one batched call |
| `dabs` | `rects, color, alpha, softness, granulation, mode` | rectangles as soft glazes (windows, bricks) |
| `scatter` | `xs, ys, radii, color, alpha, softness, mode` | many small circles (leaves, gravel) |
| `spray` | `cx, cy, rx, ry, color, count, dot, alpha, falloff, softness, mode` | airbrush ellipse (mist, fur, foam) |
| `outline` | `pts, color, width, softness, alpha, closed` | hard ink line, usually white or sepia |
| `flat_shape` | `pts, color, alpha, softness, granulation, edge, mode` | filled polygon, no deformation |
| `glaze` / `over` / `tint` | `alpha, color` | full-frame composite of a mask you built yourself |

`mode` is `"glaze"` (multiplicative, the watercolor default) or `"over"`
(opaque). `pts` is an (N,2) array of pixel coordinates.

## Helpers

| method | returns |
|---|---|
| `ellipse_points(cx, cy, rx, ry, n, jitter, angle)` | polygon approximating an ellipse |
| `deform_polygon(pts, depth, variance)` | recursively wobbled polygon |
| `polygon_alpha(pts, softness)` | soft filled-polygon mask |
| `granulate(alpha, ...)` / `edge_darken(alpha, ...)` | apply the wash effects to a mask you built |
| `to_uint8()` | flush and return the (H, W, 3) uint8 RGB image |
| `hex_rgb("#rrggbb")` | (r, g, b) in [0,1] |

## Randomness

`Canvas.rng` is the geometry stream (polygon deformation, jitter, wobble,
spray positions, and anything the scene draws itself). Use `cv.rng.uniform`,
`cv.rng.integers` etc. for procedural placement so the scene stays
reproducible. Texture noise (granulation, paper) comes from a fixed
scene-independent bank and does not consume the geometry stream.

## Budget

The container has one CPU and a 300 s wall clock per call. A full 18-element
scene renders in about a second at 1600×900 sequential.
Prefer `--scale 0.5` while iterating. `examples/full_scene.py` in this skill
directory is a worked 18-element scene using every primitive; read it for
patterns before writing your own.
