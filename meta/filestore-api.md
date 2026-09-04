# Filestore API (what the mount daemon speaks)

Recovered from the `rclone-filestore` binary (Go, custom build; symbols recovered via pclntab parse):

- Backend: `https://api.anthropic.com` — custom RPC paths under `v1/filestore/fs/*`:
  `listDirectory`, `createFile`, `readMetadata`, `readFile`, `writeFile`, `deleteFile`, `moveFile` (per-mount JWT via `Authorization: Bearer`, injected out-of-band — **never present in the on-disk mount JSON**)
- Mount config: `/tmp/rclone-mount-config.json` — `{mounts[]{source,destination,filesystem_id,readonly,file_perms,dir_perms,uid:999,gid:1000,vfs_cache_mode:"full",vfs_cache_max_size:"1G",cache_duration_s:1|3|10|3600}, service_url, state_dir, ready_file}` (session ids redacted in this copy)
- Semantics that differ from POSIX (verified): `fsync` = no network flush (upload deferred ~5–6 s); `chmod`/`xattr`/symlinks = no-ops; locks never reach the server; every write uploads `overwriteExisting:true`; dir-cache TTL per mount (3600 s on outputs).
- Reproduction note: local dirs stand in for the mounts; to fake the backend, the RPC set above + JSON responses is a ~200-line stub server.
