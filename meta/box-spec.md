# Machine spec — what to configure when you run Wiggle

The image is the disk. To match Anthropic's sandbox, configure the VM around it like this:

| Setting | Value |
|---|---|
| vCPU | **1** |
| RAM | **3.9 GiB** (4,093,820 kB), no swap |
| `/dev/shm` | = full RAM (their images depend on it; see OOM caveat below) |
| Disk | 256 GiB rw ext4 (+ read-only layers for skills if you want the same layout) |
| Privilege | agent runs as **root**, 40 capabilities (`−CAP_SYS_RESOURCE`), no seccomp, no LSM, no PID namespace |
| Cgroups | all **unlimited** (they account per-session but enforce nothing) |
| Per-call budget | ~300 s |
| Kernel | any 6.x; they ship a custom 6.18 Firecracker build (not required) |
| Network | egress allowlist: PyPI, npm, GitHub, Ubuntu archives, Anthropic API (swap in your own LLM API host); they also TLS-inspect outbound — optional |

## Run it

```bash
# Docker
docker run -it --memory=3900m --memory-swap=3900m --cpus=1 --shm-size=3900m wiggle bash

# e2b / Modal / Firecracker hosts: vCPU=1, RAM≈3.9GiB, no swap
```

## Exec environment (inject these — this is what Claude's commands actually see)

```
IS_SANDBOX=yes  HOME=/root  PYTHONUNBUFFERED=1  DEBIAN_FRONTEND=noninteractive
PATH=/home/claude/.npm-global/bin:/usr/local/bin:...   # note: HOME=/root but PATH leads /home/claude — intentional
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
NODE_PATH=/usr/local/lib/node_modules_global
PIP_ROOT_USER_ACTION=ignore
# LANG intentionally unset; CA bundle vars point at the system store
```
Full list + rationale: `meta/env-contract.md`

## Known gotchas (all authentic — present in the original)
- `pandoc x.md -o x.pdf` fails out of the box (needs `lmodern.sty` / a fallback engine) — see README
- ImageMagick: no SVG coder, webp ignores `-quality` — use Pillow/sharp
- `pip install` blocked by PEP 668 — use `uv` (offline cache included)
- Never trust tool exit codes in this image — verify artifacts (`test -s out && file out`); full rule list: `meta/` + the 38-rule playbook in the accompanying writeup
- Big writes to `/dev/shm`-adjacent paths can OOM a 3.9 GiB box if you also set shm to full RAM (Anthropic ships exactly this hazard; lower `--shm-size` to ~1 GiB if you don't need it)
