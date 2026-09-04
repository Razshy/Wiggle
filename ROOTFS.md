# Getting the rootfs

Two ways, from fastest to most authentic:

## 1. Rebuilt image (recommended for most users)
```bash
docker build -t wiggle .
```
The `Dockerfile` is the build recipe recovered from the container's own package timestamps + logs — it replays Anthropic's exact build (verified green). ~25–40 min, produces an image functionally equal to the live sandbox (minus Anthropic-only daemons). On e2b: `e2b template build -n wiggle` (needs the e2b CLI + `E2B_API_KEY`).

## 2. Exact live rootfs (byte-level, session export)
The GitHub release `v1.0-live-rootfs` carries the **complete filesystem of a live session**, split in two (GitHub's 2 GiB asset cap):
```bash
# download wiggle-part-aa and wiggle-part-ab from the release, then:
cat wiggle-part-aa wiggle-part-ab > wiggle-rootfs-sanitized.tar.zst
echo '07ceb5b2af3ab7386bf212f6aaddee59d1d75798258de93ac1596126fb42aa91  wiggle-rootfs-sanitized.tar.zst' | sha256sum -c -

# as a plain directory tree:
mkdir rootfs && tar --zstd -xf wiggle-rootfs-sanitized.tar.zst -C rootfs

# or import directly as a Docker image:
zstd -d -c wiggle-rootfs-sanitized.tar.zst | docker import - wiggle:live
docker run --rm wiggle:live /usr/bin/soffice --version   # LibreOffice 24.2.7.2
```

## Sanitization (what was changed from the raw export — nothing else was touched)
- `claude_chat_01EavkjP4hzEzMFe3KCQAVip` → `claude_chat_REDACTED` (paths + 5 files)
- cgroup session hashes `732b735e…` / `6c2653aa…` → `cgroup_session_REDACTED`
- `container_01QJ16vmsgBTwzVoBf5YMxqf--wiggle--<hex>` → `container_REDACTED--wiggle--REDACT`
- removed: root-level `container_info.json` (session id)
- deleted: session-runtime strays only if you chose (current tarball **keeps** `home/claude/{bg-test,zip*.log,cp*.log,virtual-fs-snapshot/}`, `req/`, `inspect/` — they're part of the session story)
- tar packaged with `--owner=0 --group=0 --numeric-owner --no-xattrs` (macOS metadata/username stripped)
- **Independent verification: zero private keys, zero credentials, zero cookies, zero shell history, zero user files besides `mnt/user-data/uploads/pdfcrowd.pdf` (the researcher's own test upload — kept intentionally)**
