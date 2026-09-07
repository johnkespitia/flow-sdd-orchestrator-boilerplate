#!/usr/bin/env bash

set -euo pipefail

socket_path="/var/run/docker.sock"
workspace_user="${FLOW_WORKSPACE_USER:-vscode}"

prepare_runtime_user_dirs() {
    local workspace_home="$1"
    local target_uid="$2"
    local target_gid="$3"
    local runtime_dirs=(
        "$workspace_home/.local"
        "$workspace_home/.local/share"
        "$workspace_home/.local/share/tessl"
        "$workspace_home/.local/share/pnpm"
        "$workspace_home/.local/share/pnpm/store"
        "$workspace_home/.config"
        "$workspace_home/.cache"
    )

    mkdir -p "${runtime_dirs[@]}"
    chown "$target_uid:$target_gid" "${runtime_dirs[@]}"
}

if [ -S "$socket_path" ] && id "$workspace_user" >/dev/null 2>&1; then
    socket_gid="$(stat -c '%g' "$socket_path")"
    group_name="$(getent group "$socket_gid" | cut -d: -f1 || true)"

    if [ -z "$group_name" ]; then
        group_name="docker-host"
        groupadd -f -g "$socket_gid" "$group_name"
    fi

    usermod -aG "$group_name" "$workspace_user"
fi

if [ "$(id -u)" -eq 0 ] && [ "$workspace_user" != "root" ] && id "$workspace_user" >/dev/null 2>&1; then
    target_uid="$(id -u "$workspace_user")"
    target_gid="$(id -g "$workspace_user")"
    workspace_home="$(getent passwd "$workspace_user" | cut -d: -f6 || true)"
    if [ -z "$workspace_home" ]; then
        workspace_home="/home/$workspace_user"
    fi
    prepare_runtime_user_dirs "$workspace_home" "$target_uid" "$target_gid"
    exec setpriv --reuid="$target_uid" --regid="$target_gid" --init-groups -- "$@"
fi

exec "$@"
