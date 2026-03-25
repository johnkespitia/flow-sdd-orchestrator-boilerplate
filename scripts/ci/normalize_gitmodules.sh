#!/usr/bin/env bash
set -euo pipefail

MODE="hydrate"
ROOT_DIR="$(pwd)"
root_set=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only)
      MODE="check"
      shift
      ;;
    --hydrate)
      MODE="hydrate"
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: normalize_gitmodules.sh [--check-only|--hydrate] [ROOT_DIR]

Options:
  --check-only  Validate submodule gitlinks are fetchable from their remotes, without rewriting or hydrating submodules.
  --hydrate     Rewrite .gitmodules URLs when needed and hydrate submodules (default).
USAGE
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
    *)
      if [[ "$root_set" -eq 1 ]]; then
        echo "Unexpected extra argument: $1" >&2
        exit 2
      fi
      ROOT_DIR="$1"
      root_set=1
      shift
      ;;
  esac
done

cd "$ROOT_DIR"

if [[ ! -f .gitmodules ]]; then
  echo "No .gitmodules found. Skipping normalization."
  exit 0
fi

configure_github_auth() {
  local token="${GH_PAT:-${GITHUB_TOKEN:-}}"
  local auth_base
  if [[ -z "$token" ]]; then
    echo "No GH_PAT/GITHUB_TOKEN provided. Continuing with existing git auth config."
    return 0
  fi
  auth_base="https://x-access-token:${token}@github.com/"
  local auth_header
  auth_header="$(printf 'x-access-token:%s' "$token" | base64 | tr -d '\n')"
  # Configure both local and global scopes because some CI submodule clone paths ignore local-only rules.
  for scope in --local --global; do
    git config "$scope" http.https://github.com/.extraheader "AUTHORIZATION: basic $auth_header"
    # Fallback for environments where extraheader is not propagated to submodule clone.
    git config "$scope" --unset-all "url.${auth_base}.insteadOf" >/dev/null 2>&1 || true
    git config "$scope" --add "url.${auth_base}.insteadOf" "https://github.com/"
    git config "$scope" --add "url.${auth_base}.insteadOf" "https://github.com"
    git config "$scope" --add "url.${auth_base}.insteadOf" "git@github.com:"
    git config "$scope" --add "url.${auth_base}.insteadOf" "ssh://git@github.com/"
  done
  export GIT_TERMINAL_PROMPT=0
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

if [[ "$MODE" == "hydrate" ]]; then
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
fi

resolve_submodule_fetch_url() {
  local url="$1"
  if [[ "$url" =~ ^\.\./([^/]+)(\.git)?$ ]]; then
    local repo_name="${BASH_REMATCH[1]}"
    echo "https://github.com/${origin_owner}/${repo_name}.git"
    return 0
  fi
  echo "$url"
}

fetch_commit_from_remote() {
  local remote_url="$1"
  local sha="$2"
  local tmpdir
  local fetch_output

  tmpdir="$(mktemp -d)"
  git -C "$tmpdir" init -q
  set +e
  fetch_output="$(git -C "$tmpdir" fetch -q --depth=1 "$remote_url" "$sha" 2>&1)"
  local rc=$?
  set -e
  rm -rf "$tmpdir"

  if [[ "$rc" -ne 0 ]]; then
    echo "$fetch_output"
    return 1
  fi
  return 0
}

verify_submodule_remote_gitlinks() {
  local failed=0

  while IFS= read -r line; do
    local key path name url sha resolved_url fetch_error

    key="${line%% *}"
    path="${line#* }"
    name="${key#submodule.}"
    name="${name%.path}"
    url="$(git config -f .gitmodules --get "submodule.${name}.url" || true)"

    if [[ -z "$path" || -z "$url" ]]; then
      continue
    fi

    sha="$(git ls-files -s -- "$path" | awk 'NR==1 {print $2}')"
    if [[ -z "$sha" ]]; then
      echo "No gitlink SHA recorded for submodule path: $path"
      failed=1
      continue
    fi

    resolved_url="$(resolve_submodule_fetch_url "$url")"

    if fetch_error="$(fetch_commit_from_remote "$resolved_url" "$sha")"; then
      echo "Verified gitlink for ${path}: ${sha}"
      continue
    fi

    echo "Submodule gitlink is not fetchable from remote."
    echo "  path: $path"
    echo "  remote: $resolved_url"
    echo "  sha: $sha"
    echo "  fetch error: ${fetch_error//$'\n'/ }"
    echo "  action: push the submodule commit (or update root gitlink to a pushed commit)."
    failed=1
  done < <(git config -f .gitmodules --get-regexp '^submodule\..*\.path$' || true)

  if [[ "$failed" -ne 0 ]]; then
    return 1
  fi
}

configure_github_auth
verify_submodule_remote_gitlinks

if [[ "$MODE" == "check" ]]; then
  echo "Gitmodules gitlink check complete."
  exit 0
fi

# Always initialize/update after potential rewrite.
git submodule update --init --recursive
verify_submodules_hydrated

echo "Gitmodules normalization complete."
