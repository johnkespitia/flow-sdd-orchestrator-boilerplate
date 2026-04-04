from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from flowctl.secret_scan import is_advisory_secret_finding


def command_providers_doctor(
    args,
    *,
    load_providers_config,
    provider_categories: Callable[[], list[str]],
    provider_default,
    provider_entries,
    provider_entrypoint_path,
    provider_requires,
    provider_missing_runtime,
    provider_enabled,
    providers_config_file: Path,
    rel: Callable[[Path], str],
    json_dumps: Callable[[object], str],
) -> int:
    payload = load_providers_config()
    findings: list[str] = []

    data = {
        "manifest": providers_config_file.name,
        "categories": {},
        "findings": findings,
    }

    categories = [args.category] if args.category else provider_categories()
    for category in categories:
        try:
            default_provider = provider_default(payload, category)
            entries = provider_entries(payload, category)
        except ValueError as exc:
            findings.append(str(exc))
            continue

        category_payload = {"default_provider": default_provider, "providers": []}
        for provider_name in sorted(entries):
            config = entries[provider_name]
            try:
                entrypoint = provider_entrypoint_path(config)
                requires = provider_requires(config)
                missing_runtime = provider_missing_runtime(config) if provider_enabled(config) else []
            except ValueError as exc:
                findings.append(f"{category}.{provider_name}: {exc}")
                continue

            status = "ok"
            if provider_enabled(config) and not entrypoint.is_file():
                status = "missing-entrypoint"
                findings.append(f"{category}.{provider_name}: falta `{rel(entrypoint)}`.")
            elif provider_enabled(config) and missing_runtime:
                status = "missing-runtime"
                findings.append(
                    f"{category}.{provider_name}: faltan comandos requeridos ({', '.join(missing_runtime)})."
                )
            elif not provider_enabled(config):
                status = "disabled"

            category_payload["providers"].append(
                {
                    "name": provider_name,
                    "status": status,
                    "enabled": provider_enabled(config),
                    "entrypoint": rel(entrypoint),
                    "requires": requires,
                }
            )
        data["categories"][category] = category_payload

    data["findings"] = findings
    if bool(getattr(args, "json", False)):
        print(json_dumps(data))
        return 1 if findings else 0

    print("Providers doctor")
    print(f"- manifest: {'ok' if providers_config_file.is_file() else 'missing'} ({providers_config_file.name})")
    for category, category_payload in data["categories"].items():
        print(f"- {category}.default_provider: {category_payload['default_provider']}")
        for provider in category_payload["providers"]:
            print(
                f"- {category}.{provider['name']}: {provider['status']} "
                f"(entrypoint={provider['entrypoint']}, requires={','.join(provider['requires']) or 'none'})"
            )

    if findings:
        print("", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    return 0


def command_providers_list(
    args,
    *,
    load_providers_config,
    provider_categories: Callable[[], list[str]],
    provider_section,
    provider_entries,
    provider_enabled,
    provider_entrypoint_path,
    provider_requires,
    provider_default,
) -> int:
    payload = load_providers_config()
    categories = [args.category] if args.category else provider_categories()
    data: dict[str, object] = {}

    for category in categories:
        section = provider_section(payload, category)
        entries = provider_entries(payload, category)
        items: list[dict[str, object]] = []
        for provider_name, config in sorted(entries.items()):
            items.append(
                {
                    "name": provider_name,
                    "enabled": provider_enabled(config),
                    "entrypoint": provider_entrypoint_path(config),
                    "requires": provider_requires(config),
                    "default": provider_name == str(section.get("default_provider", "")),
                }
            )
        data[category] = {
            "default_provider": provider_default(payload, category),
            "providers": items,
        }

    if bool(getattr(args, "json", False)):
        print(json.dumps(data, indent=2, ensure_ascii=True, default=str))
        return 0

    for category in categories:
        section = data[category]
        print(f"[{category}] default={section['default_provider']}")
        for item in section["providers"]:
            print(
                f"- {item['name']}: enabled={'yes' if item['enabled'] else 'no'}, "
                f"default={'yes' if item['default'] else 'no'}, "
                f"entrypoint={item['entrypoint']}, requires={','.join(item['requires']) or 'none'}"
            )
    return 0


def submodule_repo_names(repo_names: list[str], repo_strategy: Callable[[str], str]) -> list[str]:
    return [repo for repo in repo_names if repo_strategy(repo) == "submodule"]


def gitmodules_paths(root: Path, git_output) -> dict[str, str]:
    path = root / ".gitmodules"
    if not path.is_file():
        return {}
    rc, stdout, _ = git_output(["git", "config", "-f", str(path), "--get-regexp", r"^submodule\..*\.path$"])
    if rc != 0 or not stdout:
        return {}
    mapping: dict[str, str] = {}
    for line in stdout.splitlines():
        key, raw_path = line.split(" ", 1)
        name = key.split(".", 2)[1]
        mapping[name] = raw_path.strip()
    return mapping


def submodule_recorded_sha(root: Path, repo_path: str, git_output) -> Optional[str]:
    rc, stdout, _ = git_output(["git", "-C", str(root), "ls-files", "-s", "--", repo_path])
    if rc != 0 or not stdout:
        return None
    parts = stdout.split()
    if len(parts) >= 2:
        return parts[1]
    return None


def submodule_name_for_path(root: Path, repo_path: str, git_output) -> Optional[str]:
    normalized = repo_path.strip().strip("/")
    for name, path in gitmodules_paths(root, git_output).items():
        if path.strip().strip("/") == normalized:
            return name
    return None


def inspect_submodule(
    repo: str,
    *,
    root: Path,
    repo_config,
    repo_root,
    repo_strategy: Callable[[str], str],
    git_output,
) -> dict[str, object]:
    registered_paths = gitmodules_paths(root, git_output).values()
    path = str(repo_config(repo).get("path", ".")).strip()
    repo_path = repo_root(repo)
    exists = repo_path.is_dir()
    status = {
        "repo": repo,
        "path": path,
        "exists": exists,
        "strategy": repo_strategy(repo),
        "registered": path in registered_paths,
        "initialized": False,
        "dirty": False,
        "detached": False,
        "head_sha": None,
        "index_sha": None,
        "pointer_synced": True,
        "findings": [],
    }
    if not exists:
        status["findings"].append("El path del submodulo no existe en el workspace.")
        return status

    rc, stdout, stderr = git_output(["git", "-C", str(root), "submodule", "status", "--", path])
    status["initialized"] = rc == 0 and bool(stdout)
    if rc != 0:
        status["findings"].append(stderr or "No pude leer `git submodule status`.")

    head_rc, head_stdout, _ = git_output(["git", "-C", str(repo_path), "rev-parse", "HEAD"])
    if head_rc == 0:
        status["head_sha"] = head_stdout
    index_sha = submodule_recorded_sha(root, path, git_output)
    status["index_sha"] = index_sha
    if head_rc == 0 and index_sha:
        status["pointer_synced"] = head_stdout == index_sha
        if not status["pointer_synced"]:
            status["findings"].append("El gitlink del root no coincide con el HEAD actual del submodulo.")

    dirty_rc, dirty_stdout, dirty_stderr = git_output(["git", "-C", str(repo_path), "status", "--porcelain"])
    if dirty_rc == 0:
        status["dirty"] = bool(dirty_stdout)
        if status["dirty"]:
            status["findings"].append("El submodulo tiene cambios locales sin confirmar.")
    else:
        status["findings"].append(dirty_stderr or "No pude leer `git status --porcelain` del submodulo.")

    branch_rc, branch_stdout, _ = git_output(["git", "-C", str(repo_path), "symbolic-ref", "-q", "--short", "HEAD"])
    status["detached"] = branch_rc != 0 or not branch_stdout
    if status["detached"]:
        status["findings"].append("El submodulo esta en detached HEAD.")

    return status


def command_submodule_doctor(
    args,
    *,
    repo_names: list[str],
    repo_strategy: Callable[[str], str],
    root: Path,
    git_output,
    repo_config,
    repo_root,
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    submodules = submodule_repo_names(repo_names, repo_strategy)
    payload = {
        "generated_at": utc_now(),
        "submodules": [
            inspect_submodule(
                repo,
                root=root,
                repo_config=repo_config,
                repo_root=repo_root,
                repo_strategy=repo_strategy,
                git_output=git_output,
            )
            for repo in submodules
        ],
        "gitmodules": gitmodules_paths(root, git_output),
    }
    failures = 0
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        for item in payload["submodules"]:
            if not item["registered"] or not item["initialized"] or not item["pointer_synced"] or item["dirty"]:
                failures += 1
        return 1 if failures else 0

    if not submodules:
        print("No hay repos configurados con `repo_strategy: submodule`.")
        return 0

    print("Submodule doctor")
    for item in payload["submodules"]:
        print(f"- {item['repo']}: path={item['path']}")
        print(f"  registered={'yes' if item['registered'] else 'no'}")
        print(f"  initialized={'yes' if item['initialized'] else 'no'}")
        print(f"  dirty={'yes' if item['dirty'] else 'no'}")
        print(f"  detached={'yes' if item['detached'] else 'no'}")
        print(f"  pointer_synced={'yes' if item['pointer_synced'] else 'no'}")
        print(f"  head_sha={item['head_sha'] or 'n/a'}")
        print(f"  index_sha={item['index_sha'] or 'n/a'}")
        for finding in item["findings"]:
            print(f"  finding: {finding}")
        if not item["registered"] or not item["initialized"] or not item["pointer_synced"] or item["dirty"]:
            failures += 1
    return 1 if failures else 0


def command_submodule_sync(
    args,
    *,
    repo_names: list[str],
    repo_strategy: Callable[[str], str],
    root: Path,
    capture_command,
    repo_config,
    repo_root,
    git_output,
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    submodules = submodule_repo_names(repo_names, repo_strategy)
    if not submodules:
        print("No hay repos configurados con `repo_strategy: submodule`.")
        return 0

    executions: list[dict[str, object]] = []
    findings: list[str] = []
    commands = [
        ["git", "-C", str(root), "submodule", "sync", "--recursive"],
        ["git", "-C", str(root), "submodule", "update", "--init", "--recursive"],
    ]
    for command in commands:
        execution = capture_command(command, root)
        executions.append(execution)
        if int(execution["returncode"]) != 0:
            findings.append(f"Fallo `{ ' '.join(command) }`.")

    if not args.no_stage:
        for repo in submodules:
            repo_path = str(repo_config(repo).get("path", ".")).strip()
            head_sha = inspect_submodule(
                repo,
                root=root,
                repo_config=repo_config,
                repo_root=repo_root,
                repo_strategy=repo_strategy,
                git_output=git_output,
            ).get("head_sha")
            index_sha = submodule_recorded_sha(root, repo_path, git_output)
            if head_sha and index_sha and head_sha != index_sha:
                execution = capture_command(["git", "-C", str(root), "add", repo_path], root)
                execution["label"] = f"stage:{repo}"
                executions.append(execution)
                if int(execution["returncode"]) != 0:
                    findings.append(f"No pude stagear el gitlink de `{repo}`.")

    payload = {
        "generated_at": utc_now(),
        "submodules": submodules,
        "executions": executions,
        "findings": findings,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 1 if findings else 0

    print("Submodule sync")
    for execution in executions:
        print(f"- {' '.join(execution['command'])}: rc={execution['returncode']}")
    for finding in findings:
        print(f"- finding: {finding}")
    return 1 if findings else 0


def default_worktree_branch(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._/-]+", "-", name.strip()).strip("./-")
    if not normalized:
        normalized = "worktree"
    return f"demo/{normalized}"


def wait_for_worktree_path(path: Path, *, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists() and (path / ".git").exists():
            return True
        time.sleep(0.05)
    return path.exists() and (path / ".git").exists()


WORKTREE_TERMINAL_FEATURE_STATUSES = {"released", "completed"}
WORKTREE_ACTIVE_FEATURE_STATUSES = {
    "planned",
    "slice-started",
    "approved-spec",
    "in-review",
    "reviewing-spec",
    "draft-spec",
}
WORKTREE_ACTIVE_SLICE_STATUSES = {"started"}
WORKTREE_CLOSED_SLICE_STATUSES = {"passed", "completed", "skipped"}


def _safe_load_json(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _worktree_plan_index(
    *,
    plan_root: Path,
    state_root: Path,
) -> dict[str, list[dict[str, object]]]:
    index: dict[str, list[dict[str, object]]] = {}
    for plan_path in sorted(plan_root.glob("*.json")):
        plan_payload = _safe_load_json(plan_path)
        if not plan_payload:
            continue
        feature = str(plan_payload.get("feature", "")).strip() or plan_path.stem
        state_payload = _safe_load_json(state_root / f"{feature}.json") or {}
        feature_status = str(state_payload.get("status", "")).strip().lower()
        slice_results = state_payload.get("slice_results", {})
        if not isinstance(slice_results, dict):
            slice_results = {}
        for slice_payload in plan_payload.get("slices", []):
            if not isinstance(slice_payload, dict):
                continue
            worktree_text = str(slice_payload.get("worktree", "")).strip()
            if not worktree_text:
                continue
            slice_name = str(slice_payload.get("name", "")).strip()
            slice_result = slice_results.get(slice_name, {})
            if not isinstance(slice_result, dict):
                slice_result = {}
            item = {
                "feature": feature,
                "slice": slice_name,
                "repo": str(slice_payload.get("repo", "")).strip(),
                "branch": str(slice_payload.get("branch", "")).strip(),
                "feature_status": feature_status,
                "slice_status": str(slice_result.get("status", "")).strip().lower(),
                "plan_path": str(plan_path),
            }
            key = str(Path(worktree_text).resolve())
            index.setdefault(key, []).append(item)
    return index


def _infer_worktree_repo(name: str, repo_names: list[str], root_repo: str) -> str:
    candidates = sorted(
        [repo for repo in repo_names if name == repo or name.startswith(f"{repo}-")],
        key=len,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    return root_repo


def _classify_worktree_activity(plan_refs: list[dict[str, object]]) -> str:
    if not plan_refs:
        return "orphan"
    for item in plan_refs:
        feature_status = str(item.get("feature_status", "")).strip().lower()
        slice_status = str(item.get("slice_status", "")).strip().lower()
        if feature_status in WORKTREE_TERMINAL_FEATURE_STATUSES:
            continue
        if slice_status in WORKTREE_ACTIVE_SLICE_STATUSES:
            return "active"
        if slice_status and slice_status not in WORKTREE_CLOSED_SLICE_STATUSES:
            return "active"
        if feature_status in WORKTREE_ACTIVE_FEATURE_STATUSES and slice_status not in WORKTREE_CLOSED_SLICE_STATUSES:
            return "active"
    return "closed"


def _inspect_worktree_git(path: Path, capture_command) -> tuple[str, bool | None, list[str]]:
    branch_execution = capture_command(["git", "-C", str(path), "branch", "--show-current"], path)
    branch = ""
    if int(branch_execution["returncode"]) == 0:
        tail = str(branch_execution.get("output_tail", "")).strip().splitlines()
        branch = tail[-1].strip() if tail else ""

    status_execution = capture_command(["git", "-C", str(path), "status", "--porcelain"], path)
    if int(status_execution["returncode"]) != 0:
        return branch, None, [str(status_execution.get("output_tail", "")).strip() or "No pude inspeccionar git status del worktree."]

    tail = str(status_execution.get("output_tail", "")).strip()
    dirty = bool(tail)
    return branch, dirty, []


def _build_worktree_inventory(
    *,
    repo_names: list[str],
    root_repo: str,
    worktree_root: Path,
    plan_root: Path,
    state_root: Path,
    capture_command,
) -> list[dict[str, object]]:
    if not worktree_root.exists():
        return []

    plan_index = _worktree_plan_index(plan_root=plan_root, state_root=state_root)
    items: list[dict[str, object]] = []
    for candidate in sorted(worktree_root.iterdir()):
        if not candidate.is_dir():
            continue
        path = candidate.resolve()
        plan_refs = list(plan_index.get(str(path), []))
        repo = str(plan_refs[0].get("repo", "")).strip() if len(plan_refs) == 1 else ""
        if not repo:
            repo = _infer_worktree_repo(candidate.name, repo_names, root_repo)
        activity = _classify_worktree_activity(plan_refs)
        branch, dirty, findings = _inspect_worktree_git(path, capture_command)
        if not branch and plan_refs:
            branch = str(plan_refs[0].get("branch", "")).strip()

        eligible = False
        reason = ""
        if dirty is None:
            reason = "git-unavailable"
        elif dirty:
            reason = "dirty"
        elif activity == "active":
            reason = "active-plan"
        elif activity == "orphan":
            eligible = True
            reason = "orphan-clean"
        else:
            eligible = True
            reason = "closed-clean"

        items.append(
            {
                "name": candidate.name,
                "path": str(path),
                "repo": repo,
                "branch": branch,
                "activity": activity,
                "dirty": dirty,
                "plan_refs": plan_refs,
                "cleanable": eligible,
                "reason": reason,
                "findings": findings,
            }
        )
    return items


def _worktree_matches_filters(item: dict[str, object], *, names: set[str], features: set[str], stale_only: bool) -> bool:
    if names and str(item.get("name", "")) not in names:
        return False
    if features:
        refs = item.get("plan_refs", [])
        if not isinstance(refs, list):
            refs = []
        ref_features = {str(ref.get("feature", "")).strip() for ref in refs if isinstance(ref, dict)}
        if not (ref_features & features):
            return False
    if stale_only and not bool(item.get("cleanable")):
        return False
    return True


def _select_worktrees_for_cleanup(
    inventory: list[dict[str, object]],
    *,
    names: set[str],
    features: set[str],
    stale_only: bool,
    force: bool,
) -> tuple[list[dict[str, object]], list[str]]:
    selected: list[dict[str, object]] = []
    findings: list[str] = []
    for item in inventory:
        if not _worktree_matches_filters(item, names=names, features=features, stale_only=False):
            continue
        if stale_only and not bool(item.get("cleanable")):
            findings.append(
                f"`{item['name']}` se preserva ({item.get('reason', 'not-cleanable')})."
            )
            continue
        if item.get("dirty") is True and not force:
            findings.append(f"`{item['name']}` tiene cambios locales; usa `--force` para removerlo.")
            continue
        if item.get("activity") == "active" and not force:
            findings.append(f"`{item['name']}` sigue referenciado por un plan activo; usa `--force` para removerlo.")
            continue
        selected.append(item)
    return selected, findings


def command_worktree_list(
    args,
    *,
    repo_names: list[str],
    root_repo: str,
    worktree_root: Path,
    plan_root: Path,
    state_root: Path,
    capture_command,
    json_dumps: Callable[[object], str],
) -> int:
    inventory = _build_worktree_inventory(
        repo_names=repo_names,
        root_repo=root_repo,
        worktree_root=worktree_root,
        plan_root=plan_root,
        state_root=state_root,
        capture_command=capture_command,
    )
    names = {str(item).strip() for item in getattr(args, "name", []) or [] if str(item).strip()}
    features = {str(item).strip() for item in getattr(args, "feature", []) or [] if str(item).strip()}
    stale_only = bool(getattr(args, "stale_only", False))
    filtered = [
        item
        for item in inventory
        if _worktree_matches_filters(item, names=names, features=features, stale_only=stale_only)
    ]
    payload = {
        "worktree_root": str(worktree_root.resolve()),
        "count": len(filtered),
        "items": filtered,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0

    print("Worktree list")
    print(f"- root: {worktree_root.resolve()}")
    for item in filtered:
        print(
            f"- {item['name']}: repo={item['repo']}, branch={item['branch'] or 'unknown'}, "
            f"activity={item['activity']}, dirty={'yes' if item['dirty'] else 'no' if item['dirty'] is not None else 'unknown'}, "
            f"cleanable={'yes' if item['cleanable'] else 'no'} ({item['reason']})"
        )
    return 0


def command_worktree_clean(
    args,
    *,
    repo_names: list[str],
    root_repo: str,
    root: Path,
    worktree_root: Path,
    plan_root: Path,
    state_root: Path,
    repo_root: Callable[[str], Path],
    capture_command,
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    inventory = _build_worktree_inventory(
        repo_names=repo_names,
        root_repo=root_repo,
        worktree_root=worktree_root,
        plan_root=plan_root,
        state_root=state_root,
        capture_command=capture_command,
    )
    names = {str(item).strip() for item in ([getattr(args, "name", "")] if getattr(args, "name", "") else []) if str(item).strip()}
    features = {str(item).strip() for item in getattr(args, "feature", []) or [] if str(item).strip()}
    stale_only = bool(getattr(args, "stale", False) or (not names and not features))
    force = bool(getattr(args, "force", False))
    selected, findings = _select_worktrees_for_cleanup(
        inventory,
        names=names,
        features=features,
        stale_only=stale_only,
        force=force,
    )

    executions: list[dict[str, object]] = []
    pruned_roots: set[str] = set()
    removed: list[str] = []

    for item in selected:
        owner_repo = str(item.get("repo", "")).strip() or root_repo
        owner_root = repo_root(owner_repo) if owner_repo in repo_names else root
        remove_command = ["git", "-C", str(owner_root), "worktree", "remove"]
        if force:
            remove_command.append("--force")
        remove_command.append(str(item["path"]))
        if bool(getattr(args, "dry_run", False)):
            executions.append(
                {
                    "label": f"remove:{item['name']}",
                    "command": remove_command,
                    "returncode": 0,
                    "output_tail": "dry-run",
                }
            )
            removed.append(str(item["path"]))
            pruned_roots.add(str(owner_root))
            continue

        execution = capture_command(remove_command, owner_root)
        execution["label"] = f"remove:{item['name']}"
        executions.append(execution)
        if int(execution["returncode"]) != 0:
            findings.append(
                execution["output_tail"] or f"No pude remover el worktree `{item['name']}`."
            )
            continue
        removed.append(str(item["path"]))
        pruned_roots.add(str(owner_root))

    for prune_root in sorted(pruned_roots):
        prune_command = ["git", "-C", prune_root, "worktree", "prune"]
        if bool(getattr(args, "dry_run", False)):
            executions.append(
                {
                    "label": f"prune:{prune_root}",
                    "command": prune_command,
                    "returncode": 0,
                    "output_tail": "dry-run",
                }
            )
            continue
        execution = capture_command(prune_command, Path(prune_root))
        execution["label"] = f"prune:{prune_root}"
        executions.append(execution)
        if int(execution["returncode"]) != 0:
            findings.append(execution["output_tail"] or f"No pude ejecutar `git worktree prune` en `{prune_root}`.")

    payload = {
        "generated_at": utc_now(),
        "worktree_root": str(worktree_root.resolve()),
        "selected": [item["name"] for item in selected],
        "removed": removed,
        "dry_run": bool(getattr(args, "dry_run", False)),
        "force": force,
        "stale_only": stale_only,
        "executions": executions,
        "findings": findings,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 1 if findings else 0

    print("Worktree clean")
    print(f"- root: {worktree_root.resolve()}")
    print(f"- stale_only: {'yes' if stale_only else 'no'}")
    print(f"- force: {'yes' if force else 'no'}")
    print(f"- dry_run: {'yes' if payload['dry_run'] else 'no'}")
    for name in payload["selected"]:
        print(f"- selected: {name}")
    for execution in executions:
        print(f"- {execution.get('label', 'command')}: rc={execution['returncode']}")
    for finding in findings:
        print(f"- finding: {finding}")
    return 1 if findings else 0


def command_worktree_create(
    args,
    *,
    repo_names: list[str],
    repo_strategy: Callable[[str], str],
    root: Path,
    worktree_root: Path,
    repo_config,
    capture_command,
    git_output,
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    target = (worktree_root / str(args.name)).resolve()
    branch = str(getattr(args, "branch", "") or default_worktree_branch(str(args.name)))
    from_ref = str(getattr(args, "from_ref", "") or "HEAD")
    findings: list[str] = []
    executions: list[dict[str, object]] = []
    submodules = submodule_repo_names(repo_names, repo_strategy)

    try:
        target.relative_to(worktree_root.resolve())
    except ValueError as exc:
        raise SystemExit(f"El worktree debe vivir dentro de `{worktree_root}`.") from exc

    if target.exists():
        raise SystemExit(f"El worktree `{target}` ya existe.")

    worktree_root.mkdir(parents=True, exist_ok=True)

    create_execution = capture_command(
        ["git", "-C", str(root), "worktree", "add", "-b", branch, str(target), from_ref],
        root,
    )
    create_execution["label"] = "create"
    executions.append(create_execution)
    if int(create_execution["returncode"]) != 0:
        findings.append(
            create_execution["output_tail"] or f"No pude crear el worktree `{target}` desde `{from_ref}`."
        )
    elif not wait_for_worktree_path(target):
        findings.append(f"El worktree `{target}` no quedo materializado despues de `git worktree add`.")
    else:
        repair_execution = capture_command(
            ["git", "-C", str(root), "worktree", "repair", "--relative-paths", str(target)],
            root,
        )
        repair_execution["label"] = "repair"
        executions.append(repair_execution)
        if int(repair_execution["returncode"]) != 0:
            findings.append(repair_execution["output_tail"] or "No pude reparar el admin dir del worktree.")

        sync_execution = capture_command(
            ["git", "-C", str(target), "submodule", "sync", "--recursive"],
            target,
        )
        sync_execution["label"] = "submodule-sync"
        executions.append(sync_execution)
        if int(sync_execution["returncode"]) != 0:
            findings.append(sync_execution["output_tail"] or "No pude sincronizar submodulos en el worktree.")

        for repo in submodules:
            repo_path = str(repo_config(repo).get("path", ".")).strip()
            repo_name = submodule_name_for_path(root, repo_path, git_output) or repo
            seed_path = (root / repo_path).resolve()
            if not seed_path.is_dir():
                continue
            seed_execution = capture_command(
                ["git", "-C", str(target), "config", f"submodule.{repo_name}.url", str(seed_path)],
                target,
            )
            seed_execution["label"] = f"submodule-seed:{repo}"
            executions.append(seed_execution)
            if int(seed_execution["returncode"]) != 0:
                findings.append(
                    seed_execution["output_tail"] or f"No pude configurar el seed local para `{repo}`."
                )

        update_execution = capture_command(
            [
                "git",
                "-C",
                str(target),
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "update",
                "--init",
                "--recursive",
                "--jobs",
                "1",
            ],
            target,
        )
        update_execution["label"] = "submodule-update"
        executions.append(update_execution)
        if int(update_execution["returncode"]) != 0:
            findings.append(update_execution["output_tail"] or "No pude hidratar submodulos en el worktree.")

    hydrated: list[dict[str, object]] = []
    if not findings:
        for repo in submodules:
            repo_path = target / str(repo_config(repo).get("path", ".")).strip()
            exists = repo_path.is_dir()
            hydrated.append({"repo": repo, "path": str(repo_path), "exists": exists})
            if not exists:
                findings.append(f"El submodulo `{repo}` no quedo disponible en `{repo_path}`.")

    payload = {
        "generated_at": utc_now(),
        "branch": branch,
        "from_ref": from_ref,
        "worktree": str(target),
        "submodules": hydrated,
        "executions": executions,
        "findings": findings,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 1 if findings else 0

    print("Worktree create")
    print(f"- branch: {branch}")
    print(f"- from_ref: {from_ref}")
    print(f"- worktree: {target}")
    for execution in executions:
        print(f"- {execution.get('label', 'command')}: rc={execution['returncode']}")
    for item in hydrated:
        print(f"- submodule {item['repo']}: {'ok' if item['exists'] else 'missing'} ({item['path']})")
    for finding in findings:
        print(f"- finding: {finding}")
    return 1 if findings else 0


def resolve_secret_targets(payload: dict[str, object], names: list[str], secrets_target_entries) -> list[tuple[str, dict[str, object]]]:
    targets = secrets_target_entries(payload)
    if not names:
        return list(sorted(targets.items()))
    selected: list[tuple[str, dict[str, object]]] = []
    for name in names:
        if name not in targets:
            raise SystemExit(f"No existe target de secrets `{name}`.")
        selected.append((name, targets[name]))
    return selected


def render_secret_target(target_format: str, values: dict[str, str]) -> str:
    if target_format == "json":
        return json.dumps(values, indent=2, ensure_ascii=True) + "\n"
    lines: list[str] = []
    for key, value in values.items():
        rendered = shlex.quote(value) if re.search(r"\s", value) else value
        lines.append(f"{key}={rendered}")
    return "\n".join(lines) + ("\n" if lines else "")


def tracked_repo_files(repo_path: Path, git_output) -> tuple[list[str], Optional[str]]:
    rc, stdout, stderr = git_output(["git", "-C", str(repo_path), "ls-files"])
    if rc != 0:
        return [], stderr or "git ls-files fallo"
    return [line.strip() for line in stdout.splitlines() if line.strip()], None


def staged_repo_files(repo_path: Path, git_output) -> tuple[list[str], Optional[str]]:
    rc, stdout, stderr = git_output(["git", "-C", str(repo_path), "diff", "--cached", "--name-only"])
    if rc != 0:
        return [], stderr or "git diff --cached fallo"
    return [line.strip() for line in stdout.splitlines() if line.strip()], None


def command_secrets_doctor(
    args,
    *,
    load_secrets_config,
    secrets_provider_entries,
    secrets_target_entries,
    secrets_default_provider,
    secrets_provider_entrypoint,
    secrets_provider_requires,
    secrets_provider_enabled,
    secrets_target_path,
    secrets_target_format,
    secrets_target_provider,
    secrets_target_items,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
    shutil_which,
    secrets_config_file: Path,
) -> int:
    payload = load_secrets_config()
    findings: list[str] = []
    providers = secrets_provider_entries(payload)
    targets = secrets_target_entries(payload)
    default_provider = secrets_default_provider(payload)

    data = {
        "generated_at": utc_now(),
        "manifest": secrets_config_file.name,
        "default_provider": default_provider,
        "providers": [],
        "targets": [],
    }

    for provider_name, config in sorted(providers.items()):
        try:
            entrypoint = secrets_provider_entrypoint(config)
            requires = secrets_provider_requires(config)
            missing_runtime = [command for command in requires if shutil_which(command) is None]
        except ValueError as exc:
            findings.append(f"{provider_name}: {exc}")
            continue
        data["providers"].append(
            {
                "name": provider_name,
                "enabled": secrets_provider_enabled(config),
                "entrypoint": rel(entrypoint),
                "requires": requires,
                "missing_runtime": missing_runtime,
            }
        )
        if secrets_provider_enabled(config) and not entrypoint.is_file():
            findings.append(f"El provider de secrets `{provider_name}` no tiene entrypoint `{rel(entrypoint)}`.")
        if secrets_provider_enabled(config) and missing_runtime:
            findings.append(
                f"El provider de secrets `{provider_name}` requiere comandos faltantes: {', '.join(missing_runtime)}."
            )

    for target_name, raw_target in sorted(targets.items()):
        try:
            target_path = secrets_target_path(raw_target)
            target_format = secrets_target_format(raw_target)
            provider_name = secrets_target_provider(payload, raw_target)
            items = secrets_target_items(raw_target)
        except ValueError as exc:
            findings.append(f"{target_name}: {exc}")
            continue
        data["targets"].append(
            {
                "name": target_name,
                "path": rel(target_path),
                "format": target_format,
                "provider": provider_name,
                "items": sorted(items),
            }
        )

    data["findings"] = findings
    if bool(getattr(args, "json", False)):
        print(json_dumps(data))
        return 1 if findings else 0

    print("Secrets doctor")
    print(f"- manifest: {'ok' if secrets_config_file.is_file() else 'missing'} ({secrets_config_file.name})")
    print(f"- default_provider: {default_provider}")
    for provider in data["providers"]:
        print(
            f"- provider {provider['name']}: enabled={'yes' if provider['enabled'] else 'no'}, "
            f"entrypoint={provider['entrypoint']}, requires={','.join(provider['requires']) or 'none'}"
        )
    for target in data["targets"]:
        print(
            f"- target {target['name']}: path={target['path']}, format={target['format']}, "
            f"provider={target['provider']}, items={len(target['items'])}"
        )
    for finding in findings:
        print(f"- finding: {finding}")
    return 1 if findings else 0


def command_secrets_list(
    args,
    *,
    load_secrets_config,
    secrets_target_entries,
    secrets_target_path,
    secrets_target_format,
    secrets_target_provider,
    secrets_target_items,
    secrets_default_provider,
    rel: Callable[[Path], str],
    json_dumps: Callable[[object], str],
) -> int:
    payload = load_secrets_config()
    targets = secrets_target_entries(payload)
    data = {
        "default_provider": secrets_default_provider(payload),
        "targets": [],
    }

    for target_name, raw_target in sorted(targets.items()):
        target_path = secrets_target_path(raw_target)
        data["targets"].append(
            {
                "name": target_name,
                "path": rel(target_path),
                "format": secrets_target_format(raw_target),
                "provider": secrets_target_provider(payload, raw_target),
                "items": sorted(secrets_target_items(raw_target)),
            }
        )

    if bool(getattr(args, "json", False)):
        print(json_dumps(data))
        return 0

    for target in data["targets"]:
        print(
            f"- {target['name']}: path={target['path']}, format={target['format']}, "
            f"provider={target['provider']}, items={len(target['items'])}"
        )
    return 0


def command_secrets_sync(
    args,
    *,
    load_secrets_config,
    secrets_target_entries,
    secrets_target_provider,
    secrets_provider_config,
    secrets_provider_enabled,
    secrets_target_items,
    resolve_secret_value,
    secrets_target_path,
    secrets_target_format,
    render_secret_target_fn,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    write_json,
    secrets_report_root: Path,
    json_dumps: Callable[[object], str],
) -> int:
    payload = load_secrets_config()
    selected_targets = resolve_secret_targets(payload, args.target or [], secrets_target_entries)
    findings: list[str] = []
    outputs: list[dict[str, object]] = []

    for target_name, raw_target in selected_targets:
        provider_name = secrets_target_provider(payload, raw_target)
        provider_config = secrets_provider_config(payload, provider_name)
        if not secrets_provider_enabled(provider_config):
            findings.append(f"El provider `{provider_name}` del target `{target_name}` esta deshabilitado.")
            continue

        items = secrets_target_items(raw_target)
        resolved_values: dict[str, str] = {}
        for key, reference in items.items():
            value, error = resolve_secret_value(provider_name, provider_config, reference)
            if error:
                findings.append(error)
                continue
            resolved_values[key] = value or ""

        target_path = secrets_target_path(raw_target)
        target_format = secrets_target_format(raw_target)
        rendered = render_secret_target_fn(target_format, resolved_values)
        if not args.dry_run:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(rendered, encoding="utf-8")
        outputs.append(
            {
                "target": target_name,
                "path": rel(target_path),
                "format": target_format,
                "provider": provider_name,
                "items": sorted(resolved_values),
                "written": not args.dry_run,
            }
        )

    report = {
        "generated_at": utc_now(),
        "dry_run": bool(args.dry_run),
        "targets": outputs,
        "findings": findings,
    }
    report_path = secrets_report_root / f"sync-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')}.json"
    write_json(report_path, report)

    if bool(getattr(args, "json", False)):
        print(json_dumps(report))
        return 1 if findings else 0

    print(rel(report_path))
    for output in outputs:
        print(
            f"- {output['target']}: path={output['path']}, provider={output['provider']}, "
            f"items={len(output['items'])}, written={'yes' if output['written'] else 'no'}"
        )
    for finding in findings:
        print(f"- finding: {finding}")
    return 1 if findings else 0


def command_secrets_exec(
    args,
    *,
    normalize_passthrough: Callable[[list[str]], list[str]],
    load_secrets_config,
    secrets_target_entries,
    secrets_target_provider,
    secrets_provider_config,
    secrets_provider_enabled,
    secrets_target_items,
    resolve_secret_value,
    root: Path,
    json_dumps: Callable[[object], str],
) -> int:
    command = normalize_passthrough(args.command)
    if not command:
        raise SystemExit("Debes indicar un comando despues de `--`.")

    payload = load_secrets_config()
    selected_targets = resolve_secret_targets(payload, args.target or [], secrets_target_entries)
    env_updates: dict[str, str] = {}
    findings: list[str] = []
    for target_name, raw_target in selected_targets:
        provider_name = secrets_target_provider(payload, raw_target)
        provider_config = secrets_provider_config(payload, provider_name)
        if not secrets_provider_enabled(provider_config):
            findings.append(f"El provider `{provider_name}` del target `{target_name}` esta deshabilitado.")
            continue
        for key, reference in secrets_target_items(raw_target).items():
            value, error = resolve_secret_value(provider_name, provider_config, reference)
            if error:
                findings.append(error)
                continue
            env_updates[key] = value or ""

    if findings:
        raise SystemExit("\n".join(f"- {finding}" for finding in findings))

    env = os.environ.copy()
    env.update(env_updates)
    if bool(getattr(args, "json", False)):
        print(json_dumps({"command": command, "targets": args.target or [], "env_keys": sorted(env_updates)}))
        return 0
    return subprocess.run(command, cwd=root, env=env, check=False).returncode


def command_secrets_scan(
    args,
    *,
    require_dirs: Callable[[], None],
    repo_names: list[str],
    root_repo: str,
    repo_root,
    staged_repo_files_fn,
    tracked_repo_files_fn,
    git_changed_files,
    scan_secret_paths_fn,
    utc_now: Callable[[], str],
    write_json,
    secret_scan_report_root: Path,
    rel: Callable[[Path], str],
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    if args.all and args.repo:
        raise SystemExit("Usa `flow secrets scan --all` o `flow secrets scan --repo <repo>`, no ambos.")

    selected_repos = repo_names if args.all else [args.repo or root_repo]
    all_findings: list[dict[str, object]] = []
    errors: list[str] = []

    for repo_name in selected_repos:
        repo_path = repo_root(repo_name)
        if args.staged:
            relative_paths, error = staged_repo_files_fn(repo_path)
        elif args.all:
            relative_paths, error = tracked_repo_files_fn(repo_path)
        else:
            relative_paths, error = git_changed_files(repo_path)

        if error:
            errors.append(f"{repo_name}: {error}")
            continue

        all_findings.extend(scan_secret_paths_fn(repo_name, repo_path, relative_paths))

    payload = {
        "generated_at": utc_now(),
        "scope": "all" if args.all else ("staged" if args.staged else "changed"),
        "repos": selected_repos,
        "items": all_findings,
        "findings": errors + [f"{item['repo']}:{item['path']}: {', '.join(item['findings'])}" for item in all_findings],
    }
    blocking_findings = list(errors)
    for item in all_findings:
        blocking_only = [finding for finding in item["findings"] if not is_advisory_secret_finding(str(finding))]
        if blocking_only:
            blocking_findings.append(f"{item['repo']}:{item['path']}: {', '.join(blocking_only)}")
    payload["blocking_findings"] = blocking_findings

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    report_path = secret_scan_report_root / f"scan-{stamp}.json"
    write_json(report_path, payload)

    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 1 if payload["blocking_findings"] else 0

    print(rel(report_path))
    if not payload["findings"]:
        print("- Sin hallazgos.")
        return 0
    for item in all_findings:
        print(f"- {item['repo']}:{item['path']}: {', '.join(item['findings'])}")
    for error in errors:
        print(f"- {error}")
    return 1 if payload["blocking_findings"] else 0
