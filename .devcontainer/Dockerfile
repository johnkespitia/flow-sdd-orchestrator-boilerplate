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

# ── pnpm ─────────────────────────────────────────────────────────────
RUN npm install -g pnpm

# ── Tessl CLI ────────────────────────────────────────────────────────
# npm method works best inside containers (native curl installer
# targets ~/.local/bin which complicates multi-user setups)
RUN npm install -g @tessl/cli

# ── BMAD CLI ─────────────────────────────────────────────────────────
RUN npm install -g bmad-method

# ── Gateway deps ─────────────────────────────────────────────────────
RUN python3 -m pip install --no-cache-dir fastapi uvicorn httpx python-multipart

COPY workspace-entrypoint.sh /usr/local/share/flow/workspace-entrypoint.sh
RUN chmod +x /usr/local/share/flow/workspace-entrypoint.sh
