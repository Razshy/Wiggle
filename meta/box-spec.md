# Machine spec

The image is the disk. To match Anthropic's sandbox, configure the VM around
it like this:

| Setting | Value |
|---|---|
| vCPU | 1 |
| RAM | 3.9 GiB (4,093,820 kB), no swap |
| `/dev/shm` | their images assume it equals full RAM; see the OOM note below |
| Disk | 256 GiB rw ext4, plus read-only layers for skills if you want the layout |
| Privilege | commands run as root, 40 capabilities (`-CAP_SYS_RESOURCE`), no seccomp, no LSM, no PID namespace |
| Cgroups | all unlimited. They account per session but enforce nothing |
| Per-call budget | about 300 seconds |
| Kernel | any 6.x. They ship a custom 6.18 Firecracker build; not required |
| Network | egress allowlist: PyPI, npm, GitHub, Ubuntu archives, Anthropic API (swap in your own LLM host). They also TLS-inspect outbound; optional |

## Run it

```bash
# Docker
docker run -it --memory=3900m --memory-swap=3900m --cpus=1 --shm-size=3900m wiggle bash

# e2b / Modal / Firecracker hosts: vCPU=1, RAM about 3.9 GiB, no swap
```

## Exec environment

Inject these. This is what Claude's commands actually see.

```
IS_SANDBOX=yes  HOME=/root  PYTHONUNBUFFERED=1  DEBIAN_FRONTEND=noninteractive
PATH=/home/claude/.npm-global/bin:/usr/local/bin:...
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
NODE_PATH=/usr/local/lib/node_modules_global
PIP_ROOT_USER_ACTION=ignore
```

Two intentional oddities: `HOME` is `/root` but `PATH` leads with
`/home/claude`, and `LANG` is left unset. Full list with rationale:
`meta/env-contract.md`.

## Gotchas (all present in the original)

- `pandoc x.md -o x.pdf` fails until you add `fonts-lmodern` or use a
  fallback engine. See the README.
- ImageMagick has no SVG coder and ignores `-quality` on webp. Use Pillow or
  sharp.
- `pip install` is blocked by PEP 668. Use `uv`. The offline cache is included.
- Do not trust tool exit codes. Verify the artifact (`test -s out && file out`).
- `/dev/shm` at full RAM is a hazard on a 3.9 GiB box under heavy writes.
  Anthropic ships it that way. Drop `--shm-size` to about 1 GiB if you do not
  need the big one.
