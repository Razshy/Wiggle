# =============================================================================
# p0-7-Dockerfile — executable parity reconstruction of Anthropic's
# claude-code sandbox image ("container_01QJ16vmsgBTwzVoBf5YMxqf--wiggle--c916be").
#
# Evidence sources (all under /Users/kendallbooker/Downloads/container-exact):
#   var/log/apt/history.log          100 apt transactions; the 5 tool-layer ones
#                                    2026-04-18 18:07:16 -> 18:12:26 replayed verbatim
#   var/log/dpkg.log                 final installed set = 866 pkgs (base 92 + tool 774)
#   var/log/bootstrap.log            debootstrap noble 2026-04-10, mirror ftpmaster.internal
#   etc/cloud/build.info             build_name: ubuntu-oci:minimized / serial 20260410
#   home/claude/.npm/_logs/2026-04-18T18_12_33_085Z-debug-0.log
#                                    npm@10.9.7 / node v22.22.2 -g argv + registry traffic
#   home/claude/.npm-global/...      21 top-level npm pkgs resolved (pinned below)
#   usr/local/lib/python3.12/dist-packages/*.dist-info
#                                    114 uv-installed dists -> pinned uv stack below
#   home/claude/.config/uv/uv-receipt.json
#                                    uv 0.11.7, cargo-dist installer, ~/.local/bin
#   usr/local/bin                    3 custom ELF binaries + ~60 python console scripts
#   etc/{hosts,machine-id,puppeteer-config.json}, usr/local/share/ca-certificates
#
# Drift note: built 2026-09 against live mirrors, not the April snapshot, so
# point-versions drift; see p0-7-build.md for the quantified delta.
# =============================================================================

FROM --platform=linux/amd64 ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# ---- Layer 0: base parity -----------------------------------------------------
# Their base: debootstrap of noble serial 20260410 from ftpmaster.internal,
# then `dist-upgrade` + `install unminimize` (history.log lines 457-466).
# ubuntu:24.04:latest today is a newer serial -> acknowledged drift, unfixable
# without a digest pin.
COPY etc/cloud/build.info /etc/cloud/build.info

# ---- Layer 1: CA bundle staged + their txn 1 (curl ca-certificates) -----------
# Their 4 internal CAs are present before any update-ca-certificates run
# (usr/local/share/ca-certificates/*.crt, dropped 18:07 during build, imported
# at the 18:13 CA step). Fresh `apt-get update` first: their image had lists from
# the 20260410 base build; a 2026-09 rebuild must refresh against live mirrors.
COPY usr/local/share/ca-certificates/ /usr/local/share/ca-certificates/
RUN apt-get update

# (a) 18:07:16 -> 18:07:19  (17 pkgs; curl 8.5.0-2ubuntu10.8, ca-certs 20240203)
RUN apt-get install -y --no-install-recommends curl ca-certificates \
 && update-ca-certificates
# (b) 18:07:51 -> 18:07:52  (17 pkgs; gnupg 2.4.4-2ubuntu17.4, apt-transport-https 2.8.3)
RUN apt install -y apt-transport-https ca-certificates curl gnupg

# ---- Layer 2: nodesource repo (between txns 2 and 3; txn 3 pulls nodejs 22.x) --
# tx #3 installed nodejs 22.22.2-1nodesource1 from this repo; gpg+curl exist by now.
RUN mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /usr/share/keyrings/nodesource.gpg
COPY etc/apt/sources.list.d/nodesource.sources /etc/apt/sources.list.d/nodesource.sources
RUN apt-get update

