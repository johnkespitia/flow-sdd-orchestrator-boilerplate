from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


RUNTIMES_CONFIG_FILENAME = "workspace.runtimes.json"

REQUIRED_RUNTIME_KEYS = {
    "target_roots",
    "default_targets",
    "test_runner",
    "test_required_roots",
    "placeholder_dirs",
    "placeholder_files",
    "agent_skill_refs",
}

CI_STEP_KEYS = ("install", "lint", "test", "build")


class RuntimeCatalogError(Exception):
    pass


def render_runtime_file(content: object, repo_name: str) -> str:
    if isinstance(content, dict):
        text = json.dumps(content, indent=2, ensure_ascii=True) + "\n"
    else:
        text = str(content)
    return text.replace("{name}", repo_name)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeCatalogError(f"Falta {path.name} en el root del workspace.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeCatalogError(f"{path.name} no contiene JSON valido: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeCatalogError(f"{path.name} debe contener un objeto JSON.")
    return payload


def load_runtime_manifest(root: Path) -> dict[str, Any]:
    path = root / RUNTIMES_CONFIG_FILENAME
    payload = _read_json(path)
    runtimes = payload.get("runtimes")
    if not isinstance(runtimes, dict) or not runtimes:
        raise RuntimeCatalogError(f"{RUNTIMES_CONFIG_FILENAME} debe definir `runtimes`.")
    return payload


def available_runtime_names(root: Path) -> list[str]:
    manifest = load_runtime_manifest(root)
    runtimes = manifest["runtimes"]
    names = [
        str(name).strip()
        for name, config in runtimes.items()
        if isinstance(config, dict) and bool(config.get("enabled", True))
    ]
    return sorted(name for name in names if name)


def _available_runtime_names_by_kind(root: Path, runtime_kind: str) -> list[str]:
    names: list[str] = []
    for runtime in available_runtime_names(root):
        pack = resolve_runtime_pack(root, runtime, runtime, runtime)
        if str(pack.get("runtime_kind", "project")).strip().lower() == runtime_kind:
            names.append(runtime)
    return sorted(names)


def available_project_runtime_names(root: Path) -> list[str]:
    return _available_runtime_names_by_kind(root, "project")


def available_service_runtime_names(root: Path) -> list[str]:
    return _available_runtime_names_by_kind(root, "service")


def _runtime_pack_path(root: Path, runtime: str) -> Path:
    manifest = load_runtime_manifest(root)
    entry = manifest["runtimes"].get(runtime)
    if not isinstance(entry, dict):
        raise RuntimeCatalogError(f"No existe runtime `{runtime}` en {RUNTIMES_CONFIG_FILENAME}.")
    if not bool(entry.get("enabled", True)):
        raise RuntimeCatalogError(f"El runtime `{runtime}` esta deshabilitado.")

    source = str(entry.get("source", "")).strip()
    if not source:
        raise RuntimeCatalogError(f"El runtime `{runtime}` debe declarar `source`.")
    candidate = Path(source)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _format_runtime_value(value: Any, substitutions: dict[str, str]) -> Any:
    if isinstance(value, str):
        return re.sub(
            r"\{([A-Za-z0-9_]+)\}",
            lambda match: substitutions.get(match.group(1), match.group(0)),
            value,
        )
    if isinstance(value, list):
        return [_format_runtime_value(item, substitutions) for item in value]
    if isinstance(value, dict):
        return {str(key): _format_runtime_value(item, substitutions) for key, item in value.items()}
    return value


def _normalize_string_list(payload: dict[str, Any], key: str, runtime: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeCatalogError(f"El runtime `{runtime}` debe declarar `{key}` como lista de strings.")
    return [item for item in value if item]


def _normalize_ci_config(payload: dict[str, Any], runtime: str) -> dict[str, list[str]]:
    value = payload.get("ci", {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuntimeCatalogError(f"El runtime `{runtime}` debe declarar `ci` como objeto.")

    commands: dict[str, list[str]] = {}
    for step, raw_command in value.items():
        if step not in CI_STEP_KEYS:
            raise RuntimeCatalogError(
                f"El runtime `{runtime}` declara un step CI no soportado: `{step}`."
            )
        if raw_command is None:
            continue
        if not isinstance(raw_command, list) or not all(isinstance(part, str) for part in raw_command):
            raise RuntimeCatalogError(
                f"El runtime `{runtime}` debe declarar `ci.{step}` como lista de strings."
            )
        command = [part for part in raw_command if part]
        if not command:
            continue
        commands[step] = command
    return commands


def _normalize_runtime_bindings(payload: dict[str, Any], runtime: str) -> dict[str, dict[str, Any]]:
    value = payload.get("bindings", {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuntimeCatalogError(f"El runtime `{runtime}` debe declarar `bindings` como objeto.")

    bindings: dict[str, dict[str, Any]] = {}
    for raw_service_runtime, raw_binding in value.items():
        service_runtime = str(raw_service_runtime).strip()
        if not service_runtime:
            raise RuntimeCatalogError(f"El runtime `{runtime}` no puede declarar un binding con key vacia.")
        if not isinstance(raw_binding, dict):
            raise RuntimeCatalogError(
                f"El runtime `{runtime}` debe declarar `bindings.{service_runtime}` como objeto."
            )
        bindings[service_runtime] = dict(raw_binding)
    return bindings


def _normalize_runtime_pack(runtime: str, payload: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_RUNTIME_KEYS if key not in payload]
    if missing:
        raise RuntimeCatalogError(
            f"El runtime `{runtime}` debe declarar: {', '.join(sorted(missing))}."
        )

    if not isinstance(payload.get("placeholder_files"), dict):
        raise RuntimeCatalogError(f"El runtime `{runtime}` debe declarar `placeholder_files` como objeto.")

    compose = payload.get("compose")
    if compose is not None and not isinstance(compose, dict):
        raise RuntimeCatalogError(f"El runtime `{runtime}` debe declarar `compose` como objeto o null.")

    runtime_kind = str(payload.get("runtime_kind", "project")).strip().lower() or "project"
    if runtime_kind not in {"project", "service"}:
        raise RuntimeCatalogError(f"El runtime `{runtime}` debe declarar `runtime_kind` como `project` o `service`.")

    normalized = {
        "runtime_kind": runtime_kind,
        "target_roots": _normalize_string_list(payload, "target_roots", runtime),
        "default_targets": _normalize_string_list(payload, "default_targets", runtime),
        "test_runner": str(payload.get("test_runner", "none")).strip().lower() or "none",
        "test_hint": payload.get("test_hint"),
        "test_required_roots": _normalize_string_list(payload, "test_required_roots", runtime),
        "placeholder_dirs": _normalize_string_list(payload, "placeholder_dirs", runtime),
        "placeholder_files": dict(payload.get("placeholder_files", {})),
        "agent_skill_refs": _normalize_string_list(payload, "agent_skill_refs", runtime),
        "ci": _normalize_ci_config(payload, runtime),
        "bindings": _normalize_runtime_bindings(payload, runtime),
        "compose": compose,
        "notes": str(payload.get("notes", "")).strip(),
    }
    return normalized


def resolve_runtime_pack(root: Path, runtime: str, repo_name: str, repo_path: str) -> dict[str, Any]:
    path = _runtime_pack_path(root, runtime)
    payload = _read_json(path)
    normalized = _normalize_runtime_pack(runtime, payload)
    substitutions = {"name": repo_name, "path": repo_path}

    test_hint = normalized["test_hint"]
    if isinstance(test_hint, str):
        test_hint = _format_runtime_value(test_hint, substitutions)

    placeholder_files = {
        relative_path: render_runtime_file(_format_runtime_value(content, substitutions), repo_name)
        for relative_path, content in normalized["placeholder_files"].items()
    }

    compose = normalized["compose"]
    if isinstance(compose, dict):
        compose = _format_runtime_value(compose, substitutions)

    return {
        "runtime": runtime,
        "runtime_kind": normalized["runtime_kind"],
        "target_roots": _format_runtime_value(normalized["target_roots"], substitutions),
        "default_targets": _format_runtime_value(normalized["default_targets"], substitutions),
        "test_runner": normalized["test_runner"],
        "test_hint": test_hint,
        "test_required_roots": _format_runtime_value(normalized["test_required_roots"], substitutions),
        "placeholder_dirs": _format_runtime_value(normalized["placeholder_dirs"], substitutions),
        "placeholder_files": placeholder_files,
        "agent_skill_refs": normalized["agent_skill_refs"],
        "ci": _format_runtime_value(normalized["ci"], substitutions),
        "bindings": _format_runtime_value(normalized["bindings"], substitutions),
        "compose": compose,
        "notes": normalized["notes"],
        "source": path,
    }
