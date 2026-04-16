FROM mcr.microsoft.com/devcontainers/base:1-ubuntu-22.04

# ── Docker CLI + Compose plugin para operar el stack desde workspace ───────
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg software-properties-common \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" > /etc/apt/sources.list.d/docker.list

# ── PHP 8.2 CLI + extensions necesarias para Laravel 11 ──────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        docker-ce-cli \
        docker-compose-plugin \
    && add-apt-repository ppa:ondrej/php -y \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        php8.2-cli \
        php8.2-curl \
        php8.2-mbstring \
        php8.2-xml \
        php8.2-zip \
        php8.2-mysql \
        php8.2-bcmath \
        golang-go \
        python3-pip \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# ── Composer ─────────────────────────────────────────────────────────
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# ── Node 20 LTS + npm ───────────────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── GitHub CLI (gh) ────────────────────────────────────────────────
# Se instala a nivel de imagen para que todas las replicas/workspaces
# generados desde este boilerplate lo tengan disponible.
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | gpg --dearmor -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# ── Toolchain versions ───────────────────────────────────────────────
# Defaults track latest upstream versions on image rebuild. Override these
# build args to pin reproducible versions for release/staging rollouts.
ARG PNPM_VERSION=latest
ARG TESSL_CLI_VERSION=latest
ARG BMAD_METHOD_VERSION=latest
ARG ENGRAM_VERSION=latest

# ── pnpm ─────────────────────────────────────────────────────────────
RUN npm install -g "pnpm@${PNPM_VERSION}"

# ── Tessl CLI ────────────────────────────────────────────────────────
# npm method works best inside containers (native curl installer
# targets ~/.local/bin which complicates multi-user setups)
RUN npm install -g "@tessl/cli@${TESSL_CLI_VERSION}" \
    && tessl --version

# ── BMAD CLI ─────────────────────────────────────────────────────────
RUN npm install -g "bmad-method@${BMAD_METHOD_VERSION}"

# ── Engram agent memory ──────────────────────────────────────────────
# Installed in the workspace image so memory tooling is reproducible and
# project-scoped through ENGRAM_DATA_DIR instead of sharing a host-global DB.
ARG INSTALL_ENGRAM=true
RUN if [ "$INSTALL_ENGRAM" = "true" ]; then \
      set -eux; \
      arch="$(dpkg --print-architecture)"; \
      case "$arch" in \
        amd64) asset_arch="amd64" ;; \
        arm64) asset_arch="arm64" ;; \
        *) echo "Unsupported Engram architecture: $arch" >&2; exit 1 ;; \
      esac; \
      release_url="https://api.github.com/repos/Gentleman-Programming/engram/releases/latest"; \
      if [ "$ENGRAM_VERSION" != "latest" ]; then \
        release_url="https://api.github.com/repos/Gentleman-Programming/engram/releases/tags/${ENGRAM_VERSION}"; \
      fi; \
      curl -fsSL "$release_url" -o /tmp/engram-release.json; \
      url="$(ENGRAM_ASSET_ARCH="$asset_arch" python3 -c 'import json, os; arch=os.environ["ENGRAM_ASSET_ARCH"]; data=json.load(open("/tmp/engram-release.json", encoding="utf-8")); aliases={arch, "x86_64" if arch=="amd64" else arch}; matches=[str(a.get("browser_download_url") or "") for a in data.get("assets", []) if "linux" in str(a.get("name") or "").lower() and any(alias in str(a.get("name") or "").lower() for alias in aliases) and (str(a.get("name") or "").lower().endswith(".tar.gz") or str(a.get("name") or "").lower().endswith(".tgz") or str(a.get("name") or "").lower().endswith(".zip"))]; print(matches[0] if matches else "")')"; \
      test -n "$url"; \
      mkdir -p /tmp/engram-extract; \
      curl -fsSL "$url" -o /tmp/engram-archive; \
      case "$url" in \
        *.zip) unzip -q /tmp/engram-archive -d /tmp/engram-extract ;; \
        *) tar -xzf /tmp/engram-archive -C /tmp/engram-extract ;; \
      esac; \
      find /tmp/engram-extract -type f -name engram -exec install -m 0755 {} /usr/local/bin/engram \; -quit; \
      test -x /usr/local/bin/engram; \
      engram version; \
      rm -rf /tmp/engram-release.json /tmp/engram-archive /tmp/engram-extract; \
    fi

# ── Python tooling del control plane y gateway ───────────────────────
RUN python3 -m pip install --no-cache-dir fastapi uvicorn httpx python-multipart pyyaml pytest

COPY workspace-entrypoint.sh /usr/local/share/flow/workspace-entrypoint.sh
RUN chmod +x /usr/local/share/flow/workspace-entrypoint.sh
