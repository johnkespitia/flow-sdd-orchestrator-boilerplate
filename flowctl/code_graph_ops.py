from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


RunCommand = Callable[..., subprocess.CompletedProcess[str]]

SUPPORTED_EXTENSIONS = {
    ".bash", ".c", ".cc", ".cpp", ".cs", ".cu", ".dart", ".ex", ".exs",
    ".f", ".f90", ".f95", ".go", ".groovy", ".h", ".hpp", ".java", ".jl",
    ".js", ".jsx", ".json", ".kt", ".kts", ".lua", ".luau", ".m", ".mm",
    ".php", ".ps1", ".py", ".rb", ".rs", ".scala", ".sh", ".sol", ".swift",
    ".ts", ".tsx", ".v", ".vh", ".zig",
}
IGNORED_DIRS = {
    ".git", ".flow", ".worktrees", ".venv", "__pycache__", "build", "dist",
    "node_modules", "vendor",
}
METADATA_FILE = ".softos-index.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _config(workspace_config: dict[str, object]) -> dict[str, str]:
    raw = workspace_config.get("code_graph")
    cfg = raw if isinstance(raw, dict) else {}
    return {
        "provider": str(cfg.get("provider") or "graphify"),
        "version": str(cfg.get("version") or "0.9.56"),
        "output_dir": str(cfg.get("output_dir") or "graphify-out").strip("/") or "graphify-out",
        "mode": str(cfg.get("mode") or "code-only"),
        "source_boundary": str(cfg.get("source_boundary") or "derived"),
    }


