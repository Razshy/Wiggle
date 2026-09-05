# The exec-environment contract

What every command Claude runs receives, injected by the supervisor at
handoff. Reproduce it and behavior matches production. Companion docs:
[box-spec.md](box-spec.md) (VM settings),
[filestore-api.md](filestore-api.md) (the mount backend),
[../README.md](../README.md).

```
DEBIAN_FRONTEND=noninteractive
HOME=/root
IS_SANDBOX=yes
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
LANG=<absent on purpose>
NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
NODE_PATH=/usr/local/lib/node_modules_global
NPM_CONFIG_USERCONFIG=/root/.npmrc
PATH=/home/claude/.npm-global/bin:/usr/local/bin:...
PIP_CACHE_DIR=<set>
PIP_CONFIG_FILE=<set>
PIP_ROOT_USER_ACTION=ignore
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
PYTHONUNBUFFERED=1
REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
TERM=<set>
SBX_TELEMETRY_SOCKET=<set on current builds>
```

Three things worth knowing, all authentic:

- `HOME` is `/root` but `PATH` leads with `/home/claude`. The mismatch is
  real and causes the Playwright/browser path quirks people hit.
- `NPM_CONFIG_USERCONFIG` points at `/root/.npmrc` and `PIP_CONFIG_FILE` at
  `/root/.config/pip/pip.conf` — and neither file exists in the image
  (verified against the export). Correct paths, absent targets: prefix and
  index settings silently fall back to defaults. Original quirk, kept.
- The capture also includes `RUST_BACKTRACE=1`, `OLDPWD=/` and `PWD=…`
  (19 vars total; the PWD pair is per-invocation, not contract content).
  `SBX_TELEMETRY_SOCKET` is NOT in the Sept-1 capture — it arrived on later
  builds; it is provider-injected here, never assumed.
- `LANG` is deliberately unset, which is why some tools behave as pure ASCII.

Notes:

- The three CA variables point at a 150-cert bundle: 146 stock plus 4
  Anthropic egress-inspection roots (two generations, prod and staging). In
  this reproduction they just trust the normal system store.
- Privilege: commands run as uid 0, `CapEff` is all capabilities minus
  `CAP_SYS_RESOURCE`, `Seccomp` is 0, shared PID namespace, no LSM. This is
  by design; Anthropic treats root here as confined to the single-tenant VM.
- Resources: 1 vCPU, 3.9 GiB RAM with a host balloon as the real limiter, no
  swap, no `pids.max`, and a per-call budget of about 300 seconds.
- `/etc/sandbox-release` in this image carries the `IS_SANDBOX` marker so a
  script can detect it is in the sandbox.
