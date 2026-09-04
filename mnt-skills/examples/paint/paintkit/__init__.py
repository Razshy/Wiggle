"""paintkit: the hill-climbed watercolor toolkit (numpy + OpenCV).

`Canvas` is the imperative painting surface. Primitives are ROI-scoped and
composited multiplicatively (glazes) or alpha-over (opaque marks). All
geometry randomness derives from the canvas seed; texture noise comes from
a scene-independent bank so an edit re-rolls only what was edited.

The sandbox container has one CPU, so the multi-process compositor is off by
default here. Set CANVAS_WORKERS in the environment to override.
"""
import os

os.environ.setdefault("CANVAS_WORKERS", "0")

from .toolkit import Canvas, hex_rgb  # noqa: E402

__all__ = ["Canvas", "hex_rgb"]
