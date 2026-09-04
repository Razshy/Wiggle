---
name: paint
description: Paint an original image in a watercolor style by writing code, not by calling an image model. Use when the user asks you to draw, paint, sketch, or make a picture of something and there is no image-generation tool available, or when they ask for a painting, watercolor, or illustration you can iterate on. Do not use for charts, diagrams, UI mockups, or requests to edit an existing photograph.
license: Complete terms in LICENSE.txt
---

# Code-drawn watercolor

You paint by writing a short Python function against `paintkit.Canvas`, an
OpenCV watercolor toolkit bundled with this skill. Geometry is seeded, so you
can look at the output, fix the two worst things, and re-render the same
painting with only your edit changed.

**Read `reference.md` in this skill directory once before your first scene.**
It documents every primitive. `examples/full_scene.py` is a worked 18-element
scene that uses every primitive; skim it for patterns before starting. Do not
paste either into the conversation.

## Workflow

Run each step with `bash_tool`. This skill is mounted read-only at
`/mnt/skills/examples/paint`; write outputs to your working directory.

1. **Write the scene** to a file in your working directory:

   ```bash
   cat > scene.py <<'EOF'
   from paintkit import Canvas, hex_rgb

   def paint(cv: Canvas):
       cv.paper_texture(0.05)
       cv.wash(0, int(cv.h * 0.55), hex_rgb("#a7c4d8"), hex_rgb("#e8d7b8"),
               alpha=0.8, mottling=0.4)
       # ... more primitives, back to front
   EOF
   ```

2. **Render a quick preview:**

   ```bash
   python /mnt/skills/examples/paint/render.py scene.py -o preview.png --scale 0.5 --seed 1
   ```

3. **Look at it.** Call the `view` tool on `preview.png`. `bash_tool` returns
   only stdout, so without this step you never see what you drew.

4. **Critique and revise.** Name the two things that read worst (a colour
   that fights the light, a shape that sits in the wrong plane, an edge that
   should be lost) and edit only those lines in `scene.py`. Re-render and look
   again. Two or three rounds is usually enough.

5. **Render full size and deliver:**

   ```bash
   python /mnt/skills/examples/paint/render.py scene.py -o out.png --width 1600 --height 900 --seed 1
   ```

   Then call `present_files` on `out.png` and `scene.py`. The scene file is
   the editable source; keep it so "make the sky darker" is an edit, not a
   new painting.

## Keeping the transcript clean

Write and edit `scene.py` through `bash_tool` (heredoc, or a short
Python `-c` that rewrites the file). Do not paste scene source into the chat
as prose; a collapsed tool call is a few lines in the transcript.

## Painting well

Work back to front and light to dark. Reserve whites by leaving paper
unpainted or with a white `outline`; there is no white pigment. Two thin
`watercolor_blob` layers read better than one heavy `flat_shape`. Distance is
cool, low-contrast, wet, soft; foreground is warm, dark, dry, hard-edged. Use
`cv.rng` for any procedural placement so the scene stays seeded.

## Budget

The container has one CPU and a 300 s wall clock per call. A full 18-element
scene renders in about a second at 1600×900. Use `--scale 0.5` while
iterating.
