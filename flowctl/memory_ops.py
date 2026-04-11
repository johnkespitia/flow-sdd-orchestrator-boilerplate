from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


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
    payload = {
        "ok": step["returncode"] == 0,
        "available": True,
        "project": config["project"],
        "data_dir": config["data_dir"],
        "db_path": config["db_path"],
        "query": query,
        "step": step,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        print(step["stdout"] or step["stderr"])
    return 0 if payload["ok"] else 1


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
