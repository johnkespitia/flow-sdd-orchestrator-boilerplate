from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
SEARCH_HEADER_RE = re.compile(r"^\[(?P<rank>\d+)\]\s+#(?P<id>\d+)\s+\((?P<kind>[^)]*)\)\s+[—-]\s+(?P<title>.*)$")
SEARCH_META_RE = re.compile(r"^\s*(?P<created_at>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+\|\s+scope:\s*(?P<scope>\S+)\s*$")
SENSITIVE_RE = re.compile(r"(token|secret|password|api[_-]?key|private[_-]?key)\s*[:=]", re.IGNORECASE)


def _memory_config(*, root: Path, workspace_config: dict[str, object]) -> dict[str, str]:
    memory = workspace_config.get("memory")
    memory_cfg = memory if isinstance(memory, dict) else {}
    agent = memory_cfg.get("agent")
    agent_cfg = agent if isinstance(agent, dict) else {}

    project = str(os.environ.get("ENGRAM_PROJECT") or agent_cfg.get("project") or root.name).strip()
    if not project:
        project = "softos-workspace"

    raw_data_dir = str(
        os.environ.get("ENGRAM_DATA_DIR")
        or agent_cfg.get("data_dir")
        or root / ".flow" / "memory" / "engram"
    )
    data_dir = Path(raw_data_dir).expanduser()
    if not data_dir.is_absolute():
        data_dir = root / data_dir

    return {
        "project": project,
        "data_dir": str(data_dir),
        "db_path": str(data_dir / "engram.db"),
        "source_boundary": "consultive",
    }


