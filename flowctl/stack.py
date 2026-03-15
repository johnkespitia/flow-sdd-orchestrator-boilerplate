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


def compose_section_match(compose_text: str, section_name: str) -> Optional[re.Match[str]]:
    return re.search(
        rf"^{re.escape(section_name)}:\n(?P<body>.*?)(?=^[A-Za-z0-9_-]+:\n|\Z)",
        compose_text,
        flags=re.MULTILINE | re.DOTALL,
    )


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


def render_service_block(service_name: str, service_config: dict[str, object], *, comment: str) -> str:
    lines = [f"  # ── {comment} ───────────────────────────", f"  {service_name}:"]

    build = service_config.get("build")
    if isinstance(build, dict) and build:
        lines.append("    build:")
        append_yaml_mapping(lines, 6, build)

    image = service_config.get("image")
    if image:
        lines.append(f"    image: {yaml_scalar(image)}")

    restart = service_config.get("restart")
    if restart:
        lines.append(f"    restart: {yaml_scalar(restart)}")

    user = service_config.get("user")
    if user:
        lines.append(f"    user: {yaml_scalar(user)}")

    entrypoint = service_config.get("entrypoint")
    if entrypoint:
        if isinstance(entrypoint, list):
            lines.append("    entrypoint:")
            append_yaml_list(lines, 6, entrypoint)
        else:
            lines.append(f"    entrypoint: {yaml_scalar(entrypoint)}")

    volumes = service_config.get("volumes", [])
    if isinstance(volumes, list) and volumes:
        lines.append("    volumes:")
        append_yaml_list(lines, 6, volumes)

    working_dir = service_config.get("working_dir")
    if working_dir:
        lines.append(f"    working_dir: {yaml_scalar(working_dir)}")

    command = service_config.get("command")
    if command:
        if isinstance(command, list):
            lines.append("    command:")
            append_yaml_list(lines, 6, command)
        else:
            lines.append(f"    command: {yaml_scalar(command)}")

    ports = service_config.get("ports", [])
    if isinstance(ports, list) and ports:
        lines.append("    ports:")
        append_yaml_list(lines, 6, ports)

    environment = service_config.get("environment", {})
    if isinstance(environment, dict) and environment:
        lines.append("    environment:")
        append_yaml_mapping(lines, 6, environment)

    depends_on = service_config.get("depends_on", {})
    if isinstance(depends_on, dict) and depends_on:
        lines.append("    depends_on:")
        append_yaml_mapping(lines, 6, depends_on)

    healthcheck = service_config.get("healthcheck", {})
    if isinstance(healthcheck, dict) and healthcheck:
        lines.append("    healthcheck:")
        append_yaml_mapping(lines, 6, healthcheck)

    networks = service_config.get("networks", [])
    if isinstance(networks, list) and networks:
        lines.append("    networks:")
        append_yaml_list(lines, 6, networks)

    return "\n".join(lines) + "\n\n"


def render_runtime_service(
    service_name: str,
    repo_path: str,
    runtime: str,
    port: Optional[int],
    network_name: str,
    compose_config: dict[str, object],
) -> tuple[dict[str, object], dict[str, str]]:
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
    command = compose.get("command")
    if not all([dockerfile, mount_target, working_dir, command]):
        raise SystemExit(
            f"El runtime `{runtime}` debe declarar `compose.dockerfile`, `mount_target`, `working_dir` y `command`."
        )

    service_payload: dict[str, object] = {
        "build": {"context": ".", "dockerfile": dockerfile},
        "volumes": [f"../{repo_path}:{mount_target}:cached"],
        "working_dir": working_dir,
        "command": command,
    }

    extra_volumes = compose.get("extra_volumes", [])
    if isinstance(extra_volumes, list) and extra_volumes:
        service_payload["volumes"].extend(extra_volumes)
    if port:
        service_payload["ports"] = [f"{port}:{port}"]

    for field in ["environment", "depends_on", "healthcheck", "networks", "entrypoint", "restart", "user"]:
        value = compose.get(field)
        if value:
            service_payload[field] = value

    return service_payload, substitutions


def insert_service_blocks(compose_text: str, blocks: list[str]) -> str:
    insertion_match = re.search(r"\nvolumes:\n|\nnetworks:\n", compose_text)
    if insertion_match is None:
        compose_text = compose_text.rstrip() + "\n\nvolumes:\n\nnetworks:\n  workspace:\n"
        insertion_match = re.search(r"\nvolumes:\n|\nnetworks:\n", compose_text)
        if insertion_match is None:
            raise SystemExit("No pude construir secciones `volumes`/`networks` en docker-compose.yml.")

    head = compose_text[: insertion_match.start()].rstrip("\n")
    tail = compose_text[insertion_match.start() :].lstrip("\n")
    return f"{head}\n\n{''.join(blocks)}{tail}"


