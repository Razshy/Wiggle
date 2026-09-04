#!/usr/bin/env python3
"""Run a scene file and write a PNG.

    python /mnt/skills/examples/paint/render.py scene.py -o out.png
    python /mnt/skills/examples/paint/render.py scene.py -o preview.png --scale 0.5

The scene file is executed with paintkit on sys.path and must define one of:
  - `render() -> np.ndarray` returning uint8 RGB (H, W, 3), or
  - `paint(cv: Canvas) -> None` that draws onto the canvas passed in.

`--width/--height/--seed` are used only for the `paint(cv)` form; a `render()`
function owns its own dimensions.
"""
import argparse
import os
import runpy
import sys
import time
from pathlib import Path

# One CPU in the sandbox container: run the compositor in-process.
os.environ.setdefault("CANVAS_WORKERS", "0")

SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))
from paintkit import Canvas  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("scene", help="path to a Python file defining render() or paint(cv)")
    p.add_argument("-o", "--out", default="out.png")
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--width", type=int, default=1600)
    p.add_argument("--height", type=int, default=900)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    ns = runpy.run_path(args.scene, init_globals={"__paintkit__": True})
    render = ns.get("render")
    paint = ns.get("paint")

    t0 = time.monotonic()
    if callable(render):
        img = render()
    elif callable(paint):
        cv = Canvas(args.width, args.height, seed=args.seed)
        paint(cv)
        img = cv.to_uint8()
    else:
        print(f"error: {args.scene} defines neither render() nor paint(cv)",
              file=sys.stderr)
        return 2
    dt = time.monotonic() - t0

    img = np.asarray(img)
    if img.ndim != 3 or img.shape[2] != 3:
        print(f"error: expected (H, W, 3) uint8, got {img.shape}", file=sys.stderr)
        return 2
    if args.scale != 1.0:
        h, w = img.shape[:2]
        img = cv2.resize(img, (max(1, int(w * args.scale)), max(1, int(h * args.scale))),
                         interpolation=cv2.INTER_AREA)
    # toolkit works in RGB; cv2.imwrite expects BGR.
    if not cv2.imwrite(args.out, cv2.cvtColor(img, cv2.COLOR_RGB2BGR)):
        raise IOError(f"cv2.imwrite failed for {args.out!r}")
    print(f"wrote {args.out}  ({img.shape[1]}x{img.shape[0]}, {dt:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
