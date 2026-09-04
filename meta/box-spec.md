# The box itself — full machine spec (VM + kernel + limits)

Everything measured from the capture (see `deep-scan` evidence: `RE/w3-5`, `RE/reqcapture`, `RE/syskernel`, `RE/p0-8`). The container image covers the *disk* half; the rest lives in the VM config your platform sets.

## Hypervisor / VM
- **Firecracker microVM** (ACPI OEMID `FIRECK`/`FCAT`, custom fork, in-house vsock module `1.0.2.0-k`)
- Boot: `init=/process_api rdinit` (supervisor in initramfs), `panic=1 reboot=k`, `console=ttyS0`, `nomodule`, `swiotlb=noforce`, `ipv6.disable=1`, `random.trust_cpu=1`
- **vCPU:** 1, pinned; **kernel boot prints "Sapphire Rapids" but CPUID family-6 model-207 = Emerald Rapids** (audit adjudication: EMR); full AVX-512 + AMX exposed; no cpufreq, no cpuidle driver (guest never idles its timing)
- **RAM: 3.9 GiB** (`MemTotal 4,093,820 kB`); no swap; zram created-not-enabled; zswap off; **memory limiter = host virtio-balloon** (bound + free-page-reporting armed; guest `DEFLATE_ON_OOM`)
- **Disk:** vda ext4 256 GiB rw, `data=writeback` + DISCARD live (host delta-sizing), `rotational=1` (mq-deadline), `read_ahead_kb=8192`; ext4 `resv_strict,resuid=65534` (in-house option) — ENOSPC under `/` by design; vdb/vdc/vdd = **read-only squashfs** (rclone binary, skills ×2) — `ro` at device feature-bit level
- `/dev/shm` tmpfs = 100% of RAM (the OOM-chain ingredient)
- Network: eth0 MTU **1400**, gw `192.0.2.1` (TEST-NET synthetic), MAC `02:fc:…`; DNS `8.8.8.8` (cleartext); IPv6 compiled out; ifb0/ifb1 pre-created (host htb shaping); zero netfilter userspace in guest
- PCI: 8 virtio devices (balloon, 4×blk, net, vsock, rng) — **no IOMMU/DMAR tables**, so DMA isolation = Firecracker GPA validation
- Clocksource `tsc` (constant 2.1 GHz, no DVFS); HZ=250; PSI configured-but-disabled default; IO_URING=y; USER_NS=y

## Kernel
- Live-session era: **`6.18.44-fc-v22`** → seen hot-updated to **`6.18.44-fc-v24`** within 24 h (`-fc` = Anthropic's Firecracker config-salt). `/sys/kernel/notes` still carries `6.1.102-1.182.amzn2023` = guest-image lineage tag.
- Kconfig highlights: `MODULES=n`, `DEVMEM=n`, `PROC_KCORE=n`, YAMA=n, AppArmor=n, `LOCK_DOWN_KERNEL_FORCE_INTEGRITY=y`, `BPF_UNPRIV_DEFAULT_OFF`, `RANDOMIZE_BASE=y` (but root sees kallsyms), `VIRTIO_VSOCKETS=y`

## Process/limits contract (what an exec'd command gets)
- **uid 0**, `CapEff = all − CAP_SYS_RESOURCE` (40 caps; bounding keeps MKNOD etc.), `Seccomp: 0`, `NoNewPrivs: 0`, no PID/cgroup ns, no LSM
- cgroups: **v1 hierarchy; every controller = unlimited** (`memory.limit_in_bytes = LLONG_MAX`, `cfs_quota = −1`); `pids.max` file absent (ceiling unknown; per-uid task limit ~15,952 inferred); per-session accounting tag `memory:/process_api/<32-hex>`
- No auditd; `/dev/kmsg` 0644 world-readable; `/proc/1/{exe,mem,ns/*}` — root-readable in the v22-era image, **EPERM by v24** (dumpability hardening observed mid-audit)
- Time budget per tool call: ~300 s (skill-side constant; enforcement lives in the supervisor)
- Egress: host-side allowlist (PyPI/npm/GitHub/Ubuntu archives/Anthropic API + a few) behind a transparent TLS-MITM with 4 baked Anthropic roots; `api.anthropic.com` pinned in `/etc/hosts` to `160.79.104.10`; no proxy env anywhere

## Reproducing the box (platform config = the missing half)
The Docker image gives you the exact disk. Add the machine config:

```bash
# Docker approximation:
docker run -it --memory=3900m --memory-swap=3900m --cpus=1 --shm-size=3900m \
  --env-file <(echo 'IS_SANDBOX=yes') wiggle:live bash
```
(or use the repo Dockerfile's env block; note e2b/Modal/Firecracker hosts: set vCPU=1, RAM≈3.9 GiB, no swap, 1400-MTU net or default; balloon ≈ their platform's job — Docker's `--memory` is the honest equivalent.)

What you *can't* reproduce without their stack: the custom `-fc` kernel build (any 6.1+/6.18 works), the `-k` vsock fork, the MITM CAs (stub your own), and `process_api` (e2b `envd` is the role-equivalent daemon).
