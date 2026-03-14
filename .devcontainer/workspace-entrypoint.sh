#!/usr/bin/env bash

set -euo pipefail

socket_path="/var/run/docker.sock"
workspace_user="${FLOW_WORKSPACE_USER:-vscode}"

if [ -S "$socket_path" ] && id "$workspace_user" >/dev/null 2>&1; then
    socket_gid="$(stat -c '%g' "$socket_path")"
    group_name="$(getent group "$socket_gid" | cut -d: -f1 || true)"

    if [ -z "$group_name" ]; then
        group_name="docker-host"
        groupadd -f -g "$socket_gid" "$group_name"
    fi

    usermod -aG "$group_name" "$workspace_user"
fi

exec "$@"
