from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


def provider_categories() -> list[str]:
    return ["release", "infra"]


def provider_section(payload: dict[str, object], category: str, *, manifest_name: str) -> dict[str, object]:
    section = payload.get(category)
    if not isinstance(section, dict):
        raise ValueError(f"Falta la seccion `{category}` en {manifest_name}.")
    return section


def provider_entries(payload: dict[str, object], category: str, *, manifest_name: str) -> dict[str, dict[str, object]]:
    section = provider_section(payload, category, manifest_name=manifest_name)
    providers = section.get("providers")
    if not isinstance(providers, dict):
        raise ValueError(f"`{category}.providers` debe ser un objeto en {manifest_name}.")
    normalized: dict[str, dict[str, object]] = {}
    for name, raw_config in providers.items():
        if not isinstance(raw_config, dict):
            raise ValueError(f"La configuracion de `{category}.{name}` debe ser un objeto.")
        normalized[str(name)] = raw_config
    return normalized


def provider_default(payload: dict[str, object], category: str, *, manifest_name: str) -> str:
    section = provider_section(payload, category, manifest_name=manifest_name)
    default_provider = section.get("default_provider")
    if not isinstance(default_provider, str) or not default_provider.strip():
        raise ValueError(f"`{category}.default_provider` debe ser un string no vacio.")
    if default_provider not in provider_entries(payload, category, manifest_name=manifest_name):
        raise ValueError(f"`{category}.default_provider` apunta a un provider inexistente: `{default_provider}`.")
    return default_provider


def provider_config(
    payload: dict[str, object],
    category: str,
    provider: str,
    *,
    manifest_name: str,
) -> dict[str, object]:
    entries = provider_entries(payload, category, manifest_name=manifest_name)
    if provider not in entries:
        available = ", ".join(sorted(entries))
        raise ValueError(f"No existe provider `{provider}` para `{category}`. Disponibles: {available}.")
    return entries[provider]


def provider_enabled(config: dict[str, object]) -> bool:
    return bool(config.get("enabled", True))


def provider_entrypoint_path(root: Path, config: dict[str, object]) -> Path:
    entrypoint = str(config.get("entrypoint", "")).strip()
    if not entrypoint:
        raise ValueError("Cada provider debe declarar `entrypoint`.")
    candidate = Path(entrypoint)
    if candidate.is_absolute():
        return candidate
    return (root / candidate).resolve()


def provider_requires(config: dict[str, object]) -> list[str]:
    raw = config.get("requires", [])
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
        raise ValueError("`requires` debe ser una lista de strings si existe.")
    return [item.strip() for item in raw]


def provider_static_env(config: dict[str, object]) -> dict[str, str]:
    raw = config.get("env", {})
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("`env` debe ser un objeto key/value si existe.")
    return {str(key): str(value) for key, value in raw.items()}


def provider_missing_runtime(config: dict[str, object]) -> list[str]:
    from shutil import which

    return [command for command in provider_requires(config) if which(command) is None]


def select_provider(
    root: Path,
    payload: dict[str, object],
    category: str,
    *,
    manifest_name: str,
    relativize,
    explicit: Optional[str] = None,
) -> tuple[str, dict[str, object]]:
    provider_name = explicit or provider_default(payload, category, manifest_name=manifest_name)
    config = provider_config(payload, category, provider_name, manifest_name=manifest_name)
    if not provider_enabled(config):
        raise SystemExit(f"El provider `{provider_name}` para `{category}` esta deshabilitado.")
    missing_runtime = provider_missing_runtime(config)
    if missing_runtime:
        joined = ", ".join(missing_runtime)
        raise SystemExit(f"Al provider `{provider_name}` para `{category}` le faltan comandos: {joined}.")
    entrypoint = provider_entrypoint_path(root, config)
    if not entrypoint.is_file():
        raise SystemExit(f"El entrypoint del provider `{provider_name}` no existe: {relativize(entrypoint)}.")
    return provider_name, config


