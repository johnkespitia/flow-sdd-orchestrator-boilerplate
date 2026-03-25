from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional


def git_scope(repo_path: Path) -> tuple[Optional[Path], Optional[str], Optional[str]]:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "git rev-parse fallo"
        return None, None, stderr

    git_root = Path(result.stdout.strip()).resolve()
    resolved_repo = repo_path.resolve()
    if resolved_repo == git_root:
        return git_root, None, None

    try:
        prefix = resolved_repo.relative_to(git_root).as_posix()
    except ValueError:
        return resolved_repo, None, None
    return git_root, prefix, None


def normalize_scoped_git_paths(paths: list[str], prefix: Optional[str]) -> list[str]:
    if not prefix:
        return sorted(path.strip("/") for path in paths if path.strip("/"))

    normalized: list[str] = []
    prefix_with_sep = f"{prefix}/"
    for path in paths:
        candidate = path.strip().strip("/")
        if not candidate:
            continue
        if candidate == prefix:
            continue
        if candidate.startswith(prefix_with_sep):
            candidate = candidate[len(prefix_with_sep) :]
        else:
            continue
        candidate = candidate.strip("/")
        if candidate:
            normalized.append(candidate)
    return sorted(dict.fromkeys(normalized))


def git_diff_name_only(repo_path: Path, base: Optional[str] = None, head: Optional[str] = None) -> tuple[list[str], Optional[str]]:
    git_root, prefix, scope_error = git_scope(repo_path)
    if scope_error or git_root is None:
        return [], scope_error or "No pude resolver el root de Git."

    command = ["git", "-C", str(git_root), "diff", "--name-only"]
    if base and head:
        command.append(f"{base}...{head}")
    elif base:
        command.append(f"{base}...HEAD")
    elif head:
        command.extend([head])
    if prefix:
        command.extend(["--", prefix])

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "git diff fallo"
        return [], stderr

    changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return normalize_scoped_git_paths(changed, prefix), None


def git_changed_files(repo_path: Path) -> tuple[list[str], Optional[str]]:
    git_root, prefix, scope_error = git_scope(repo_path)
    if scope_error or git_root is None:
        return [], scope_error or "No pude resolver el root de Git."

    result = subprocess.run(
        ["git", "-C", str(git_root), "status", "--porcelain", *(["--", prefix] if prefix else [])],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "git status fallo"
        return [], stderr

    changed: set[str] = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        raw_path = line[3:].strip()
        path = raw_path.split(" -> ", 1)[-1].strip()
        if path:
            absolute = git_root / path
            if absolute.is_dir():
                for nested in absolute.rglob("*"):
                    if nested.is_file():
                        try:
                            changed.add(nested.relative_to(git_root).as_posix())
                        except ValueError:
                            continue
                continue
            changed.add(path)

    return normalize_scoped_git_paths(sorted(changed), prefix), None


def repo_paths_changed_under_roots(repo: str, changed_files: list[str], *, contract_roots: dict[str, set[str]]) -> list[str]:
    roots = contract_roots.get(repo, set())
    selected: list[str] = []
    normalized_roots = [str(root).strip("/").replace("\\", "/") for root in roots if str(root).strip("/")]
    for changed_file in changed_files:
        normalized_file = str(changed_file).strip("/").replace("\\", "/")
        if not normalized_file:
            continue
        if any(
            normalized_file == root or normalized_file.startswith(f"{root}/")
            for root in normalized_roots
        ):
            selected.append(changed_file)
    return selected


def git_output(command: list[str], *, cwd: Optional[Path] = None, root: Path) -> tuple[int, str, str]:
    result = subprocess.run(command, cwd=cwd or root, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def repo_head_sha(repo: str, *, repo_root: Callable[[str], Path]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root(repo)), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"No pude resolver el SHA actual de `{repo}`.")
    return result.stdout.strip()