def ensure_named_volumes(compose_text: str, volume_names: list[str]) -> str:
    if not volume_names:
        return compose_text

    section = compose_section_match(compose_text, "volumes")
    if section is None:
        networks = compose_section_match(compose_text, "networks")
        insertion_index = networks.start() if networks is not None else len(compose_text)
        head = compose_text[:insertion_index].rstrip("\n")
        tail = compose_text[insertion_index:].lstrip("\n")
        compose_text = f"{head}\n\nvolumes:\n{tail if tail else ''}"
        section = compose_section_match(compose_text, "volumes")
        if section is None:
            raise SystemExit("No pude crear la seccion `volumes` en docker-compose.yml.")

    body = section.group("body")
    existing = set(re.findall(r"^  ([A-Za-z0-9_.-]+):\s*$", body, flags=re.MULTILINE))
    additions = [name for name in volume_names if name not in existing]
    if not additions:
        return compose_text

    insertion_index = section.end("body")
    block = "".join(f"  {name}:\n" for name in additions)
    return compose_text[:insertion_index] + block + compose_text[insertion_index:]


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

    network_name = infer_compose_network_name(compose_text)
    runtime_service, substitutions = render_runtime_service(service_name, repo_path, runtime, port, network_name, compose_config)
    blocks = [render_service_block(service_name, runtime_service, comment=f"Added project: {service_name} ({runtime})")]

    support_services = compose_config.get("support_services", {})
    if isinstance(support_services, dict):
        for support_name, support_config in support_services.items():
            if compose_service_exists(compose_text, support_name):
                continue
            if not isinstance(support_config, dict):
                raise SystemExit(
                    f"El runtime `{runtime}` debe declarar `compose.support_services.{support_name}` como objeto."
                )
            formatted_support = format_compose_value(support_config, substitutions)
            if not isinstance(formatted_support, dict):
                raise SystemExit(
                    f"El runtime `{runtime}` debe resolver `compose.support_services.{support_name}` como objeto."
                )
            blocks.append(render_service_block(support_name, formatted_support, comment=f"Runtime support: {support_name} ({runtime})"))

    updated = insert_service_blocks(compose_text, blocks)

    named_volumes_raw = compose_config.get("named_volumes", [])
    named_volumes = format_compose_value(named_volumes_raw, substitutions)
    if isinstance(named_volumes, list):
        updated = ensure_named_volumes(updated, [str(name) for name in named_volumes])
    write_compose_text(compose_file, updated)


def add_standalone_service_to_compose(
    compose_file: Path,
    service_name: str,
    runtime: str,
    compose_config: dict[str, object],
) -> None:
    compose_text = load_compose_text(compose_file)
    if compose_service_exists(compose_text, service_name):
        raise SystemExit(f"El servicio `{service_name}` ya existe en {compose_file}.")

    substitutions = {
        "network_name": infer_compose_network_name(compose_text),
        "service_name": service_name,
        "repo_path": service_name,
    }
    formatted = format_compose_value(compose_config, substitutions)
    if not isinstance(formatted, dict):
        raise SystemExit(f"El runtime `{runtime}` debe resolver `compose` como objeto.")

    support_services = formatted.pop("support_services", {})
    named_volumes = formatted.pop("named_volumes", [])
    blocks = [render_service_block(service_name, formatted, comment=f"Added service: {service_name} ({runtime})")]

    if isinstance(support_services, dict):
        for support_name, support_config in support_services.items():
            if compose_service_exists(compose_text, support_name):
                continue
            if not isinstance(support_config, dict):
                raise SystemExit(
                    f"El runtime `{runtime}` debe declarar `compose.support_services.{support_name}` como objeto."
                )
            formatted_support = format_compose_value(support_config, substitutions)
            if not isinstance(formatted_support, dict):
                raise SystemExit(
                    f"El runtime `{runtime}` debe resolver `compose.support_services.{support_name}` como objeto."
                )
            blocks.append(render_service_block(support_name, formatted_support, comment=f"Runtime support: {support_name} ({runtime})"))

    updated = insert_service_blocks(compose_text, blocks)
    if isinstance(named_volumes, list):
        updated = ensure_named_volumes(updated, [str(name) for name in named_volumes])
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