# (c) 18:07:57 -> 18:08:00  (12 pkgs; nodejs 22.22.2-1nodesource1)
RUN apt-get install -y nodejs
# (d) 18:08:56 -> 18:10:53  (604 pkgs; texlive/libreoffice/ffmpeg/fonts/build stack)
RUN apt-get install -y --no-install-recommends wget fuse3 gnupg2 software-properties-common git graphviz build-essential zip unzip file bc netcat-openbsd libxml2-utils libnss3-tools p11-kit p11-kit-modules python3 python3-pip python3-dev python3-venv python3-wheel python3-uno pipx libcairo2-dev pkg-config libgl1 libglib2.0-0 default-jre-headless fonts-crosextra-carlito fonts-crosextra-caladea fonts-noto-cjk fonts-noto-cjk-extra fonts-dejavu fonts-liberation2 fonts-texgyre texlive-latex-base texlive-fonts-recommended texlive-latex-recommended texlive-xetex texlive-science texlive-pictures latexmk ffmpeg pandoc libreoffice-writer libreoffice-java-common ure-java poppler-utils qpdf imagemagick wkhtmltopdf tesseract-ocr tesseract-ocr-eng pdftk libreoffice-impress libreoffice-calc
# (e) 18:12:17 -> 18:12:26  (124 pkgs; headless-chromium runtime libs + xvfb + fonts)
RUN apt-get install -y --no-install-recommends libasound2t64 libatk-bridge2.0-0t64 libatk1.0-0t64 libatspi2.0-0t64 libcairo2 libcups2t64 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0t64 libnspr4 libnss3 libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 libcairo-gobject2 libfontconfig1 libfreetype6 libgdk-pixbuf-2.0-0 libgtk-3-0t64 libpangocairo-1.0-0 libx11-xcb1 libxcb-shm0 libxcursor1 libxi6 libxrender1 gstreamer1.0-libav gstreamer1.0-plugins-bad gstreamer1.0-plugins-base gstreamer1.0-plugins-good libicu74 libatomic1 libenchant-2-2 libepoxy0 libevent-2.1-7t64 libflite1 libgles2 libgstreamer-gl1.0-0 libgstreamer-plugins-bad1.0-0 libgstreamer-plugins-base1.0-0 libgstreamer1.0-0 libgtk-4-1 libharfbuzz-icu0 libharfbuzz0b libhyphen0 libjpeg-turbo8 liblcms2-2 libmanette-0.2-0 libopus0 libpng16-16t64 libsecret-1-0 libvpx9 libwayland-client0 libwayland-egl1 libwayland-server0 libwebp7 libwebpdemux2 libwoff1 libxml2 libxslt1.1 libx264-164 libavif16 xvfb fonts-noto-color-emoji fonts-unifont xfonts-cyrillic xfonts-scalable fonts-liberation fonts-ipafont-gothic fonts-wqy-zenhei fonts-tlwg-loma-otf fonts-freefont-ttf

# ---- Layer 4: the CA install step + dpkg trigger re-run (18:13:00/18:13:02) ----
# dpkg.log ends with two ca-certificates-java trigger passes at 18:13:00 and
# 18:13:02 — i.e. `update-ca-certificates` was run again after the java/p11-kit
# stack landed (their docker-entrypoint/CA-sync step). Re-run here for parity.
RUN update-ca-certificates && update-ca-certificates -f

# ---- Layer 5: uv toolchain + pinned Python stack -------------------------------
# uv 0.11.7 via cargo-dist installer into /home/claude/.local/bin (uv-receipt.json).
# 114 dists into /usr/local/lib/python3.12/dist-packages with `/usr/bin/python`
# resolved to /usr/bin/python3 (their shebangs are all #!/usr/bin/python) using
# uv pip install --system (INSTALLER=uv on all 114 dist-infos).
# Their index was https://artifactory.infra.ant.dev/artifactory/api/pypi/pypi-all
# (internal mirror of PyPI) -> public PyPI used here; pins are the dist-info versions.
RUN useradd -m -u 999 -s /bin/bash claude
COPY _context/uv_requirements.txt /tmp/uv_requirements.txt
USER claude
RUN curl -LsSf https://astral.sh/uv/0.11.7/install.sh | sh
ENV PATH="/home/claude/.local/bin:${PATH}"
USER root
# their /usr/bin/python -> python3 symlink is hand-made (no python-is-python3 pkg
# in dpkg.log); EXTERNALLY-MANAGED marker still present in snapshot -> they used
# --break-system-packages against the system interpreter.
RUN ln -sf /usr/bin/python3 /usr/bin/python \
 && uv pip install --python /usr/bin/python3 --system --break-system-packages -r /tmp/uv_requirements.txt

# ---- Layer 6: Node global prefix + pinned npm stack ----------------------------
# `npm i -g` as claude with prefix=/home/claude/.npm-global (home/claude/.npmrc).
# Log argv (2026-04-18T18:12:33.085Z, npm@10.9.7 / node v22.22.2):
#   install --global graphviz @mermaid-js/mermaid-cli markdownlint-cli
#     markdownlint-cli2 marked markdown-pdf markdown-toc remark-cli
#     remark-preset-lint-recommended playwright@1.56.0 typescript tsx ts-node
#     docx pdf-lib pdfjs-dist pptxgenjs react react-dom react-icons sharp
# Versions below are the RESOLVED versions read from
# home/claude/.npm-global/lib/node_modules/*/package.json (April 18).
COPY _context/npmrc /home/claude/.npmrc
USER claude
RUN npm install --global \
      graphviz@0.0.9 \
      @mermaid-js/mermaid-cli@11.12.0 \
      markdownlint-cli@0.48.0 \
      markdownlint-cli2@0.22.0 \
      marked@18.0.2 \
      markdown-pdf@11.0.0 \
      markdown-toc@1.2.0 \
      remark-cli@12.0.1 \
      remark-preset-lint-recommended@7.0.1 \
      playwright@1.56.0 \
      typescript@6.0.3 \
      tsx@4.21.0 \
      ts-node@10.9.2 \
      docx@9.6.1 \
      pdf-lib@1.17.1 \
      pdfjs-dist@5.6.205 \
      pptxgenjs@4.0.1 \
      react@19.2.5 \
      react-dom@19.2.5 \
      react-icons@5.6.0 \
      sharp@0.34.5
