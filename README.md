# wiggle — the claude.ai code-execution sandbox, reproduced

A faithful, rebuilt copy of **the VM that runs Claude's code execution** (claude.ai chat/cowork tool sandbox, internally codenamed `wiggle`): Ubuntu 24.04 in a Firecracker microVM with Anthropic's exact package set, tool stack, directory layout, and exec-environment contract.

Built from a complete filesystem export of a live sandbox (178,151 files, swept end-to-end) plus its recovered build recipe. **Sanitized: zero credentials, keys, cookies, or shell history inside.**

## What's in the box

- Ubuntu 24.04.2, 866 apt packages (exact versions pinned in `meta/dpkg-manifest.txt`)
- Python: 3.12 + uv stack — 114 pinned distributions (`meta/uv-manifest.txt`) — numpy/pandas/scikit-learn/matplotlib/scipy/jupyter, Pillow 12.1.1, opencv, playwright 1.56
- Node 22.22.2 + 21 pinned npm globals incl. `@anthropic-ai/mcpb`-era toolchain, sharp, puppeteer 23.11 + Chrome-headless-shell 131, playwright chromium-1194 (`/opt/pw-browsers`)
- Document stack: LibreOffice 24.2, TeX Live 2023, poppler 24.02, qpdf 11.9, ImageMagick 6, tesseract (eng+osd, public models byte-identical), ffmpeg, pandoc, wkhtmltopdf
- **40 Anthropic skills** at `/mnt/skills` (verbatim — the instruction playbooks Claude follows: docx/pptx/xlsx/pdf, deep-research, morning, skill-creator, mcp-builder, …)
- Anthropic's custom binaries: `extract-text` (Rust, document→text) and `magika` (public build) — the mount daemon `rclone-filestore` interface is documented in `meta/`
- Exact `/mnt` layout: `user-data/{uploads,outputs}`, `transcripts`, `tool_results`; exact exec-env contract (18 vars incl. `IS_SANDBOX=yes`) — see `meta/env-contract.md`

Known authentic quirks preserved: pandoc→PDF needs `fonts-lmodern` + `poppler-data` (missing in the original image too — that's a finding, not a bug), `LANG` unset, npm offline cache deliberately cleaned at build, two `rclone-filestore` builds coexist on the PATH.

## Use it

**Plain Docker (works immediately):**
```bash
docker build -t wiggle .        # uses Dockerfile.recovered (verified to build green)
docker run -it wiggle bash
```
**Prebuilt rootfs (fastest):** release asset `wiggle-rootfs-sanitized.tar.zst` (2.53 GB, sha256 in `meta/rootfs-sha256.txt`):
```bash
skopeo/umoci or simply: mkdir rootfs && tar --zstd -xf wiggle-rootfs-sanitized.tar.zst -C rootfs
# or import straight into Docker:
cat wiggle-rootfs-sanitized.tar.zst | zstd -d | docker import - wiggle:live
```

**e2b (same architecture as the original — Firecracker microVM + in-VM daemon):**
```bash
e2b template build -n wiggle -d Dockerfile.recovered   # tested with e2b SDK 1.7.0
```
then `Sandbox(template="wiggle")` — your agent sees Claude's sandbox: same binaries, same paths, same skills, same quirks. (The original's PID 1 `process_api` is replaced by e2b's `envd` — role-equivalent.)

**Modal / any Firecracker or container platform:** the Dockerfile is plain `ubuntu:24.04` + steps; nothing Anthropic-proprietary required.

## Notes

- The original mounts a per-conversation remote filesystem (custom rclone backend over Anthropic's Filestore API). Here `/mnt/user-data/*` are local dirs; the RPC contract is documented in `meta/filestore-api.md`.
- Not included (Anthropic-side by design): the in-VM supervisor binary, MITM egress CAs, the telemetry collector. Egress in production is an allowlist (PyPI/npm/GitHub/Ubuntu/Anthropic API) — configure in your platform.
- Verified (parity smoke-test of the imported live rootfs, Docker on Apple Silicon): 866/866 packages, LibreOffice 24.2.7.2, pandoc 3.1.3, magika 1.0.1, node 22.22.2, python 3.12.3 + full 114-dist stack (pandas/numpy/pdfplumber/pypdfium2/playwright/cv2 import OK), 21 npm globals, skills present, env contract intact. Two notes: `extract-text` SIGSEGVs only under Rosetta/qemu x86 emulation (ARM hosts) — fine on native x86-64; `/mnt/user-data/outputs` + `tool_results` are mount points that exist only when the (Anthropic-side) mounts are attached — `mkdir` them or use the Dockerfile, which creates them.

<!-- parity verified 2026-09-04: docker import of live rootfs -> 866 pkgs, all stacks OK -->

- Everything here was reconstructed from the container itself + public CVE data; see the write-up: [link to your post].

*Not affiliated with Anthropic. Reproduce freely.*
