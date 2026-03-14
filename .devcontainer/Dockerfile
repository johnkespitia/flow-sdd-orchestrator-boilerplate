FROM mcr.microsoft.com/devcontainers/base:1-ubuntu-22.04

# ── PHP 8.2 CLI + extensions necesarias para Laravel 11 ──────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends software-properties-common \
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
