#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-$(pwd)}"
cd "$ROOT_DIR"

if [[ ! -f .gitmodules ]]; then
  echo "No .gitmodules found. Skipping normalization."
  exit 0
fi

origin_url="$(git config --get remote.origin.url || true)"
if [[ -z "$origin_url" ]]; then
  echo "No remote.origin.url found. Skipping normalization."
  exit 0
fi

extract_owner_repo() {
  local url="$1"
  local cleaned
  local slug

  cleaned="$url"
  cleaned="${cleaned%.git}"

  if [[ "$cleaned" =~ ^git@github\.com:([^/]+)/([^/]+)$ ]]; then
    echo "${BASH_REMATCH[1]} ${BASH_REMATCH[2]}"
    return 0
  fi

  if [[ "$cleaned" =~ ^https://github\.com/([^/]+)/([^/]+)$ ]]; then
    echo "${BASH_REMATCH[1]} ${BASH_REMATCH[2]}"
    return 0
  fi

  if [[ "$cleaned" =~ ^\.\./([^/]+)$ ]]; then
    echo "RELATIVE ${BASH_REMATCH[1]}"
    return 0
  fi

  return 1
}

if ! origin_parts="$(extract_owner_repo "$origin_url")"; then
  echo "Origin is not a supported GitHub URL: $origin_url"
  exit 0
fi

origin_owner="${origin_parts%% *}"
changed=0

while IFS= read -r key; do
  current_url="$(git config -f .gitmodules --get "$key" || true)"
  if [[ -z "$current_url" ]]; then
    continue
  fi

  if ! submodule_parts="$(extract_owner_repo "$current_url")"; then
    continue
  fi

  submodule_owner="${submodule_parts%% *}"
  submodule_repo="${submodule_parts##* }"

  # Keep already-relative URLs untouched.
  if [[ "$submodule_owner" == "RELATIVE" ]]; then
    continue
  fi

  # Rewrite only when owner matches the root owner.
  if [[ "$submodule_owner" == "$origin_owner" ]]; then
    relative_url="../${submodule_repo}.git"
    if [[ "$current_url" != "$relative_url" ]]; then
      git config -f .gitmodules "$key" "$relative_url"
      echo "Rewrote $key: $current_url -> $relative_url"
      changed=1
    fi
  fi
done < <(git config -f .gitmodules --name-only --get-regexp '^submodule\..*\.url$' || true)

if [[ "$changed" -eq 1 ]]; then
  git submodule sync --recursive
fi

# Always initialize/update after potential rewrite.
git submodule update --init --recursive

echo "Gitmodules normalization complete."
