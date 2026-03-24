#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-$(pwd)}"
cd "$ROOT_DIR"

if [[ ! -f .gitmodules ]]; then
  echo "No .gitmodules found. Skipping normalization."
  exit 0
fi

configure_github_auth() {
  local token="${GH_PAT:-${GITHUB_TOKEN:-}}"
  if [[ -z "$token" ]]; then
    echo "No GH_PAT/GITHUB_TOKEN provided. Continuing with existing git auth config."
    return 0
  fi
  local auth_header
  auth_header="$(printf 'x-access-token:%s' "$token" | base64 | tr -d '\n')"
  git config --local http.https://github.com/.extraheader "AUTHORIZATION: basic $auth_header"
  # Fallback for environments where extraheader is not propagated to submodule clone.
  git config --local url."https://x-access-token:${token}@github.com/".insteadOf "https://github.com/"
  git config --local url."https://x-access-token:${token}@github.com/".insteadOf "git@github.com:"
  git config --local url."https://x-access-token:${token}@github.com/".insteadOf "ssh://git@github.com/"
  echo "Configured GitHub auth for submodule operations (extraheader + url.insteadOf)."
}

verify_submodules_hydrated() {
  local failed=0
  while IFS= read -r line; do
    local key path
    key="${line%% *}"
    path="${line#* }"
    if [[ -z "$path" ]]; then
      continue
    fi
    if [[ ! -d "$path" ]]; then
      echo "Submodule path missing after update: $path"
      failed=1
      continue
    fi
    if ! git -C "$path" rev-parse --verify HEAD >/dev/null 2>&1; then
      echo "Submodule not hydrated correctly (no HEAD): $path"
      failed=1
    fi
  done < <(git config -f .gitmodules --get-regexp '^submodule\..*\.path$' || true)
  if [[ "$failed" -ne 0 ]]; then
    echo "Submodule hydration failed. Check token permissions and .gitmodules URLs."
    return 1
  fi
}

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

configure_github_auth

# Always initialize/update after potential rewrite.
git submodule update --init --recursive
verify_submodules_hydrated

echo "Gitmodules normalization complete."
