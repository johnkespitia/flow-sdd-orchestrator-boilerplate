#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "workspace.config.json"
TEXT_EXTENSIONS = {".md", ".json", ".yml", ".yaml", ".txt"}
BOOTSTRAP_PROFILES = ("master", "slave")


def load_config(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_repo_paths(config: dict[str, object]) -> dict[str, str]:
    return {
        repo: str(repo_config.get("path", ".")).strip()
        for repo, repo_config in config["repos"].items()
    }


def ensure_clean_destination(destination: Path, force: bool) -> None:
    if destination.exists() and any(destination.iterdir()) and not force:
        raise SystemExit(f"{destination} ya existe y no esta vacio. Usa --force para reemplazarlo.")
    destination.mkdir(parents=True, exist_ok=True)


def copy_template(source_config: dict[str, object], destination: Path, *, profile: str) -> None:
    excluded_repo_paths = {
        path
        for repo, path in source_repo_paths(source_config).items()
        if repo != source_config["project"]["root_repo"] and path not in {"", "."}
    }

    def ignore(directory: str, names: list[str]) -> set[str]:
        current = Path(directory)
        ignored = {".git", ".worktrees", "_bmad-output", "__pycache__", ".pytest_cache", "node_modules", "vendor"}
        if current.resolve() == ROOT.resolve():
            ignored.update(excluded_repo_paths)
            for legacy_path in ("backend", "frontend"):
                if legacy_path not in excluded_repo_paths:
                    ignored.add(legacy_path)
            if profile == "slave":
                # En modo slave no levantamos control-plane central.
                ignored.add("gateway")
        if current.name == ".flow":
            ignored.update({"state", "plans", "reports", "runs"})
        if current.name == "data" and current.parent.name == "gateway":
            ignored.update({name for name in names if name.endswith(".db") or name.endswith(".log")})
        return ignored.intersection(names)

    shutil.copytree(ROOT, destination, dirs_exist_ok=True, ignore=ignore)


def reset_flow_state(destination: Path) -> None:
    placeholders = {
        destination / ".flow" / "state" / ".gitkeep": "",
        destination / ".flow" / "plans" / ".gitkeep": "",
        destination / ".flow" / "reports" / ".gitkeep": "",
        destination / ".flow" / "runs" / ".gitignore": "*\n!.gitignore\n",
    }
    for path, content in placeholders.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def remove_repo_specific_files(destination: Path) -> None:
    for relative_path in [".gitmodules"]:
        target = destination / relative_path
        if target.exists():
            target.unlink()


def build_repo_config(path: str, kind: str, source_repo: dict[str, object]) -> dict[str, object]:
    repo_config = dict(source_repo)
    repo_config["path"] = path
    repo_config["kind"] = kind
    if kind == "root":
        repo_config["slice_prefix"] = repo_config.get("slice_prefix", "root")
        repo_config["compose_service"] = str(repo_config.get("compose_service", "workspace"))

    default_targets = list(repo_config.get("default_targets", []))
    target_roots = list(repo_config.get("target_roots", []))
    test_hint = repo_config.get("test_hint")

    source_path = str(source_repo.get("path", ".")).strip()
    if source_path not in {"", "."}:
        default_targets = [target.replace(f"../../{source_path}/", f"../../{path}/") for target in default_targets]
        if isinstance(test_hint, str):
            test_hint = test_hint.replace(f"../../{source_path}/", f"../../{path}/")

    if kind == "root":
        if "workspace.config.json" not in target_roots:
            target_roots.append("workspace.config.json")
        if "workspace.capabilities.json" not in target_roots:
            target_roots.append("workspace.capabilities.json")
        if "workspace.providers.json" not in target_roots:
            target_roots.append("workspace.providers.json")
        if "workspace.runtimes.json" not in target_roots:
            target_roots.append("workspace.runtimes.json")
        if "workspace.secrets.json" not in target_roots:
            target_roots.append("workspace.secrets.json")
        if "workspace.stack.json" not in target_roots:
            target_roots.append("workspace.stack.json")
        if "workspace.skills.json" not in target_roots:
            target_roots.append("workspace.skills.json")
        if "flowctl" not in target_roots:
            target_roots.append("flowctl")
        if "capabilities" not in target_roots:
            target_roots.append("capabilities")
        if "runtimes" not in target_roots:
            target_roots.append("runtimes")
        if "scripts" not in target_roots:
            target_roots.append("scripts")

    repo_config["default_targets"] = default_targets
    repo_config["target_roots"] = target_roots
    if test_hint:
        repo_config["test_hint"] = test_hint
    return repo_config


def rewrite_workspace_config(
    destination: Path,
    source_config: dict[str, object],
    project_name: str,
    root_repo: str,
) -> None:
    root_source = source_config["repos"][source_config["project"]["root_repo"]]

    destination_config = {
        "project": {
            "display_name": project_name,
            "root_repo": root_repo,
        },
        "repos": {
            root_repo: build_repo_config(".", "root", root_source),
        },
    }

    (destination / "workspace.config.json").write_text(
        json.dumps(destination_config, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def patch_devcontainer(destination: Path, project_name: str) -> None:
    devcontainer_json = destination / ".devcontainer" / "devcontainer.json"
    payload = json.loads(devcontainer_json.read_text(encoding="utf-8"))
    payload["name"] = project_name
    devcontainer_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rewrite_text_file(path: Path, replacements: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    updated = text
    for source, target in replacements.items():
        updated = updated.replace(source, target)
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def rewrite_project_texts(
    destination: Path,
    source_config: dict[str, object],
    project_name: str,
    root_repo: str,
) -> None:
    source_project_name = str(source_config["project"].get("display_name", ROOT.name))
    source_root_repo = str(source_config["project"]["root_repo"])

    replacements = {
        source_project_name: project_name,
        source_root_repo: root_repo,
    }

    for relative_root in [
        "README.md",
        "flow",
        "templates",
        "specs",
        "docs",
        ".tessl",
        ".github",
        "scripts",
        "flowctl",
        "capabilities",
        "runtimes",
        "workspace.capabilities.json",
        "workspace.config.json",
        "workspace.providers.json",
        "workspace.runtimes.json",
        "workspace.secrets.json",
        "workspace.skills.json",
        "workspace.stack.json",
        "Makefile",
    ]:
        target = destination / relative_root
        if target.is_file():
            rewrite_text_file(target, replacements)
            continue

        for path in target.rglob("*"):
            if path.is_dir():
                continue
            if path.suffix in TEXT_EXTENSIONS or path.name in {"Makefile", "flow", "AGENTS.md"}:
                rewrite_text_file(path, replacements)


def git_init(destination: Path) -> None:
    subprocess.run(["git", "init"], cwd=destination, check=True)
    hooks_dir = destination / "scripts" / "git-hooks"
    if hooks_dir.is_dir():
        subprocess.run(["git", "config", "core.hooksPath", "scripts/git-hooks"], cwd=destination, check=True)
    subprocess.run(["git", "add", "."], cwd=destination, check=True)
    subprocess.run(["git", "commit", "-m", "chore: initialize workspace from boilerplate"], cwd=destination, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spawn a clean spec-driven workspace from this repo.")
    parser.add_argument("destination", help="Directorio donde nacerá el nuevo workspace.")
    parser.add_argument("--project-name", required=True, help="Nombre visible del proyecto.")
    parser.add_argument("--root-repo", required=True, help="Nombre del repo root del nuevo workspace.")
    parser.add_argument(
        "--backend-repo",
        default=None,
        help="Deprecated. El boilerplate ahora nace sin proyectos de implementacion; usa `flow add-project` despues.",
    )
    parser.add_argument(
        "--frontend-repo",
        default=None,
        help="Deprecated. El boilerplate ahora nace sin proyectos de implementacion; usa `flow add-project` despues.",
    )
    parser.add_argument("--force", action="store_true", help="Permitir escribir sobre un directorio existente.")
    parser.add_argument("--git-init", action="store_true", help="Inicializar Git y crear un primer commit.")
    parser.add_argument(
        "--profile",
        choices=BOOTSTRAP_PROFILES,
        default="master",
        help="Perfil de bootstrap: `master` (control-plane con gateway) o `slave` (runner conectado a gateway remoto).",
    )
    parser.add_argument(
        "--gateway-url",
        default="",
        help="Solo profile=slave. URL base del gateway master (ej: https://gateway.example.com).",
    )
    parser.add_argument(
        "--gateway-token",
        default="",
        help="Solo profile=slave. Token opcional para autenticación hacia gateway master.",
    )
    parser.add_argument(
        "--skip-gateway-check",
        action="store_true",
        help="Solo profile=slave. Omite validación HTTP /healthz del gateway remoto.",
    )
    return parser.parse_args()


def _normalize_gateway_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return value
    parsed = urlparse(value)
    if not parsed.scheme:
        value = f"http://{value}"
        parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise SystemExit("Gateway URL invalida. Usa esquema http:// o https://.")
    if not parsed.netloc:
        raise SystemExit("Gateway URL invalida. Falta host.")
    return value.rstrip("/")


def _prompt_gateway_url() -> str:
    print("")
    print("[slave setup] Configuracion de gateway remoto")
    print("Ingresa la URL base del gateway master (ej: https://gateway.example.internal)")
    raw = input("Gateway URL: ").strip()
    return _normalize_gateway_url(raw)


def _check_gateway_health(base_url: str, timeout_seconds: int = 5) -> None:
    health_url = f"{base_url}/healthz"
    request = Request(health_url, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - URL provista por operador
            if int(getattr(response, "status", 0)) != 200:
                raise SystemExit(f"No se pudo validar gateway ({health_url}): status {getattr(response, 'status', 'n/a')}")
    except URLError as exc:
        raise SystemExit(f"No se pudo conectar a {health_url}: {exc}") from exc


def _persist_slave_gateway_connection(destination: Path, gateway_url: str, gateway_token: str) -> None:
    config_path = destination / "workspace.config.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    gateway_cfg = payload.get("gateway")
    if not isinstance(gateway_cfg, dict):
        gateway_cfg = {}
    gateway_cfg["connection"] = {
        "mode": "remote",
        "base_url": gateway_url,
    }
    payload["gateway"] = gateway_cfg
    config_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    env_gateway = destination / ".env.gateway"
    lines = [
        "# Generado por scripts/bootstrap_workspace.py (profile=slave)",
        f"SOFTOS_GATEWAY_URL={gateway_url}",
    ]
    token = gateway_token.strip()
    if token:
        lines.append(f"SOFTOS_GATEWAY_API_TOKEN={token}")
    else:
        lines.append("# SOFTOS_GATEWAY_API_TOKEN=<set-me>")
    env_gateway.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    destination = Path(args.destination).expanduser().resolve()
    source_config = load_config(CONFIG_FILE)

    ensure_clean_destination(destination, args.force)
    copy_template(source_config, destination, profile=args.profile)
    reset_flow_state(destination)
    remove_repo_specific_files(destination)
    rewrite_workspace_config(
        destination,
        source_config,
        project_name=args.project_name,
        root_repo=args.root_repo,
    )
    patch_devcontainer(destination, args.project_name)
    rewrite_project_texts(
        destination,
        source_config,
        project_name=args.project_name,
        root_repo=args.root_repo,
    )

    if args.profile == "slave":
        gateway_url = _normalize_gateway_url(args.gateway_url)
        if not gateway_url:
            gateway_url = _prompt_gateway_url()
        if not args.skip_gateway_check:
            _check_gateway_health(gateway_url)
        _persist_slave_gateway_connection(destination, gateway_url, args.gateway_token)

    if args.git_init:
        git_init(destination)

    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