def _engram_env(config: dict[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    env["ENGRAM_PROJECT"] = config["project"]
    env["ENGRAM_DATA_DIR"] = config["data_dir"]
    return env


def _version(
    *,
    binary: str,
    config: dict[str, str],
    run_command: RunCommand,
) -> dict[str, object]:
    completed = run_command(
        [binary, "version"],
        env=_engram_env(config),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _print_or_json(payload: dict[str, object], *, json_mode: bool, json_dumps: Callable[[object], str]) -> None:
    if json_mode:
        print(json_dumps(payload))
        return
    status = "available" if payload.get("available") else "unavailable"
    print(f"Engram memory: {status}")
    print(f"Project: {payload.get('project')}")
    print(f"Data dir: {payload.get('data_dir')}")
    if payload.get("binary"):
        print(f"Binary: {payload.get('binary')}")
    if payload.get("version"):
        print(f"Version: {payload.get('version')}")
    if payload.get("notes"):
        print(f"Notes: {payload.get('notes')}")


def _missing_binary_payload(config: dict[str, str]) -> dict[str, object]:
    return {
        "ok": False,
        "available": False,
        "project": config["project"],
        "data_dir": config["data_dir"],
        "db_path": config["db_path"],
        "error": "`engram` is not available in PATH. Rebuild the workspace devcontainer.",
    }


def _run_engram(
    command: list[str],
    *,
    config: dict[str, str],
    run_command: RunCommand,
) -> dict[str, object]:
    completed = run_command(
        command,
        env=_engram_env(config),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def parse_search_stdout(stdout: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    body_lines: list[str] = []

    def flush() -> None:
        nonlocal current, body_lines
        if current is None:
            return
        current["body"] = "\n".join(line.rstrip() for line in body_lines).strip()
        items.append(current)
        current = None
        body_lines = []

    for raw_line in stdout.splitlines():
        line = raw_line.rstrip()
        header = SEARCH_HEADER_RE.match(line)
        if header:
            flush()
            current = {
                "rank": int(header.group("rank")),
                "id": header.group("id"),
                "kind": header.group("kind"),
                "title": header.group("title").strip(),
                "scope": "",
                "created_at": "",
                "body": "",
                "raw_header": line,
            }
            continue
        if current is None:
            continue
        meta = SEARCH_META_RE.match(line)
        if meta:
            current["created_at"] = meta.group("created_at")
            current["scope"] = meta.group("scope")
            continue
        if line.startswith("    "):
            body_lines.append(line[4:])
        elif line:
            body_lines.append(line)

    flush()
    return items


def _load_export_file(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Export JSON invalido `{path}`: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Export JSON `{path}` debe ser un objeto.")
    observations = payload.get("observations")
    if observations is None:
        observations = []
    if not isinstance(observations, list):
        raise SystemExit(f"Export JSON `{path}` tiene `observations` invalido.")
    return payload


def _export_secret_findings(payload: dict[str, object]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    observations = payload.get("observations")
    if not isinstance(observations, list):
        return findings
    for index, observation in enumerate(observations, start=1):
        if not isinstance(observation, dict):
            continue
        content = str(observation.get("content") or "")
        title = str(observation.get("title") or "")
        haystack = f"{title}\n{content}"
        if SENSITIVE_RE.search(haystack):
            findings.append(
                {
                    "index": index,
                    "id": observation.get("id", ""),
                    "title": title,
                    "reason": "potential secret-like key in title/content",
                }
            )
    return findings


def _observation_timestamp(observation: dict[str, object]) -> datetime:
    for key in ("updated_at", "last_seen_at", "created_at"):
        raw = str(observation.get(key) or "").strip()
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return datetime.fromtimestamp(0, timezone.utc)


def _prune_candidates(
    observations: list[object],
    *,
    query: str,
    older_than_days: int | None,
    keep_latest: int | None,
    now: datetime,
) -> list[dict[str, object]]:
    candidates: dict[str, dict[str, object]] = {}
    normalized_query = query.lower().strip()
    typed_observations = [item for item in observations if isinstance(item, dict)]
    sorted_observations = sorted(typed_observations, key=_observation_timestamp, reverse=True)
    keep_ids = {
        str(item.get("id") or item.get("sync_id") or index)
        for index, item in enumerate(sorted_observations[: keep_latest or 0], start=1)
    } if keep_latest else set()

    seen_fingerprints: dict[str, str] = {}
    for index, observation in enumerate(sorted_observations, start=1):
        obs_id = str(observation.get("id") or observation.get("sync_id") or index)
        title = str(observation.get("title") or "")
        content = str(observation.get("content") or "")
        fingerprint = f"{title}\n{content}".strip().lower()
        reasons: list[str] = []
        if normalized_query and normalized_query in fingerprint:
            reasons.append(f"query:{query}")
        if older_than_days is not None:
            age_days = (now - _observation_timestamp(observation)).days
            if age_days >= older_than_days:
                reasons.append(f"older_than_days:{older_than_days}")
        if keep_latest is not None and obs_id not in keep_ids:
            reasons.append(f"beyond_keep_latest:{keep_latest}")
        if fingerprint and fingerprint in seen_fingerprints:
            reasons.append(f"duplicate_of:{seen_fingerprints[fingerprint]}")
        elif fingerprint:
            seen_fingerprints[fingerprint] = obs_id
        duplicate_count = observation.get("duplicate_count")
        if isinstance(duplicate_count, int) and duplicate_count > 0:
            reasons.append(f"duplicate_count:{duplicate_count}")
        if reasons:
            candidates[obs_id] = {
                "id": obs_id,
                "title": title,
                "scope": observation.get("scope", ""),
                "created_at": observation.get("created_at", ""),
                "updated_at": observation.get("updated_at", ""),
                "reasons": reasons,
            }
    return list(candidates.values())


def command_memory_doctor(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    config = _memory_config(root=root, workspace_config=workspace_config)
    Path(config["data_dir"]).mkdir(parents=True, exist_ok=True)
    binary = which("engram")
    version: dict[str, object] | None = None
    if binary:
        version = _version(binary=binary, config=config, run_command=run_command)

    payload: dict[str, object] = {
        "ok": True,
        "available": bool(binary and version and version["ok"]),
        "binary": binary or "",
        "project": config["project"],
        "data_dir": config["data_dir"],
        "db_path": config["db_path"],
        "source_boundary": config["source_boundary"],
        "version": version["stdout"] if version and version["ok"] else "",
        "notes": "Engram is optional; missing Engram must not block SoftOS SDLC.",
    }
    if version and not version["ok"]:
        payload["version_error"] = version

    _print_or_json(payload, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
    return 0


def command_memory_smoke(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    config = _memory_config(root=root, workspace_config=workspace_config)
    Path(config["data_dir"]).mkdir(parents=True, exist_ok=True)
    binary = which("engram")
    if not binary:
        payload = _missing_binary_payload(config)
        _print_or_json(payload, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
        return 1

    steps: list[dict[str, object]] = []
    for command in (
        [binary, "version"],
        [binary, "stats"],
        [binary, "context", config["project"]],
        [binary, "search", config["project"]],
    ):
        step = _run_engram(command, config=config, run_command=run_command)
        steps.append(step)
        if step["returncode"] != 0:
            break

    if bool(getattr(args, "save", False)) and all(step["returncode"] == 0 for step in steps):
        message = (
            "TYPE: outcome\n"
            f"Project: {config['project']}\n"
            "Area: memory-smoke\n"
            "What: Engram workspace memory smoke completed\n"
            "Why: Validate isolated optional agent memory inside the devcontainer\n"
            "Where: flowctl/memory_ops.py\n"
            "Evidence: flow memory smoke --save\n"
            "Learned: Engram remains consultive and project-scoped"
        )
        step = _run_engram([binary, "save", "SoftOS memory smoke", message], config=config, run_command=run_command)
        step["command"] = f"{binary} save 'SoftOS memory smoke' <message>"
        steps.append(step)

    ok = all(step["returncode"] == 0 for step in steps)
    payload = {
        "ok": ok,
        "available": True,
        "project": config["project"],
        "data_dir": config["data_dir"],
        "db_path": config["db_path"],
        "source_boundary": config["source_boundary"],
        "steps": steps,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        _print_or_json(payload, json_mode=False, json_dumps=json_dumps)
        for step in steps:
            print(f"- {step['command']} -> {step['returncode']}")
    return 0 if ok else 1


def command_memory_stats(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    config = _memory_config(root=root, workspace_config=workspace_config)
    binary = which("engram")
    if not binary:
        payload = _missing_binary_payload(config)
        _print_or_json(payload, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
        return 1

    step = _run_engram([binary, "stats"], config=config, run_command=run_command)
    payload = {
        "ok": step["returncode"] == 0,
        "available": True,
        "project": config["project"],
        "data_dir": config["data_dir"],
        "db_path": config["db_path"],
        "step": step,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        print(step["stdout"] or step["stderr"])
    return 0 if payload["ok"] else 1


def command_memory_search(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    config = _memory_config(root=root, workspace_config=workspace_config)
    binary = which("engram")
    if not binary:
        payload = _missing_binary_payload(config)
        _print_or_json(payload, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
        return 1

    query = str(getattr(args, "query", "") or "").strip()
    step = _run_engram([binary, "search", query], config=config, run_command=run_command)
    items = parse_search_stdout(str(step["stdout"]))
    payload = {
        "ok": step["returncode"] == 0,
        "available": True,
        "project": config["project"],
        "data_dir": config["data_dir"],
        "db_path": config["db_path"],
        "query": query,
        "items": items,
        "count": len(items),
        "raw_stdout": step["stdout"],
        "step": step,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        print(step["stdout"] or step["stderr"])
    return 0 if payload["ok"] else 1


def command_memory_export(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    config = _memory_config(root=root, workspace_config=workspace_config)
    binary = which("engram")
    if not binary:
        payload = _missing_binary_payload(config)
        _print_or_json(payload, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
        return 1

    exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    output = getattr(args, "output", None)
    if output:
        output_path = Path(str(output)).expanduser()
        if not output_path.is_absolute():
            output_path = root / output_path
    else:
        stamp = exported_at.replace(":", "").replace("+00:00", "Z")
        output_path = root / ".flow" / "memory" / "exports" / f"{config['project']}-{stamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    step = _run_engram([binary, "export", str(output_path)], config=config, run_command=run_command)

    export_payload: dict[str, object] = {}
    if output_path.is_file():
        try:
            parsed = json.loads(output_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                export_payload = parsed
        except json.JSONDecodeError:
            export_payload = {}
    observations = export_payload.get("observations")
    observation_count = len(observations) if isinstance(observations, list) else 0

    result = {
        "ok": step["returncode"] == 0,
        "available": True,
        "project": config["project"],
        "exported_at": exported_at,
        "observation_count": observation_count,
        "output": str(output_path),
        "step": step,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(result))
    else:
        print(str(output_path))
    return 0 if result["ok"] else 1


def command_memory_backup(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    config = _memory_config(root=root, workspace_config=workspace_config)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(":", "").replace("+00:00", "Z")
    output = root / ".flow" / "memory" / "backups" / f"{config['project']}-{stamp}.json"
    setattr(args, "output", str(output))
    return command_memory_export(
        args,
        root=root,
        workspace_config=workspace_config,
        json_dumps=json_dumps,
        which=which,
        run_command=run_command,
    )


def command_memory_import(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    config = _memory_config(root=root, workspace_config=workspace_config)
    import_path = Path(str(getattr(args, "file"))).expanduser()
    if not import_path.is_absolute():
        import_path = root / import_path
    payload = _load_export_file(import_path)
    observations = payload.get("observations")
    observation_count = len(observations) if isinstance(observations, list) else 0
    findings = _export_secret_findings(payload)
    confirmed = bool(getattr(args, "confirm", False))

    result: dict[str, object] = {
        "ok": not findings,
        "available": bool(which("engram")),
        "project": config["project"],
        "file": str(import_path),
        "dry_run": not confirmed,
        "confirmed": confirmed,
        "observation_count": observation_count,
        "secret_findings": findings,
    }
    if findings:
        result["error"] = "Import blocked by potential secret-like content."
        if bool(getattr(args, "json", False)):
            print(json_dumps(result))
        else:
            print(result["error"])
        return 1
    if not confirmed:
        result["notes"] = "Dry-run only. Re-run with --confirm to execute `engram import`."
        if bool(getattr(args, "json", False)):
            print(json_dumps(result))
        else:
            print(result["notes"])
        return 0

    binary = which("engram")
    if not binary:
        missing = _missing_binary_payload(config)
        missing.update(result)
        _print_or_json(missing, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
        return 1
    step = _run_engram([binary, "import", str(import_path)], config=config, run_command=run_command)
    result["ok"] = step["returncode"] == 0
    result["step"] = step
    if bool(getattr(args, "json", False)):
        print(json_dumps(result))
    else:
        print(step["stdout"] or step["stderr"])
    return 0 if result["ok"] else 1


def command_memory_prune(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    config = _memory_config(root=root, workspace_config=workspace_config)
    binary = which("engram")
    if not binary:
        payload = _missing_binary_payload(config)
        _print_or_json(payload, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
        return 1

    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(":", "").replace("+00:00", "Z")
    source_path = root / ".flow" / "memory" / "prune" / f"{config['project']}-{stamp}-source.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    step = _run_engram([binary, "export", str(source_path)], config=config, run_command=run_command)
    payload = _load_export_file(source_path)
    observations = payload.get("observations")
    obs_list = observations if isinstance(observations, list) else []
    older_than_days = getattr(args, "older_than_days", None)
    keep_latest = getattr(args, "keep_latest", None)
    query = str(getattr(args, "query", "") or "")
    candidates = _prune_candidates(
        obs_list,
        query=query,
        older_than_days=older_than_days,
        keep_latest=keep_latest,
        now=datetime.now(timezone.utc),
    )
    result = {
        "ok": step["returncode"] == 0,
        "mode": "advisory",
        "destructive": False,
        "project": config["project"],
        "source_export": str(source_path),
        "observation_count": len(obs_list),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "criteria": {
            "query": query,
            "older_than_days": older_than_days,
            "keep_latest": keep_latest,
        },
        "notes": "Engram v1.11.0 exposes no safe granular delete; prune only reports candidates.",
        "step": step,
    }
    output = getattr(args, "output", None)
    if output:
        output_path = Path(str(output)).expanduser()
        if not output_path.is_absolute():
            output_path = root / output_path
    else:
        output_path = root / ".flow" / "memory" / "prune" / f"{config['project']}-{stamp}-report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    result["output"] = str(output_path)
    if bool(getattr(args, "json", False)):
        print(json_dumps(result))
    else:
        print(str(output_path))
    return 0 if result["ok"] else 1


def command_memory_save(
    args: object,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: RunCommand = subprocess.run,
) -> int:
    config = _memory_config(root=root, workspace_config=workspace_config)
    Path(config["data_dir"]).mkdir(parents=True, exist_ok=True)
    binary = which("engram")
    if not binary:
        payload = _missing_binary_payload(config)
        _print_or_json(payload, json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
        return 1

    title = str(getattr(args, "title", "") or "").strip()
    body = str(getattr(args, "body", "") or "")
    body_file = getattr(args, "body_file", None)
    if body_file:
        body = Path(str(body_file)).read_text(encoding="utf-8")
    if not body.strip():
        raise SystemExit("`flow memory save` requiere `--body` o `--body-file` con contenido.")

    step = _run_engram([binary, "save", title, body], config=config, run_command=run_command)
    safe_step = dict(step)
    safe_step["command"] = f"{binary} save {title!r} <body>"
    payload = {
        "ok": step["returncode"] == 0,
        "available": True,
        "project": config["project"],
        "data_dir": config["data_dir"],
        "db_path": config["db_path"],
        "title": title,
        "step": safe_step,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        print(step["stdout"] or step["stderr"])
    return 0 if payload["ok"] else 1