def _repos(workspace_config: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = workspace_config.get("repos")
    if not isinstance(raw, dict):
        return {}
    return {
        str(name): value
        for name, value in raw.items()
        if isinstance(value, dict)
    }


def _contained(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _repo_path(root: Path, repo_cfg: dict[str, object]) -> Path:
    raw = str(repo_cfg.get("path") or ".").strip()
    candidate = (root / raw).resolve()
    if not _contained(root, candidate):
        raise ValueError(f"repo path escapes workspace: {raw}")
    return candidate


def _nested_exclusions(
    repo_name: str,
    repo_path: Path,
    *,
    root: Path,
    repos: dict[str, dict[str, object]],
) -> list[str]:
    exclusions: list[str] = []
    for other_name, other_cfg in sorted(repos.items()):
        if other_name == repo_name:
            continue
        try:
            other_path = _repo_path(root, other_cfg)
            relative = other_path.relative_to(repo_path)
        except (OSError, ValueError):
            continue
        if relative.parts:
            exclusions.append(relative.as_posix())
    return exclusions


def _source_inventory(
    repo_path: Path,
    *,
    output_dir: str,
    exclusions: list[str],
) -> tuple[int, int, str]:
    latest_mtime_ns = 0
    entries: list[str] = []
    excluded_roots = {
        (repo_path / value).resolve()
        for value in exclusions
    }
    for current, dirs, files in os.walk(repo_path):
        current_path = Path(current)
        dirs[:] = [
            name
            for name in dirs
            if name not in IGNORED_DIRS
            and name != output_dir
            and (current_path / name).resolve() not in excluded_roots
        ]
        dirs.sort()
        for name in sorted(files):
            path = current_path / name
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            latest_mtime_ns = max(latest_mtime_ns, stat.st_mtime_ns)
            entries.append(
                f"{path.relative_to(repo_path).as_posix()}\0{stat.st_size}\0{stat.st_mtime_ns}"
            )
    fingerprint = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return len(entries), latest_mtime_ns, fingerprint


def _metadata_expected(
    repo_name: str,
    repo_cfg: dict[str, object],
    exclusions: list[str],
    config: dict[str, str],
    source_file_count: int,
    source_fingerprint: str,
) -> dict[str, object]:
    return {
        "repo": repo_name,
        "repo_path": str(repo_cfg.get("path") or "."),
        "exclusions": exclusions,
        "provider": config["provider"],
        "indexer_version": config["version"],
        "mode": config["mode"],
        "source_file_count": source_file_count,
        "source_fingerprint": source_fingerprint,
    }


def _graph_counts(graph_path: Path) -> tuple[int, int]:
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("graph.json must contain an object")
    nodes = payload.get("nodes")
    edges = payload.get("links", payload.get("edges"))
    return (
        len(nodes) if isinstance(nodes, list) else 0,
        len(edges) if isinstance(edges, list) else 0,
    )


def inspect_repo(
    repo_name: str,
    *,
    root: Path,
    workspace_config: dict[str, object],
) -> dict[str, object]:
    config = _config(workspace_config)
    repos = _repos(workspace_config)
    repo_cfg = repos.get(repo_name)
    if repo_cfg is None:
        return {
            "repo": repo_name,
            "status": "error",
            "error": {"code": "unknown_repo", "message": "Repo is not registered in workspace.config.json."},
        }
    try:
        repo_path = _repo_path(root, repo_cfg)
    except ValueError as exc:
        return {
            "repo": repo_name,
            "status": "error",
            "error": {"code": "invalid_repo_path", "message": str(exc)},
        }
    output_path = repo_path / config["output_dir"]
    graph_path = output_path / "graph.json"
    manifest_path = output_path / "manifest.json"
    metadata_path = output_path / METADATA_FILE
    exclusions = _nested_exclusions(repo_name, repo_path, root=root, repos=repos)
    base: dict[str, object] = {
        "repo": repo_name,
        "kind": str(repo_cfg.get("kind") or "implementation"),
        "path": str(repo_path),
        "output_dir": str(output_path),
        "graph_path": str(graph_path),
        "manifest_path": str(manifest_path),
        "exclusions": exclusions,
        "source_boundary": config["source_boundary"],
    }
    if not repo_path.is_dir():
        return {
            **base,
            "status": "error",
            "error": {"code": "repo_path_missing", "message": "Registered repo directory is unavailable."},
        }

    source_count, latest_source_mtime_ns, source_fingerprint = _source_inventory(
        repo_path,
        output_dir=config["output_dir"],
        exclusions=exclusions,
    )
    base["source_file_count"] = source_count
    base["source_fingerprint"] = source_fingerprint
    if source_count == 0:
        return {
            **base,
            "status": "unsupported",
            "warning": "No Graphify-supported source files were found.",
        }
    if not graph_path.is_file():
        return {**base, "status": "missing"}

    try:
        node_count, edge_count = _graph_counts(graph_path)
        graph_mtime_ns = graph_path.stat().st_mtime_ns
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
        if not isinstance(metadata, dict):
            metadata = {}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            **base,
            "status": "error",
            "error": {"code": "invalid_index", "message": str(exc)},
        }

    expected = _metadata_expected(
        repo_name,
        repo_cfg,
        exclusions,
        config,
        source_count,
        source_fingerprint,
    )
    config_current = all(metadata.get(key) == value for key, value in expected.items())
    stale_reasons: list[str] = []
    if latest_source_mtime_ns > graph_mtime_ns:
        stale_reasons.append("source_newer_than_graph")
    if not manifest_path.is_file():
        stale_reasons.append("manifest_missing")
    if not config_current:
        stale_reasons.append("configuration_changed")
    return {
        **base,
        "status": "stale" if stale_reasons else "current",
        "stale_reasons": stale_reasons,
        "node_count": node_count,
        "edge_count": edge_count,
        "indexed_at": metadata.get("indexed_at", ""),
    }


def inspect_repos(
    *,
    root: Path,
    workspace_config: dict[str, object],
    selected: list[str] | None = None,
) -> list[dict[str, object]]:
    names = selected if selected is not None else sorted(_repos(workspace_config))
    return [
        inspect_repo(name, root=root, workspace_config=workspace_config)
        for name in names
    ]


def _summary(items: list[dict[str, object]]) -> dict[str, int]:
    summary = {name: 0 for name in ("current", "stale", "missing", "unsupported", "error")}
    for item in items:
        status = str(item.get("status") or "error")
        summary[status] = summary.get(status, 0) + 1
    return summary


def _print_payload(payload: dict[str, object], *, json_mode: bool, json_dumps: Callable[[object], str]) -> None:
    if json_mode:
        print(json_dumps(payload))
        return
    if "repos" in payload:
        for item in payload["repos"]:  # type: ignore[index]
            print(f"{item['repo']}: {item['status']}")
        return
    print(f"Graphify: {'available' if payload.get('available') else 'unavailable'}")


def command_code_graph_doctor(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    binary = which("graphify")
    mcp_binary = which("graphify-mcp")
    version_step: dict[str, object] | None = None
    if binary:
        completed = run_command(
            [binary, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        version_step = {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
        if completed.returncode != 0:
            python = which("python3")
            if python:
                completed = run_command(
                    [
                        python,
                        "-c",
                        'import importlib.metadata; print(importlib.metadata.version("graphifyy"))',
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                version_step = {
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                }
    items = inspect_repos(root=root, workspace_config=workspace_config)
    config = _config(workspace_config)
    version_output = (
        str(version_step["stdout"]).splitlines()[0].strip()
        if version_step and version_step["returncode"] == 0
        else ""
    )
    version_match = re.search(r"\d+(?:\.\d+)+", version_output)
    installed_version = version_match.group(0) if version_match else version_output
    expected_version = str(config["version"])
    version_matches = not expected_version or installed_version.lstrip("v") == expected_version.lstrip("v")
    available = bool(
        binary
        and mcp_binary
        and version_step
        and version_step["returncode"] == 0
        and version_matches
    )
    payload = {
        "ok": True,
        "available": available,
        "binary": binary or "",
        "mcp_binary": mcp_binary or "",
        "version": installed_version,
        "version_matches_config": version_matches,
        "config": config,
        "managed_project_count": len(items),
        "summary": _summary(items),
        "notes": "Graphify is optional for unrelated SoftOS lifecycle commands.",
    }
    if version_step and version_step["returncode"] != 0:
        payload["version_error"] = version_step
    _print_payload(payload, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
    return 0


def command_code_graph_status(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
) -> int:
    repo = str(getattr(args, "repo", "") or "").strip()
    items = inspect_repos(
        root=root,
        workspace_config=workspace_config,
        selected=[repo] if repo else None,
    )
    payload = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "ok": not any(item.get("status") == "error" for item in items),
        "summary": _summary(items),
        "repos": items,
    }
    _print_payload(payload, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
    return 0 if payload["ok"] else 1


def _ensure_local_git_exclude(repo_path: Path, output_dir: str, run_command: RunCommand) -> None:
    completed = run_command(
        ["git", "-C", str(repo_path), "rev-parse", "--git-path", "info/exclude"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return
    exclude_path = Path(completed.stdout.strip())
    if not exclude_path.is_absolute():
        exclude_path = repo_path / exclude_path
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    pattern = f"/{output_dir}/"
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.is_file() else ""
    if pattern not in {line.strip() for line in existing.splitlines()}:
        with exclude_path.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(pattern + "\n")


def refresh_repo(
    repo_name: str,
    *,
    root: Path,
    workspace_config: dict[str, object],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> dict[str, object]:
    before = inspect_repo(repo_name, root=root, workspace_config=workspace_config)
    if before.get("status") in {"error", "unsupported"}:
        return before
    binary = which("graphify")
    if not binary:
        return {
            **before,
            "status": "error",
            "error": {"code": "graphify_missing", "message": "`graphify` is not available in PATH."},
        }
    config = _config(workspace_config)
    repo_path = Path(str(before["path"]))
    temp_base = Path(tempfile.mkdtemp(prefix=".graphify-softos-", dir=repo_path))
    generated_path = temp_base / "graphify-out"
    output_path = repo_path / config["output_dir"]
    command = [
        binary,
        "extract",
        str(repo_path),
        "--code-only",
        "--out",
        str(temp_base),
        "--exclude",
        temp_base.name,
    ]
    for exclusion in before.get("exclusions", []):
        command.extend(["--exclude", str(exclusion)])
    env = dict(os.environ)
    env["GRAPHIFY_NO_TIPS"] = "1"
    try:
        completed = run_command(
            command,
            cwd=repo_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return {
                **before,
                "status": "error",
                "operation": "init" if before.get("status") == "missing" else "update",
                "error": {
                    "code": "graphify_failed",
                    "message": completed.stderr.strip() or completed.stdout.strip() or "Graphify failed.",
                },
            }
        generated_graph = generated_path / "graph.json"
        generated_manifest = generated_path / "manifest.json"
        if not generated_graph.is_file() or not generated_manifest.is_file():
            return {
                **before,
                "status": "error",
                "operation": "init" if before.get("status") == "missing" else "update",
                "error": {
                    "code": "graphify_output_incomplete",
                    "message": "Graphify completed without graph.json and manifest.json.",
                },
            }
        _graph_counts(generated_graph)
        metadata = _metadata_expected(
            repo_name,
            _repos(workspace_config)[repo_name],
            list(before.get("exclusions", [])),
            config,
            int(before["source_file_count"]),
            str(before["source_fingerprint"]),
        )
        metadata["indexed_at"] = _utc_now()
        (generated_path / METADATA_FILE).write_text(
            json.dumps(metadata, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        backup_path = temp_base / "previous-index"
        if output_path.exists():
            os.replace(output_path, backup_path)
        try:
            os.replace(generated_path, output_path)
        except OSError:
            if backup_path.exists() and not output_path.exists():
                os.replace(backup_path, output_path)
            raise
        if backup_path.exists():
            shutil.rmtree(backup_path)
        _ensure_local_git_exclude(repo_path, config["output_dir"], run_command)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            **before,
            "status": "error",
            "operation": "init" if before.get("status") == "missing" else "update",
            "error": {"code": "graphify_update_failed", "message": str(exc)},
        }
    finally:
        shutil.rmtree(temp_base, ignore_errors=True)
    after = inspect_repo(repo_name, root=root, workspace_config=workspace_config)
    after["operation"] = "init" if before.get("status") == "missing" else "update"
    after["command"] = command
    return after


def command_code_graph_refresh(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    repo = str(getattr(args, "repo", "") or "").strip()
    all_repos = bool(getattr(args, "all", False))
    if repo and all_repos:
        raise SystemExit("Usa un repo o `--all`, no ambos.")
    if not repo and not all_repos:
        raise SystemExit("`flow code-graph refresh` requiere un repo o `--all`.")
    names = sorted(_repos(workspace_config)) if all_repos else [repo]
    items: list[dict[str, object]] = []
    for name in names:
        try:
            items.append(
                refresh_repo(
                    name,
                    root=root,
                    workspace_config=workspace_config,
                    which=which,
                    run_command=run_command,
                )
            )
        except Exception as exc:  # isolate unexpected project-specific failures
            items.append(
                {
                    "repo": name,
                    "status": "error",
                    "error": {"code": "unexpected_error", "message": str(exc)},
                }
            )
    payload = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "ok": not any(item.get("status") == "error" for item in items),
        "summary": _summary(items),
        "repos": items,
    }
    _print_payload(payload, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
    return 0 if payload["ok"] else 1