def run_provider(
    root: Path,
    workspace_path: str,
    category: str,
    action: str,
    provider_name: str,
    config: dict[str, object],
    env: dict[str, str],
    *,
    relativize,
) -> dict[str, object]:
    entrypoint = provider_entrypoint_path(root, config)
    merged_env = os.environ.copy()
    merged_env.update(provider_static_env(config))
    merged_env.update(env)
    merged_env["FLOW_PROVIDER_CATEGORY"] = category
    merged_env["FLOW_PROVIDER_ACTION"] = action
    merged_env["FLOW_PROVIDER_NAME"] = provider_name
    merged_env["FLOW_WORKSPACE_ROOT"] = str(root.resolve())
    merged_env["FLOW_WORKSPACE_PATH"] = workspace_path

    execution = subprocess.run(
        ["bash", str(entrypoint.resolve())],
        cwd=root,
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = (execution.stdout + "\n" + execution.stderr).strip()
    return {
        "provider": provider_name,
        "entrypoint": relativize(entrypoint),
        "returncode": execution.returncode,
        "output_tail": "\n".join(combined.splitlines()[-40:]) if combined else "",
    }


def secrets_provider_entries(payload: dict[str, object], *, manifest_name: str) -> dict[str, dict[str, object]]:
    providers = payload.get("providers", {})
    if not isinstance(providers, dict):
        raise ValueError(f"`providers` debe ser un objeto en {manifest_name}.")
    normalized: dict[str, dict[str, object]] = {}
    for name, raw_config in providers.items():
        if not isinstance(raw_config, dict):
            raise ValueError(f"La configuracion del provider de secrets `{name}` debe ser un objeto.")
        normalized[str(name)] = raw_config
    return normalized


def secrets_default_provider(payload: dict[str, object], *, manifest_name: str) -> str:
    default_provider = payload.get("default_provider")
    if not isinstance(default_provider, str) or not default_provider.strip():
        raise ValueError(f"`default_provider` debe ser un string no vacio en {manifest_name}.")
    if default_provider not in secrets_provider_entries(payload, manifest_name=manifest_name):
        raise ValueError(f"`default_provider` apunta a un provider inexistente: `{default_provider}`.")
    return default_provider


def secrets_provider_config(
    payload: dict[str, object],
    provider: str,
    *,
    manifest_name: str,
) -> dict[str, object]:
    entries = secrets_provider_entries(payload, manifest_name=manifest_name)
    if provider not in entries:
        available = ", ".join(sorted(entries))
        raise ValueError(f"No existe provider de secrets `{provider}`. Disponibles: {available}.")
    return entries[provider]


def secrets_target_entries(payload: dict[str, object], *, manifest_name: str) -> dict[str, dict[str, object]]:
    targets = payload.get("targets", {})
    if not isinstance(targets, dict):
        raise ValueError(f"`targets` debe ser un objeto en {manifest_name}.")
    normalized: dict[str, dict[str, object]] = {}
    for name, raw_target in targets.items():
        if not isinstance(raw_target, dict):
            raise ValueError(f"El target `{name}` debe ser un objeto.")
        normalized[str(name)] = raw_target
    return normalized


def secrets_target_path(root: Path, raw_target: dict[str, object]) -> Path:
    raw_path = str(raw_target.get("path", "")).strip()
    if not raw_path:
        raise ValueError("Cada target de secrets debe declarar `path`.")
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise ValueError("Los targets de secrets deben usar rutas relativas al workspace.")
    resolved = (root / candidate).resolve()
    if root.resolve() not in [resolved, *resolved.parents]:
        raise ValueError("Los targets de secrets no pueden salir del workspace.")
    return resolved


def secrets_target_items(raw_target: dict[str, object]) -> dict[str, str]:
    items = raw_target.get("items", {})
    if not isinstance(items, dict):
        raise ValueError("`items` debe ser un objeto key/value.")
    normalized: dict[str, str] = {}
    for key, value in items.items():
        key_name = str(key).strip()
        if not key_name:
            raise ValueError("Los items de secrets deben tener claves no vacias.")
        normalized[key_name] = str(value)
    return normalized


def secrets_target_format(raw_target: dict[str, object]) -> str:
    value = str(raw_target.get("format", "dotenv")).strip().lower() or "dotenv"
    if value not in {"dotenv", "json"}:
        raise ValueError("`format` de secrets debe ser `dotenv` o `json`.")
    return value


def secrets_target_provider(payload: dict[str, object], raw_target: dict[str, object], *, manifest_name: str) -> str:
    explicit = str(raw_target.get("provider", "")).strip()
    return explicit or secrets_default_provider(payload, manifest_name=manifest_name)


def secrets_provider_enabled(config: dict[str, object]) -> bool:
    return bool(config.get("enabled", True))


def secrets_provider_requires(config: dict[str, object]) -> list[str]:
    raw = config.get("requires", [])
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
        raise ValueError("`requires` debe ser una lista de strings si existe.")
    return [item.strip() for item in raw]


def secrets_provider_env(config: dict[str, object]) -> dict[str, str]:
    raw = config.get("env", {})
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("`env` debe ser un objeto key/value si existe.")
    return {str(key): str(value) for key, value in raw.items()}


def secrets_provider_entrypoint(root: Path, config: dict[str, object]) -> Path:
    entrypoint = str(config.get("entrypoint", "")).strip()
    if not entrypoint:
        raise ValueError("Cada provider de secrets debe declarar `entrypoint`.")
    candidate = Path(entrypoint)
    if candidate.is_absolute():
        return candidate
    return (root / candidate).resolve()


def resolve_secret_value(
    root: Path,
    provider_name: str,
    config: dict[str, object],
    reference: str,
    *,
    relativize,
) -> tuple[Optional[str], Optional[str]]:
    entrypoint = secrets_provider_entrypoint(root, config)
    if not entrypoint.is_file():
        return None, f"El entrypoint de secrets `{provider_name}` no existe: {relativize(entrypoint)}."

    from shutil import which

    missing_runtime = [command for command in secrets_provider_requires(config) if which(command) is None]
    if missing_runtime:
        joined = ", ".join(missing_runtime)
        return None, f"Al provider de secrets `{provider_name}` le faltan comandos: {joined}."

    env = os.environ.copy()
    env.update(secrets_provider_env(config))
    env["FLOW_SECRET_PROVIDER"] = provider_name
    env["FLOW_SECRET_REF"] = reference
    execution = subprocess.run(
        ["bash", str(entrypoint.resolve())],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if execution.returncode != 0:
        combined = (execution.stdout + "\n" + execution.stderr).strip()
        tail = "\n".join(combined.splitlines()[-20:]) if combined else "sin salida"
        return None, f"`{provider_name}` no pudo resolver `{reference}`: {tail}"

    return execution.stdout.rstrip("\n"), None
