# Wiggle

A working copy of the sandbox that Claude (claude.ai) runs code in.

When Claude executes a command, reads a file, converts a document, or takes a
screenshot, it is not running on a web server. It is running inside a small
virtual machine, one per conversation. This repository is that machine: the
same files, tools, packages, and instructions, packaged so you can run it
yourself on Docker, e2b, Modal, or any Linux host.

Codename `wiggle` is what Anthropic calls this VM internally.

## Quick start

```bash
docker build -t wiggle .
docker run -it wiggle bash

# inside:
soffice --version            # LibreOffice 24.2
python3 -c "import pandas"   # full data science stack
ls /mnt/skills               # the 40 playbooks Claude follows
```

Want the exact bytes instead of a rebuild? The GitHub release carries the
full filesystem of a live session (8.9 GB, sanitized):

```bash
cat wiggle-part-aa wiggle-part-ab > wiggle.tar.zst
zstd -d -c wiggle.tar.zst | docker import - wiggle:live
```

## How it works

- Claude decides to run something and sends the command over a private
  channel to a supervisor process inside the VM.
- The supervisor starts the command with a fixed environment (see
  `meta/env-contract.md`) and streams the output back.
- The command runs as root with no seccomp and no user sandbox. Inside this
  VM, root is normal. The isolation that matters is the VM boundary itself.
- User files arrive as mounted folders under `/mnt/user-data`. In production
  those are remote storage; here they are plain directories.

Machine spec to match if you care about parity: 1 vCPU, 3.9 GiB RAM, no
swap. Details in `meta/box-spec.md`.

## What is inside

| Capability | What gives you that |
|---|---|
| Documents (docx, xlsx, pptx, pdf) | LibreOffice 24.2, pandoc, python-docx, openpyxl |
| OCR (make scans searchable) | tesseract 5 with English models, byte-identical to the public Google release |
| File-type detection | magika (Google model, public build) |
| Web automation and screenshots | Playwright 1.56 with a pinned Chromium at `/opt/pw-browsers`, plus puppeteer with Chrome-headless-shell |
| Diagrams and charts | mermaid-cli, matplotlib, graphviz |
| Numbers and data | pandas, numpy, scipy, scikit-learn, Jupyter |
| Typesetting and PDFs | TeX Live 2023, poppler, qpdf, ImageMagick, wkhtmltopdf |
| Media | ffmpeg |
| **The playbooks Claude follows** | `/mnt/skills`, 40 skills, verbatim |

The skills are the interesting part. They are plain Markdown instruction
files that Claude reads before doing certain jobs: how to fill a PDF form,
how to run deep research (including the sub-agent prompts), how to drive the
desktop with computer use, how to build a skill. Public ones cover office
documents and file reading; example ones cover deep-research, morning
briefings, painting, MCP server building, and more.

Two custom Anthropic binaries are included: `extract-text` (turns uploaded
documents into text, Rust) and the mount daemon interface (`rclone-filestore`,
Go, documented in `meta/filestore-api.md`).

## What is not included

Four things live outside the filesystem, so no dump could contain them:

- The supervisor binary itself (runs from RAM, never from disk).
- The model, which is remote by definition.
- Anthropic's egress firewall and its CA roots.
- The remote storage service behind `/mnt/user-data` (contract documented).

For e2b users: e2b's own daemon takes the supervisor's role, which is why
this image drops straight into an e2b template.

## Using it with your own agent

Any agent that can shell into a container can use this box exactly the way
Claude does: read the relevant `/mnt/skills/*/SKILL.md`, then run the tools
it names. Inject the environment from `meta/env-contract.md` and the
behavior matches production, quirks included.

## Known quirks (present in the original, kept on purpose)

- `pandoc x.md -o x.pdf` fails until you add `fonts-lmodern` or use the
  Chromium fallback. The real sandbox has the same hole.
- `pip install` is blocked by PEP 668. Use `uv`. The offline wheel cache is
  included.
- ImageMagick has no SVG coder and ignores `-quality` for webp. Use
  Pillow or sharp.
- Tool exit codes lie often. Verify outputs (`test -s out && file out`)
  instead of trusting success.
- `extract-text` segfaults under x86 emulation on ARM Macs. It is fine on
  native x86-64 hosts.

## Repository layout

```
Dockerfile          recovered build recipe (verified to build green)
_context/           build inputs: pinned manifests + the Anthropic binaries
mnt-skills/         the 40 skills, copied to /mnt/skills
meta/               manifests, env contract, filestore API, machine spec
ROOTFS.md           how to get the exact live filesystem dump
```

## License

The build recipe, scripts, and documentation in this repo are MIT (`LICENSE`).

Everything Anthropic-made is theirs, not MIT:

- The 40 skill files in `mnt-skills/` and the Anthropic binaries each carry
  Anthropic's own license (`NOTICE` and each `LICENSE.txt`), which does not
  clearly allow redistribution. They are here as captured research artifacts.
- If you would rather not ship them, delete `mnt-skills/` and remove the one
  `COPY mnt-skills/` line from the Dockerfile. The box still builds and runs;
  any user can re-obtain the skills by asking Claude to show them.

Not affiliated with Anthropic.
