from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional


def load_compose_text(compose_file: Path) -> str:
    if not compose_file.is_file():
        raise SystemExit(f"Falta {compose_file}.")
    return compose_file.read_text(encoding="utf-8")


def write_compose_text(compose_file: Path, text: str) -> None:
    compose_file.write_text(text, encoding="utf-8")


def infer_compose_network_name(compose_text: str) -> str:
    match = re.search(r"^networks:\n(?:\s*\n)*  ([A-Za-z0-9_-]+):\s*$", compose_text, flags=re.MULTILINE)
    if match:
        return match.group(1)
    return "workspace"


def compose_service_exists(compose_text: str, service_name: str) -> bool:
    return re.search(rf"^  {re.escape(service_name)}:\s*$", compose_text, flags=re.MULTILINE) is not None


def format_compose_value(value: object, substitutions: dict[str, str]) -> object:
    if isinstance(value, str):
        return value.format(**substitutions)
    if isinstance(value, list):
        return [format_compose_value(item, substitutions) for item in value]
    if isinstance(value, dict):
        return {str(key): format_compose_value(item, substitutions) for key, item in value.items()}
    return value


def yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_./:-]+", text):
        return text
    return json.dumps(text, ensure_ascii=True)


def append_yaml_mapping(lines: list[str], indent: int, mapping: dict[str, object]) -> None:
    prefix = " " * indent
    for key, value in mapping.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            append_yaml_mapping(lines, indent + 2, value)
            continue
        if isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            append_yaml_list(lines, indent + 2, value)
            continue
        lines.append(f"{prefix}{key}: {yaml_scalar(value)}")


def append_yaml_list(lines: list[str], indent: int, items: list[object]) -> None:
    prefix = " " * indent
    for item in items:
        if isinstance(item, dict):
            lines.append(f"{prefix}-")
            append_yaml_mapping(lines, indent + 2, item)
            continue
        lines.append(f"{prefix}- {yaml_scalar(item)}")


def render_compose_service(
    service_name: str,
    repo_path: str,
    runtime: str,
    port: Optional[int],
    network_name: str,
    compose_config: dict[str, object],
) -> str:
    substitutions = {
        "network_name": network_name,
        "service_name": service_name,
        "repo_path": repo_path,
    }
    compose = format_compose_value(compose_config, substitutions)
    if not isinstance(compose, dict):
        raise SystemExit(f"El runtime `{runtime}` debe resolver `compose` como objeto.")

    dockerfile = str(compose.get("dockerfile", "")).strip()
    mount_target = str(compose.get("mount_target", "")).strip()
    working_dir = str(compose.get("working_dir", "")).strip()
    command = str(compose.get("command", "")).strip()
    if not all([dockerfile, mount_target, working_dir, command]):
        raise SystemExit(
            f"El runtime `{runtime}` debe declarar `compose.dockerfile`, `mount_target`, `working_dir` y `command`."
        )

    lines = [
        f"  # ── Added project: {service_name} ({runtime}) ───────────────────────────",
        f"  {service_name}:",
        "    build:",
        "      context: .",
        f"      dockerfile: {dockerfile}",
        "    volumes:",
        f"      - ../{repo_path}:{mount_target}:cached",
    ]

    extra_volumes = compose.get("extra_volumes", [])
    if isinstance(extra_volumes, list):
        lines.extend(f"      - {yaml_scalar(item)}" for item in extra_volumes)

    lines.extend(
        [
            f"    working_dir: {yaml_scalar(working_dir)}",
            f"    command: {yaml_scalar(command)}",
        ]
    )
    if port:
        lines.extend(["    ports:", f'      - "{port}:{port}"'])

    environment = compose.get("environment", {})
    if isinstance(environment, dict) and environment:
        lines.append("    environment:")
        append_yaml_mapping(lines, 6, environment)

    depends_on = compose.get("depends_on", {})
    if isinstance(depends_on, dict) and depends_on:
        lines.append("    depends_on:")
        append_yaml_mapping(lines, 6, depends_on)

    networks = compose.get("networks", [])
    if isinstance(networks, list) and networks:
        lines.append("    networks:")
        append_yaml_list(lines, 6, networks)

    return "\n".join(lines) + "\n\n"


