# Getting the rootfs

Two ways, from fastest to most authentic.

## 1. Rebuilt image (recommended)

```bash
docker build -t wiggle .
```

The `Dockerfile` is the build recipe recovered from the container's own
package timestamps and logs. It replays the exact build (verified green).
Takes about 25 to 40 minutes and produces an image functionally equal to the
live sandbox, minus the Anthropic-only daemons. On e2b:
`e2b template build -n wiggle` (needs the e2b CLI and `E2B_API_KEY`).

## 2. Exact live rootfs (byte-level session export)

The GitHub release `v1.0-live-rootfs` carries the complete filesystem of a
live session, split in two for GitHub's 2 GiB asset limit:

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

## Sanitization

What was changed from the raw export. Nothing else was touched.

- `claude_chat_01EavkjP4hzEzMFe3KCQAVip` set to `claude_chat_REDACTED`
  (directory names and 5 files)
- cgroup session hashes `732b735e...` and `6c2653aa...` set to
  `cgroup_session_REDACTED`
- `container_01QJ16vmsgBTwzVoBf5YMxqf--wiggle--<hex>` set to
  `container_REDACTED--wiggle--REDACT`
- removed the root-level `container_info.json` (it held the session id)
- tar packaged with `--owner=0 --group=0 --numeric-owner --no-xattrs`, so
  macOS metadata and the local username are stripped
- verified clean: zero private keys, zero credentials, zero cookies, zero
  shell history, and no user files except `mnt/user-data/uploads/pdfcrowd.pdf`
  (the researcher's own test upload, kept on purpose)

The session-runtime strays (`home/claude/zip.log` and friends, `req/`,
`inspect/`, the `virtual-fs-snapshot/` folder) are kept. They are part of the
session, and they show what a live box actually accumulates.
