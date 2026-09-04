# Filestore API

What the mount daemon (`rclone-filestore`, a custom Go build) speaks.
Recovered from the binary's symbols. Included so you can build a stand-in
backend if you want the mounts to behave like production.

## Transport

- Backend base: an API host (production uses `https://api.anthropic.com`)
- Auth: per-mount JWT as `Authorization: Bearer <token>`
- The token is injected out of band. It is never present in the on-disk
  mount config.

## RPC surface (custom JSON paths under `v1/filestore/fs/`)

| Call | Purpose |
|---|---|
| `listDirectory` | list a folder |
| `createFile` | start/register an upload |
| `readMetadata` | stat a file |
| `readFile` | download |
| `writeFile` | upload content |
| `deleteFile` | remove |
| `moveFile` | move or rename |

## Mount config shape (`/tmp/rclone-mount-config.json`)

```json
{
  "service_url": "https://api.anthropic.com",
  "state_dir": "/tmp/rclone-mounts",
  "ready_file": "/tmp/rclone-mounts/ready",
  "mounts": [
    {
      "source": "/outputs",
      "destination": "/mnt/user-data/outputs",
      "filesystem_id": "claude_chat_<id>",
      "readonly": false,
      "file_perms": "0644", "dir_perms": "0755",
      "uid": 999, "gid": 1000,
      "vfs_cache_mode": "full", "vfs_cache_max_size": "1G",
      "cache_duration_s": 3600
    }
  ]
}
```

Four mounts ship: `uploads` (ro, 1 s cache), `tool_results` (ro, 3 s),
`transcripts` (ro, 10 s), `outputs` (rw, 3600 s).

## Semantics that differ from POSIX (all verified)

These are the surprising ones, and the reason a stub backend should mimic
them if you want true parity:

- `fsync` performs no network flush. Uploads are deferred about 5 to 6
  seconds. A kill inside that window loses the file.
- `chmod`, extended attributes, and symlinks are accepted but are no-ops.
- Locks never reach the server. Two VMs on one filesystem id can overwrite
  each other silently.
- Every write uploads with `overwriteExisting: true`.
- Reported file permissions are synthetic (constant per config), not real.

A faithful stand-in backend is roughly a small HTTP server implementing the
seven calls above plus the deferred-upload behavior. The read-only mounts can
also just be plain local directories for most agent use cases.