def add_service_to_compose(
    compose_file: Path,
    service_name: str,
    repo_path: str,
    runtime: str,
    port: Optional[int],
    compose_config: dict[str, object],
) -> None:
    compose_text = load_compose_text(compose_file)
    if compose_service_exists(compose_text, service_name):
        raise SystemExit(f"El servicio `{service_name}` ya existe en {compose_file}.")

    comment_marker = re.search(r"\n  # [^\n]*\n  db:\n", compose_text)
    service_marker = re.search(r"\n  db:\n", compose_text)
    volumes_marker = re.search(r"\nvolumes:\n", compose_text)
    insertion_match = comment_marker or service_marker or volumes_marker
    if insertion_match is None:
        raise SystemExit(f"No pude encontrar un punto de insercion valido en {compose_file}.")

    network_name = infer_compose_network_name(compose_text)
    service_block = render_compose_service(service_name, repo_path, runtime, port, network_name, compose_config)
    head = compose_text[: insertion_match.start()].rstrip("\n")
    tail = compose_text[insertion_match.start() :].lstrip("\n")
    updated = f"{head}\n\n{service_block}{tail}"
    write_compose_text(compose_file, updated)


def detect_compose_context(
    compose_file: Path,
    default_project: str,
    *,
    running_inside_workspace: bool,
) -> dict[str, object]:
    resolved_compose_file = compose_file.resolve()
    context: dict[str, object] = {
        "project": default_project,
        "files": [resolved_compose_file],
        "active": False,
    }

    result = subprocess.run(
        ["docker", "compose", "ls", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return context

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return context

    if not isinstance(payload, list):
        return context

    for entry in payload:
        if not isinstance(entry, dict):
            continue
        config_files = [
            Path(raw_path).resolve()
            for raw_path in str(entry.get("ConfigFiles", "")).split(",")
            if raw_path
        ]
        if resolved_compose_file in config_files:
            context["project"] = str(entry.get("Name") or default_project)
            context["files"] = config_files or [resolved_compose_file]
            context["active"] = True
            return context

    if running_inside_workspace:
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("Name") or "") != str(context["project"]):
                continue
            config_files = [
                Path(raw_path).resolve()
                for raw_path in str(entry.get("ConfigFiles", "")).split(",")
                if raw_path
            ]
            context["files"] = config_files or context["files"]
            context["active"] = True
            return context

    return context


def compose_base_command(project: str, compose_file: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        str(project),
        "--project-directory",
        str(compose_file.resolve().parent),
        "-f",
        str(compose_file.resolve()),
    ]


def compose_exec_args(
    service: str,
    *,
    use_tty: bool,
    workdir: Optional[str] = None,
) -> list[str]:
    args = ["exec"]
    if not use_tty:
        args.append("-T")
    if workdir:
        args.extend(["-w", workdir])
    args.append(service)
    return args


def run_compose(base_command: list[str], cwd: Path, extra_args: list[str]) -> int:
    try:
        return subprocess.run(base_command + extra_args, cwd=cwd, check=False).returncode
    except FileNotFoundError as exc:
        raise SystemExit("No encontre `docker` en PATH para operar el stack del workspace.") from exc


def capture_compose(base_command: list[str], cwd: Path, extra_args: list[str]) -> dict[str, object]:
    try:
        result = subprocess.run(
            base_command + extra_args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SystemExit("No encontre `docker` en PATH para operar el stack del workspace.") from exc

    combined = (result.stdout + "\n" + result.stderr).strip()
    tail = "\n".join(combined.splitlines()[-40:]) if combined else ""
    return {
        "command": base_command + extra_args,
        "returncode": result.returncode,
        "output_tail": tail,
        "stdout": result.stdout,
    }


def workspace_executable_available(
    executable: str,
    *,
    running_inside_workspace: bool,
    workspace_service: str,
    workspace_path: str,
    compose_base: list[str],
    cwd: Path,
) -> bool:
    if running_inside_workspace:
        from shutil import which

        return which(executable) is not None

    command = compose_base + compose_exec_args(
        workspace_service,
        use_tty=False,
        workdir=workspace_path,
    )
    command.extend(["sh", "-lc", f"command -v {executable!s} >/dev/null 2>&1"])
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return False
    return result.returncode == 0
