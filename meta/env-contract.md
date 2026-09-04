# The exec-environment contract (what every command Claude runs gets)

Injected by the supervisor at exec handoff. Reproduced here for reference / replication:

```
DEBIAN_FRONTEND=noninteractive
HOME=/root                       # note: PATH leads /home/claude/* — the HOME/PATH split is original
IS_SANDBOX=yes
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
LANG=<absent>                    # deliberate: causes documented ASCII behaviors
NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
NODE_PATH=/usr/local/lib/node_modules_global
NPM_CONFIG_USERCONFIG=/home/claude/.npmrc   # file exists but is NOT read (HOME=/root) — original quirk
PATH=/home/claude/.npm-global/bin:/usr/local/bin:...
PIP_CACHE_DIR=... PIP_CONFIG_FILE=... PIP_ROOT_USER_ACTION=ignore
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
PYTHONUNBUFFERED=1
REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
TERM=<set>
SBX_TELEMETRY_SOCKET=<set on current builds>   # telemetry ingest door (see filestore-api.md sibling note)
```

- The CA trio point at a 150-cert bundle = 146 stock + **4 Anthropic egress-inspection roots** (2 generations × prod/staging) — in this reproduction they simply trust the normal store.
- Privilege: commands run **uid 0**, `CapEff = all − CAP_SYS_RESOURCE`, `Seccomp: 0`, shared PID namespace, no LSM (by design, per Anthropic triage: root is confined to the single-tenant sandbox).
- Resources: 1 vCPU @2.1GHz, 3.9 GiB RAM (host balloon = real memory limiter), no swap, no `pids.max`; per-tool-call budget ~300 s.
- `/etc/sandbox-release` here carries the `IS_SANDBOX` marker for detection.