USER root

# ---- Layer 7: Playwright browsers, pinned to build 1194 -------------------------
# opt/pw-browsers: chromium-1194, chromium_headless_shell-1194, ffmpeg-1011
# (PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers, from .npmrc/env).
# playwright@1.56.0 normally wants chromium-1200; their image force-installed the
# 1194 set -> same force here via PUPPETEER/PLAYWRIGHT env-free explicit install.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    PATH="/home/claude/.local/bin:/home/claude/.npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
RUN mkdir -p /opt/pw-browsers && chown claude:claude /opt/pw-browsers
USER claude
RUN playwright install chromium \
 && mkdir -p /opt/pw-browsers/chromium-1194 /opt/pw-browsers/chromium_headless_shell-1194 \
 && ( playwright install chromium@1194 chromium_headless_shell@1194 2>/dev/null \
      || echo 'WARN: pinned chromium-1194 revision not installable via playwright 1.56.0 CLI; default revision kept (see p0-7-build.md drift)' ) \
 && ls -la /opt/pw-browsers
USER root
# Also their puppeteer cache (Chrome 131.0.6778.204, used by markdown-pdf &
# mermaid-cli via puppeteer-config.json):
RUN chown -R claude:claude /home/claude/.cache || true

# ---- Layer 8: the 3 custom ELF binaries -----------------------------------------
# All x86-64 ELF, dropped in at 11:11-11:13 build time (not from apt/pip/npm):
#   extract-text     2.0 MB  stripped   (Rust text-extraction CLI)
#   magika            32 MB  unstripped (Google magika standalone; pip magika 0.6.3 also present)
#   rclone-filestore 29 MB   stripped   (Anthropic rclone fork; twin at /opt/rclone/)
COPY _context/bin/extract-text     /usr/local/bin/extract-text
COPY _context/bin/magika           /usr/local/bin/magika
COPY _context/bin/rclone-filestore /usr/local/bin/rclone-filestore
COPY _context/opt/rclone/rclone-filestore /opt/rclone/rclone-filestore
RUN chmod 755 /usr/local/bin/extract-text /usr/local/bin/magika /usr/local/bin/rclone-filestore \
 && mkdir -p /opt/rclone-attach

# ---- Layer 9: /etc edits ---------------------------------------------------------
# hosts: api.anthropic.com pinned to 160.79.104.10; runsc + vm blackholed to
# localhost (gVisor sandbox + metadata-service isolation).
COPY etc/hosts /etc/hosts
COPY etc/machine-id /etc/machine-id
COPY etc/puppeteer-config.json /etc/puppeteer-config.json

# ---- Layer 10: user/env finalization ---------------------------------------------
# /home/claude/.local/bin on PATH (uv installer modify_path=true)
RUN printf '%s\n' \
      'export PATH="/home/claude/.local/bin:/home/claude/.npm-global/bin:/usr/local/bin:${PATH}"' \
      'export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers' \
      'export PUPPETEER_CONFIG=/etc/puppeteer-config.json' \
      'export NODE_PATH=/home/claude/.npm-global/lib/node_modules' \
      > /etc/profile.d/claude-sandbox.sh \
 && chmod 644 /etc/profile.d/claude-sandbox.sh

ENV PATH="/home/claude/.local/bin:/home/claude/.npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    PUPPETEER_CONFIG=/etc/puppeteer-config.json \
    NODE_PATH=/home/claude/.npm-global/lib/node_modules

WORKDIR /home/claude
CMD ["/bin/bash"]

# --- additions for standalone use (original mounted these via squashfs) ---
COPY mnt-skills/ /mnt/skills/
RUN mkdir -p /mnt/user-data/uploads /mnt/user-data/outputs /mnt/transcripts /mnt/user-data/tool_results /tmp/rclone-mounts \
 && (id claude 2>/dev/null || groupadd -g 1001 claude; useradd -m -u 999 -g 1001 claude || true) \
 && printf 'IS_SANDBOX=yes\n' > /etc/sandbox-release
