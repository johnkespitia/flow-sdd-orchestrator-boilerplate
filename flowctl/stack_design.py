from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional

import yaml

from flowctl.specs import (
    frontmatter_status_allows_execution,
    frontmatter_status_is_terminal,
    normalize_frontmatter_status,
)


STACK_CONFIG_FILENAME = "workspace.stack.json"
CAPABILITIES_CONFIG_FILENAME = "workspace.capabilities.json"


class StackDesignError(Exception):
    pass


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise StackDesignError(f"Falta {path.name} en el root del workspace.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StackDesignError(f"{path.name} no contiene JSON valido para `{label}`: {exc}") from exc
    if not isinstance(payload, dict):
        raise StackDesignError(f"{path.name} debe contener un objeto JSON.")
    return payload


def load_stack_manifest(path: Path) -> dict[str, object]:
    payload = _read_json_object(path, "stack")
    if not isinstance(payload.get("projects", []), list):
        raise StackDesignError(f"{path.name} debe definir `projects` como lista.")
    if not isinstance(payload.get("services", []), list):
        raise StackDesignError(f"{path.name} debe definir `services` como lista.")
    if not isinstance(payload.get("capabilities", []), list):
        raise StackDesignError(f"{path.name} debe definir `capabilities` como lista.")
    return payload


def write_stack_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _emit_stack_error(message: str, *, json_mode: bool, json_dumps: Callable[[object], str]) -> int:
    if json_mode:
        print(json_dumps({"error": message}))
    else:
        print(message)
    return 1


def load_capabilities_manifest(path: Path) -> dict[str, object]:
    payload = _read_json_object(path, "capabilities")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict) or not capabilities:
        raise StackDesignError(f"{path.name} debe definir `capabilities`.")
    return payload


def resolve_capability_pack(root: Path, capability: str) -> tuple[dict[str, object], Path]:
    manifest = load_capabilities_manifest(root / CAPABILITIES_CONFIG_FILENAME)
    entry = manifest["capabilities"].get(capability)
    if not isinstance(entry, dict):
        raise StackDesignError(f"No existe capability `{capability}` en {CAPABILITIES_CONFIG_FILENAME}.")
    if not bool(entry.get("enabled", True)):
        raise StackDesignError(f"La capability `{capability}` esta deshabilitada.")
    source = str(entry.get("source", "")).strip()
    if not source:
        raise StackDesignError(f"La capability `{capability}` debe declarar `source`.")
    path = Path(source)
    if not path.is_absolute():
        path = root / path
    payload = _read_json_object(path.resolve(), capability)
    return payload, path.resolve()


def requested_capabilities(manifest: dict[str, object]) -> list[str]:
    names = [str(item).strip() for item in manifest.get("capabilities", []) if str(item).strip()]
    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        for item in project.get("capabilities", []):
            candidate = str(item).strip()
            if candidate and candidate not in names:
                names.append(candidate)
    return names


def available_capability_names(root: Path) -> list[str]:
    manifest = load_capabilities_manifest(root / CAPABILITIES_CONFIG_FILENAME)
    names = [
        str(name).strip()
        for name, config in manifest.get("capabilities", {}).items()
        if isinstance(config, dict) and bool(config.get("enabled", True))
    ]
    return sorted(name for name in names if name)


def _is_yaml_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _normalize_optional_mapping(value: Any, label: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise StackDesignError(f"`{label}` debe declararse como objeto.")

    payload: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not key:
            raise StackDesignError(f"`{label}` no puede usar keys vacias.")
        if not _is_yaml_scalar(raw_value):
            raise StackDesignError(f"`{label}.{key}` debe usar un valor escalar YAML.")
        payload[key] = raw_value
    return payload


def _default_project_name(prompt: str, kind: str) -> str:
    if kind == "api":
        return "api"
    if kind == "web":
        return "web"
    match = re.search(r"\b(llamad[oa]|nombre|name)\s+([A-Za-z0-9_-]+)", prompt, flags=re.IGNORECASE)
    if match:
        return match.group(2).strip().lower()
    return kind


def _default_port(runtime: str) -> Optional[int]:
    return {
        "go-api": 8080,
        "php": 8000,
        "pnpm": 5173,
    }.get(runtime)


def _runtime_compose_config(
    *,
    root: Path,
    runtime: str,
    repo_name: str,
    repo_path: str,
    resolve_runtime_pack,
) -> dict[str, object]:
    runtime_pack = resolve_runtime_pack(root, runtime, repo_name, repo_path)
    compose = runtime_pack.get("compose")
    return dict(compose) if isinstance(compose, dict) else {}


def _runtime_default_port(
    *,
    root: Path,
    runtime: str,
    repo_name: str,
    repo_path: str,
    resolve_runtime_pack,
) -> Optional[int]:
    compose = _runtime_compose_config(
        root=root,
        runtime=runtime,
        repo_name=repo_name,
        repo_path=repo_path,
        resolve_runtime_pack=resolve_runtime_pack,
    )
    default_port = compose.get("default_port")
    if isinstance(default_port, int) and not isinstance(default_port, bool):
        return default_port
    return _default_port(runtime)


def _runtime_service_defaults(
    *,
    root: Path,
    runtime: str,
    service_name: str,
    resolve_runtime_pack,
) -> dict[str, object]:
    compose = _runtime_compose_config(
        root=root,
        runtime=runtime,
        repo_name=service_name,
        repo_path=service_name,
        resolve_runtime_pack=resolve_runtime_pack,
    )
    payload: dict[str, object] = {}

    environment = compose.get("environment")
    if isinstance(environment, dict):
        payload["env"] = {str(key): value for key, value in environment.items() if _is_yaml_scalar(value)}

    ports = compose.get("ports")
    if isinstance(ports, list):
        items = []
        for item in ports:
            if isinstance(item, bool) or not isinstance(item, (str, int)):
                continue
            if isinstance(item, str) and not item.strip():
                continue
            items.append(item)
        if items:
            payload["ports"] = items

    volumes = compose.get("volumes")
    if isinstance(volumes, list):
        items = [str(item).strip() for item in volumes if isinstance(item, str) and str(item).strip()]
        if items:
            payload["volumes"] = items

    return payload


def _merge_dict(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _format_binding_value(value: Any, substitutions: dict[str, str]) -> Any:
    if isinstance(value, str):
        return re.sub(
            r"\{([A-Za-z0-9_]+)\}",
            lambda match: substitutions.get(match.group(1), match.group(0)),
            value,
        )
    if isinstance(value, list):
        return [_format_binding_value(item, substitutions) for item in value]
    if isinstance(value, dict):
        return {
            str(_format_binding_value(key, substitutions)): _format_binding_value(item, substitutions)
            for key, item in value.items()
        }
    return value


def _runtime_binding_override(
    runtime_pack: dict[str, object],
    *,
    service_runtime: str,
    service_name: str,
) -> dict[str, object]:
    bindings = runtime_pack.get("bindings", {})
    if not isinstance(bindings, dict):
        return {}

    raw_override = bindings.get(service_runtime)
    if raw_override is None:
        raw_override = bindings.get(service_name)
    if not isinstance(raw_override, dict):
        return {}

    formatted = _format_binding_value(
        raw_override,
        {
            "service_name": service_name,
            "service_runtime": service_runtime,
        },
    )
    return formatted if isinstance(formatted, dict) else {}


def _binding_environment(override: dict[str, object]) -> dict[str, object]:
    environment = override.get("environment")
    if not isinstance(environment, dict):
        return {}
    return {str(key): value for key, value in environment.items() if _is_yaml_scalar(value)}


def design_stack_from_prompt(prompt: str, *, root: Path, resolve_runtime_pack) -> dict[str, object]:
    lowered = prompt.lower()
    manifest: dict[str, object] = {
        "schema_version": 1,
        "source_prompt": prompt.strip(),
        "projects": [],
        "services": [],
        "capabilities": [],
        "notes": [],
    }

    projects: list[dict[str, object]] = []
    services: list[dict[str, object]] = []
    capabilities: list[str] = []

    api_runtime: Optional[str] = None
    if any(keyword in lowered for keyword in ["golang", "go api", "api en go", "api in go", "api en golang"]):
        api_runtime = "go-api"
    elif any(keyword in lowered for keyword in ["laravel", "php api", "api en php", "api en laravel"]):
        api_runtime = "php"

    if api_runtime is not None:
        api_name = _default_project_name(prompt, "api")
        api_runtime_pack = resolve_runtime_pack(root, api_runtime, api_name, api_name)
        api_project = {
            "name": api_name,
            "path": api_name,
            "runtime": api_runtime,
            "repo_code": api_name,
            "compose_service": api_name,
            "port": _runtime_default_port(
                root=root,
                runtime=api_runtime,
                repo_name=api_name,
                repo_path=api_name,
                resolve_runtime_pack=resolve_runtime_pack,
            ),
            "capabilities": [],
            "service_bindings": [],
            "env": {},
            "_runtime_pack": api_runtime_pack,
        }
        projects.append(api_project)

    if any(keyword in lowered for keyword in ["frontend", "web app", "vite", "react app", "react frontend"]):
        web_name = _default_project_name(prompt, "web")
        web_runtime_pack = resolve_runtime_pack(root, "pnpm", web_name, web_name)
        projects.append(
            {
                "name": web_name,
                "path": web_name,
                "runtime": "pnpm",
                "repo_code": web_name,
                "compose_service": web_name,
                "port": _runtime_default_port(
                    root=root,
                    runtime="pnpm",
                    repo_name=web_name,
                    repo_path=web_name,
                    resolve_runtime_pack=resolve_runtime_pack,
                ),
                "capabilities": [],
                "service_bindings": [],
                "env": {},
                "_runtime_pack": web_runtime_pack,
            }
        )

    if any(keyword in lowered for keyword in ["postgresql", "postgres", "postgre"]):
        postgres_service = {"name": "postgres", "runtime": "postgres-service"}
        postgres_service.update(
            _runtime_service_defaults(
                root=root,
                runtime="postgres-service",
                service_name="postgres",
                resolve_runtime_pack=resolve_runtime_pack,
            )
        )
        services.append(postgres_service)
        for project in projects:
            runtime_pack = project.get("_runtime_pack", {})
            if not isinstance(runtime_pack, dict):
                continue
            binding_override = _runtime_binding_override(
                runtime_pack,
                service_runtime="postgres-service",
                service_name="postgres",
            )
            if not binding_override:
                continue
            project["service_bindings"].append("postgres")
            project_env = dict(project.get("env", {}))
            project_env.update(_binding_environment(binding_override))
            project["env"] = project_env

    if any(keyword in lowered for keyword in ["mongodb", "mongo db", "mongo"]):
        mongo_service = {"name": "mongo", "runtime": "mongo-service"}
        mongo_service.update(
            _runtime_service_defaults(
                root=root,
                runtime="mongo-service",
                service_name="mongo",
                resolve_runtime_pack=resolve_runtime_pack,
            )
        )
        services.append(mongo_service)
        for project in projects:
            runtime_pack = project.get("_runtime_pack", {})
            if not isinstance(runtime_pack, dict):
                continue
            binding_override = _runtime_binding_override(
                runtime_pack,
                service_runtime="mongo-service",
                service_name="mongo",
            )
            if not binding_override:
                continue
            project["service_bindings"].append("mongo")
            project_env = dict(project.get("env", {}))
            project_env.update(_binding_environment(binding_override))
            project["env"] = project_env

    if "graphql" in lowered:
        capabilities.append("graphql")
        for project in projects:
            if str(project.get("runtime")) in {"go-api", "php"}:
                project["capabilities"].append("graphql")

    manifest["projects"] = projects
    manifest["services"] = services
    manifest["capabilities"] = capabilities
    notes = [
        "V1 usa inferencia heuristica local; no invoca un modelo externo.",
        "Los servicios standalone se materializan en docker-compose sin crear repos falsos.",
    ]
    if not projects and not services:
        notes.append(
            "No pude inferir topologia materializable desde el prompt; se generara una spec draft con stack vacio para revision humana."
        )
    for project in projects:
        if isinstance(project, dict):
            project.pop("_runtime_pack", None)
    manifest["notes"] = notes
    return manifest


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-")


def _prompt_spec_identity(prompt: str, manifest: dict[str, object]) -> tuple[str, str]:
    projects = manifest.get("projects", [])
    first_project = projects[0] if isinstance(projects, list) and projects else {}
    project_name = str(first_project.get("name", "")).strip()
    if project_name:
        title = f"{project_name.replace('-', ' ').title()} Stack Bootstrap"
        slug = f"stack-{_slugify(project_name)}-bootstrap"
        return slug, title
    return "stack-bootstrap", "Stack Bootstrap"


def _frontmatter_target_block(targets: list[str]) -> list[str]:
    items = [str(target).strip() for target in targets if str(target).strip()]
    if not items:
        return ["targets: []"]
    return ["targets:"] + [f"  - {item}" for item in items]


def _yaml_frontmatter_block(payload: dict[str, object]) -> str:
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False).strip()
    return "---\n" + text + "\n---\n"


def draft_stack_spec_from_prompt(
    *,
    prompt: str,
    manifest: dict[str, object],
    root_repo: str,
    feature_specs: Path,
    default_targets: dict[str, list[str]],
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    write_state,
    slug: str | None = None,
    title: str | None = None,
    force: bool = False,
) -> tuple[Path, dict[str, object]]:
    suggested_slug, suggested_title = _prompt_spec_identity(prompt, manifest)
    spec_slug = _slugify(slug or suggested_slug)
    if not spec_slug:
        raise StackDesignError("No pude derivar un slug para la spec. Usa `--slug`.")
    spec_title = str(title or suggested_title).strip()
    if not spec_title:
        raise StackDesignError("No pude derivar un titulo para la spec. Usa `--title`.")

    spec_path = feature_specs / f"{spec_slug}.spec.md"
    if spec_path.exists() and not force:
        raise StackDesignError(
            f"La spec `{rel(spec_path)}` ya existe. Usa `--force` para regenerar el draft."
        )

    required_runtimes = sorted(
        {
            str(project.get("runtime", "")).strip()
            for project in manifest.get("projects", [])
            if isinstance(project, dict) and str(project.get("runtime", "")).strip()
        }
    )
    required_services = sorted(
        {
            str(service.get("runtime", "")).strip()
            for service in manifest.get("services", [])
            if isinstance(service, dict) and str(service.get("runtime", "")).strip()
        }
    )
    required_capabilities = requested_capabilities(manifest)

    frontmatter = {
        "schema_version": 2,
        "name": spec_title,
        "description": "TODO describir el resultado observable",
        "status": "draft",
        "owner": "platform",
        "depends_on": [],
        "required_runtimes": required_runtimes,
        "required_services": required_services,
        "required_capabilities": required_capabilities,
        "stack_projects": list(manifest.get("projects", [])),
        "stack_services": list(manifest.get("services", [])),
        "stack_capabilities": list(manifest.get("capabilities", [])),
        "targets": list(default_targets.get(root_repo, [])),
    }

    project_lines = []
    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        port = project.get("port")
        service_bindings = ", ".join(str(item) for item in project.get("service_bindings", []) if str(item).strip()) or "sin bindings"
        repo_code = str(project.get("repo_code", "")).strip() or str(project["name"])
        project_lines.append(
            f"- `{project['name']}` runtime `{project['runtime']}` en `{project.get('path', project['name'])}` "
            f"(port: `{port if port is not None else 'n/a'}`, repo_code: `{repo_code}`, bindings: {service_bindings})"
        )
    if not project_lines:
        project_lines = ["- TODO completar proyectos a materializar"]

    service_lines = []
    for service in manifest.get("services", []):
        if not isinstance(service, dict):
            continue
        ports = ", ".join(str(item) for item in service.get("ports", []) if str(item).strip()) or "sin puertos publicados"
        service_lines.append(
            f"- `{service['name']}` con runtime `{service['runtime']}` (ports: {ports})"
        )
    if not service_lines:
        service_lines = ["- sin servicios inferidos"]
    capability_lines = [
        f"- `{capability}`"
        for capability in manifest.get("capabilities", [])
        if str(capability).strip()
    ] or ["- sin capabilities inferidas"]

    body = "\n".join(
        [
            f"# {spec_title}",
            "",
            "## Objetivo",
            "",
            "Describir el stack que debe quedar materializado desde esta spec antes de entrar a implementación detallada.",
            "",
            "## Prompt original",
            "",
            f"> {prompt.strip()}",
            "",
            "## Contexto",
            "",
            "- esta spec nace desde una inferencia asistida y debe ser revisada por un humano o cliente IA",
            "- la topología declarativa del stack vive en el frontmatter, no en `workspace.stack.json`",
            "- el manifest del stack se derivará solo después de aprobar esta spec",
            "",
            "## Problema a resolver",
            "",
            "- describir por que se necesita este stack ahora",
            "- describir que foundations o dependencias deben existir antes de implementarlo",
            "",
            "## Topología propuesta",
            "",
            "Revisar y confirmar en frontmatter: `repo_code`, `compose_service`, `port`, `env`, `service_bindings`, `ports` y `volumes`.",
            "",
            "### Proyectos",
            "",
            *project_lines,
            "",
            "### Servicios",
            "",
            *service_lines,
            "",
            "### Capabilities",
            "",
            *capability_lines,
            "",
            "## Alcance",
            "",
            "### Incluye",
            "",
            "- revisar y completar la topología declarada en el frontmatter",
            "- aprobar la spec antes de derivar `workspace.stack.json`",
            "",
            "### No incluye",
            "",
            "- implementar comportamiento de negocio detallado dentro de los repos nuevos",
            "- aprobar foundations generadas automáticamente sin review explícita",
            "",
            "## Repos afectados",
            "",
            "| Repo | Targets |",
            "| --- | --- |",
            f"| `{root_repo}` | {', '.join(default_targets.get(root_repo, []))} |",
            "",
            "## Resultado esperado",
            "",
            "- TODO describir el stack observable que debe quedar listo tras `stack apply --spec`",
            "",
            "## Reglas de negocio",
            "",
            "- la spec aprobada es la fuente de verdad para la topología materializable",
            "- `stack design --prompt` solo asiste el authoring del draft inicial",
            "",
            "## Flujo principal",
            "",
            "1. se redacta o corrige esta spec hasta dejarla lista para review",
            "2. `spec review` valida dependencias, runtimes, servicios y capabilities declaradas",
            "3. `stack design|plan|apply --spec` deriva y materializa el stack desde la spec aprobada",
            "",
            "## Contrato funcional",
            "",
            "- inputs clave: spec aprobada con `stack_projects`, `stack_services`, `stack_capabilities`",
            "- outputs clave: `workspace.stack.json`, repos/proyectos materializados, foundations generadas",
            "- errores esperados: runtimes faltantes, servicios no declarados, spec no aprobada",
            "- side effects relevantes: cambios en `workspace.config.json`, compose y `specs/000-foundation/generated/**`",
            "",
            "## Routing de implementacion",
            "",
            "- El repo se deduce desde `targets`.",
            "- Cada slice debe pertenecer a un solo repo.",
            "- El plan operativo vive en `.flow/plans/**`.",
            "- Las dependencias estructurales viven en el frontmatter y deben resolverse antes de aprobar.",
            "",
            "## Criterios de aceptacion",
            "",
            "- `python3 ./flow spec review {slug}` debe identificar gaps de la topología declarada".format(slug=spec_slug),
            "- `python3 ./flow stack plan --spec {slug}` debe describir el stack a crear solo después de aprobar la spec".format(slug=spec_slug),
            "",
            "## Test plan",
            "",
            "- Evidencia de verificacion del workspace: review manual o check operativo.",
            "",
            "## Rollout",
            "",
            "- TODO describir cómo se adoptará este stack en el workspace",
            "",
            "## Rollback",
            "",
            "- TODO describir cómo revertir la materialización del stack si la spec cambia",
            "",
        ]
    )

    text = _yaml_frontmatter_block(frontmatter) + "\n" + body
    spec_path.write_text(text, encoding="utf-8")

    write_state(
        spec_slug,
        {
            "feature": spec_slug,
            "title": spec_title,
            "spec_path": rel(spec_path),
            "status": "draft-spec",
            "repos": [root_repo],
            "created_at": utc_now(),
            "source_prompt": prompt.strip(),
        },
    )

    return spec_path, manifest


def _normalize_optional_string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise StackDesignError(f"`{label}` debe declararse como lista.")
    items = [str(item).strip() for item in value if str(item).strip()]
    return items


def design_stack_from_spec(
    spec_path: Path,
    analysis: dict[str, object],
    *,
    root: Path,
    resolve_runtime_pack,
    require_approved: bool = True,
) -> dict[str, object]:
    frontmatter = analysis.get("frontmatter", {})
    if not isinstance(frontmatter, dict):
        raise StackDesignError(f"La spec `{spec_path}` no tiene frontmatter valido.")
    frontmatter_status = str(frontmatter.get("status", "")).strip() or "draft"
    if require_approved and frontmatter_status_is_terminal(frontmatter_status):
        raise StackDesignError(f"La spec `{spec_path}` ya esta en `released`; no se debe rematerializar stack.")
    if require_approved and not frontmatter_status_allows_execution(frontmatter_status):
        raise StackDesignError(f"La spec `{spec_path}` debe estar en `approved` para materializar stack.")

    raw_projects = analysis.get("stack_projects", [])
    raw_services = analysis.get("stack_services", [])
    raw_capabilities = analysis.get("stack_capabilities", [])
    if not isinstance(raw_projects, list):
        raw_projects = []
    if not isinstance(raw_services, list):
        raw_services = []
    if not isinstance(raw_capabilities, list):
        raw_capabilities = []

    if not raw_projects and not raw_services and not raw_capabilities:
        raise StackDesignError(
            f"La spec `{spec_path}` no declara topologia de stack. "
            "Usa `stack_projects`, `stack_services` o `stack_capabilities` en el frontmatter."
        )

    services: list[dict[str, object]] = []
    service_names: list[str] = []
    service_runtimes: dict[str, str] = {}
    for index, item in enumerate(raw_services, start=1):
        if not isinstance(item, dict):
            raise StackDesignError(f"`stack_services` item #{index} no es valido.")
        name = str(item.get("name", "")).strip()
        runtime = str(item.get("runtime", "")).strip()
        if not name or not runtime:
            raise StackDesignError(f"`stack_services` item #{index} debe declarar `name` y `runtime`.")
        runtime_pack = resolve_runtime_pack(root, runtime, name, name)
        if str(runtime_pack.get("runtime_kind", "project")) != "service":
            raise StackDesignError(f"`stack_services` item `{name}` usa `{runtime}`, que no es un runtime de servicio.")
        service_names.append(name)
        service_runtimes[name] = runtime
        service_payload: dict[str, object] = {"name": name, "runtime": runtime}
        service_env = _normalize_optional_mapping(item.get("env"), f"stack_services[{name}].env")
        if service_env:
            service_payload["env"] = service_env
        ports = item.get("ports")
        if ports is not None:
            service_payload["ports"] = _normalize_optional_string_list(ports, f"stack_services[{name}].ports")
        volumes = _normalize_optional_string_list(item.get("volumes"), f"stack_services[{name}].volumes")
        if volumes:
            service_payload["volumes"] = volumes
        services.append(service_payload)

    capabilities = list(dict.fromkeys(str(item).strip() for item in raw_capabilities if str(item).strip()))

    projects: list[dict[str, object]] = []
    for index, item in enumerate(raw_projects, start=1):
        if not isinstance(item, dict):
            raise StackDesignError(f"`stack_projects` item #{index} no es valido.")
        name = str(item.get("name", "")).strip()
        runtime = str(item.get("runtime", "")).strip()
        if not name or not runtime:
            raise StackDesignError(f"`stack_projects` item #{index} debe declarar `name` y `runtime`.")
        path = str(item.get("path", name)).strip() or name
        runtime_pack = resolve_runtime_pack(root, runtime, name, path)
        if str(runtime_pack.get("runtime_kind", "project")) != "project":
            raise StackDesignError(f"`stack_projects` item `{name}` usa `{runtime}`, que no es un runtime de proyecto.")

        project_capabilities = _normalize_optional_string_list(item.get("capabilities"), f"stack_projects[{name}].capabilities")
        service_bindings = _normalize_optional_string_list(item.get("service_bindings"), f"stack_projects[{name}].service_bindings")
        if not service_bindings and len(raw_projects) == 1:
            service_bindings = list(service_names)
        for service_name in service_bindings:
            if service_name not in service_names:
                raise StackDesignError(
                    f"`stack_projects` item `{name}` referencia un servicio no declarado: `{service_name}`."
                )

        compose_overrides: dict[str, object] = {}
        project_payload: dict[str, object] = {
            "name": name,
            "path": path,
            "runtime": runtime,
            "port": item.get(
                "port",
                _runtime_default_port(
                    root=root,
                    runtime=runtime,
                    repo_name=name,
                    repo_path=path,
                    resolve_runtime_pack=resolve_runtime_pack,
                ),
            ),
            "capabilities": project_capabilities,
            "service_bindings": service_bindings,
            "compose_overrides": compose_overrides,
        }
        compose_service = str(item.get("compose_service", "")).strip()
        if compose_service:
            project_payload["compose_service"] = compose_service
        repo_code = str(item.get("repo_code", "")).strip()
        if repo_code:
            project_payload["repo_code"] = repo_code
        aliases = _normalize_optional_string_list(item.get("aliases"), f"stack_projects[{name}].aliases")
        if aliases:
            project_payload["aliases"] = aliases
        project_env = _normalize_optional_mapping(item.get("env"), f"stack_projects[{name}].env")
        if project_env:
            project_payload["env"] = project_env
        default_targets = _normalize_optional_string_list(
            item.get("default_targets"),
            f"stack_projects[{name}].default_targets",
        )
        if default_targets:
            project_payload["default_targets"] = default_targets
        target_roots = _normalize_optional_string_list(
            item.get("target_roots"),
            f"stack_projects[{name}].target_roots",
        )
        if target_roots:
            project_payload["target_roots"] = target_roots
        for service_name in service_bindings:
            service_runtime = service_runtimes.get(service_name, "")
            compose_overrides = _merge_dict(
                compose_overrides,
                _runtime_binding_override(
                    runtime_pack,
                    service_runtime=service_runtime,
                    service_name=service_name,
                ),
            )
        if project_env:
            compose_overrides = _merge_dict(compose_overrides, {"environment": project_env})
        project_payload["compose_overrides"] = compose_overrides
        if isinstance(item.get("use_existing_dir"), bool):
            project_payload["use_existing_dir"] = bool(item.get("use_existing_dir"))
        projects.append(project_payload)
        for capability in project_capabilities:
            if capability not in capabilities:
                capabilities.append(capability)

    for capability in analysis.get("required_capabilities", []):
        candidate = str(capability).strip()
        if candidate and candidate not in capabilities:
            capabilities.append(candidate)

    notes = [
        "V2 deriva el stack desde una spec aprobada."
        if normalize_frontmatter_status(frontmatter_status) == "approved"
        else "V2 permite previsualizar el stack desde una spec lista para aprobar.",
        "workspace.stack.json queda como artefacto materializado, no como fuente primaria.",
    ]

    return {
        "schema_version": 2,
        "source_prompt": "",
        "source_spec": str(spec_path),
        "source_spec_status": frontmatter_status,
        "projects": projects,
        "services": services,
        "capabilities": capabilities,
        "notes": notes,
    }


def _format_text(value: str, substitutions: dict[str, str]) -> str:
    return value.format(**substitutions)


def render_foundation_spec(pack: dict[str, object], substitutions: dict[str, str], targets: list[str]) -> list[tuple[Path, str]]:
    items = pack.get("foundation_specs", [])
    rendered: list[tuple[Path, str]] = []
    if not isinstance(items, list):
        return rendered
    for item in items:
        if not isinstance(item, dict):
            continue
        path = Path(_format_text(str(item.get("path", "")).strip(), substitutions))
        name = _format_text(str(item.get("name", "")).strip(), substitutions)
        description = _format_text(str(item.get("description", "")).strip(), substitutions)
        owner = _format_text(str(item.get("owner", "platform")).strip(), substitutions)
        body_items = item.get("body", [])
        if not path or not name or not isinstance(body_items, list):
            continue
        body = "\n".join(_format_text(str(line), substitutions) for line in body_items)
        frontmatter = [
            "---",
            f"name: {name}",
            f"description: {description}",
            "status: draft",
            f"owner: {owner}",
            "targets:",
        ]
        for target in targets:
            frontmatter.append(f"  - {target}")
        frontmatter.append("---")
        text = "\n".join(frontmatter) + "\n\n" + body.strip() + "\n"
        rendered.append((path, text))
    return rendered


def _current_repo_config(load_workspace_config: Callable[[], dict[str, object]]) -> dict[str, dict[str, object]]:
    payload = load_workspace_config()
    repos = payload.get("repos", {})
    if not isinstance(repos, dict):
        raise StackDesignError("workspace.config.json debe definir `repos`.")
    return repos


def apply_project_definition(
    project: dict[str, object],
    *,
    root: Path,
    root_repo: str,
    workspace_config_file: Path,
    load_workspace_config: Callable[[], dict[str, object]],
    load_skills_config: Callable[[], dict[str, object]],
    skills_entries,
    normalize_repo_path: Callable[[str], str],
    validate_identifier: Callable[[str, str], str],
    ensure_project_directory,
    repo_placeholder_text,
    resolve_runtime_pack,
    add_service_to_compose,
    find_repo_compose_file,
    rel: Callable[[Path], str],
) -> dict[str, object]:
    repo_name = validate_identifier(str(project.get("name", "")).strip(), "nombre del proyecto")
    repo_path = normalize_repo_path(str(project.get("path", repo_name)))
    runtime = str(project.get("runtime", "")).strip()
    runtime_pack = resolve_runtime_pack(root, runtime, repo_name, repo_path)
    if str(runtime_pack.get("runtime_kind", "project")) != "project":
        raise StackDesignError(f"El runtime `{runtime}` no es un runtime de proyecto.")

    current_workspace = load_workspace_config()
    current_repos = current_workspace.get("repos", {})
    if not isinstance(current_repos, dict):
        raise StackDesignError("workspace.config.json debe definir `repos`.")
    if repo_name in current_repos:
        return {"name": repo_name, "status": "skipped", "reason": "repo already registered"}

    destination = root / repo_path
    ensure_project_directory(destination, use_existing=bool(project.get("use_existing_dir", False)), rel=rel)

    agents_text, readme_text = repo_placeholder_text(root_repo, repo_name, runtime_pack["agent_skill_refs"])
    if not (destination / "AGENTS.md").exists():
        (destination / "AGENTS.md").write_text(agents_text, encoding="utf-8")
    if not (destination / "README.md").exists():
        (destination / "README.md").write_text(readme_text, encoding="utf-8")

    for directory in runtime_pack["placeholder_dirs"]:
        target_dir = destination / str(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = target_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")

    for relative_path, content in runtime_pack["placeholder_files"].items():
        target_file = destination / relative_path
        if not target_file.exists():
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content, encoding="utf-8")

    compose_service = validate_identifier(str(project.get("compose_service") or repo_name), "nombre del servicio")
    compose_config = runtime_pack.get("compose")
    compose_overrides = project.get("compose_overrides", {})
    if isinstance(compose_config, dict) and isinstance(compose_overrides, dict):
        compose_config = _merge_dict(compose_config, compose_overrides)
    explicit_compose_file = str(project.get("compose_file", "")).strip()
    external_compose_file: Path | None = None
    if explicit_compose_file:
        candidate = (root / explicit_compose_file).resolve()
        if candidate.is_file():
            external_compose_file = candidate
    if external_compose_file is None:
        external_compose_file = find_repo_compose_file(destination)

    updated_workspace = load_workspace_config()
    repos = updated_workspace["repos"]
    if not isinstance(repos, dict):
        raise StackDesignError("workspace.config.json debe definir `repos`.")

    repos[repo_name] = {
        "path": repo_path,
        "compose_service": compose_service,
        "kind": "implementation",
        "runtime": runtime,
        "repo_strategy": "plain",
        "slice_prefix": repo_name.replace("_", "-"),
        "default_targets": list(project.get("default_targets") or runtime_pack["default_targets"]),
        "target_roots": list(project.get("target_roots") or runtime_pack["target_roots"]),
        "contract_roots": list(runtime_pack["test_required_roots"]),
        "test_required_roots": list(runtime_pack["test_required_roots"]),
        "agent_skill_refs": list(runtime_pack["agent_skill_refs"]),
        "test_runner": str(project.get("test_runner") or runtime_pack["test_runner"]),
    }
    if external_compose_file is not None:
        try:
            repos[repo_name]["compose_file"] = external_compose_file.relative_to(root).as_posix()
        except ValueError:
            repos[repo_name]["compose_file"] = str(external_compose_file)
    repo_code = str(project.get("repo_code", "")).strip()
    if repo_code:
        repos[repo_name]["code"] = repo_code
    aliases = [str(item).strip() for item in project.get("aliases", []) if str(item).strip()]
    if aliases:
        repos[repo_name]["aliases"] = aliases
    if runtime_pack.get("test_hint"):
        repos[repo_name]["test_hint"] = runtime_pack["test_hint"]
    if runtime_pack.get("ci"):
        repos[repo_name]["ci"] = dict(runtime_pack["ci"])

    workspace_config_file.write_text(
        json.dumps(updated_workspace, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    if external_compose_file is None and isinstance(compose_config, dict):
        add_service_to_compose(
            compose_service,
            repo_path,
            runtime,
            int(project["port"]) if project.get("port") is not None else None,
            compose_config,
        )

    missing_skill_refs: list[str] = []
    try:
        skills_payload = load_skills_config()
        entries, errors = skills_entries(skills_payload)
        if errors:
            raise StackDesignError("\n".join(errors))
        known = {str(entry["name"]) for entry in entries}
        missing_skill_refs = [ref for ref in runtime_pack["agent_skill_refs"] if ref not in known]
    except Exception:
        missing_skill_refs = list(runtime_pack["agent_skill_refs"])

    return {
        "name": repo_name,
        "status": "added",
        "path": repo_path,
        "runtime": runtime,
        "compose_service": compose_service,
        "compose_source": "external" if external_compose_file is not None else "workspace",
        "missing_skill_refs": missing_skill_refs,
    }


def resolve_stack_manifest(
    args,
    *,
    root: Path,
    stack_config_file: Path,
    resolve_spec,
    ensure_spec_ready_for_approval,
    resolve_runtime_pack,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    persist: bool,
    require_approved: bool,
) -> tuple[dict[str, object], Path | None, str, bool]:
    spec_identifier = str(getattr(args, "spec", "") or "").strip()
    if not spec_identifier:
        manifest = load_stack_manifest(stack_config_file)
        return manifest, None, str(manifest.get("source_spec_status", "")).strip(), False

    spec_path = resolve_spec(spec_identifier)
    analysis = ensure_spec_ready_for_approval(spec_path)
    frontmatter = analysis.get("frontmatter", {})
    spec_status = str(frontmatter.get("status", "")).strip() if isinstance(frontmatter, dict) else ""
    manifest = design_stack_from_spec(
        spec_path,
        analysis,
        root=root,
        resolve_runtime_pack=resolve_runtime_pack,
        require_approved=require_approved,
    )
    manifest["designed_at"] = utc_now()
    manifest["source_spec"] = rel(spec_path)
    persisted = False
    if persist and frontmatter_status_allows_execution(spec_status):
        write_stack_manifest(stack_config_file, manifest)
        persisted = True
    elif persist and frontmatter_status_is_terminal(spec_status):
        manifest["notes"] = list(manifest.get("notes", [])) + [
            "No se persistio workspace.stack.json porque la spec ya esta en released."
        ]
    elif persist and not frontmatter_status_allows_execution(spec_status):
        manifest["notes"] = list(manifest.get("notes", [])) + [
            "No se persistio workspace.stack.json porque la spec sigue en draft."
        ]
    return manifest, spec_path, spec_status, persisted


def command_stack_design(
    args,
    *,
    root: Path,
    stack_config_file: Path,
    root_repo: str,
    feature_specs: Path,
    default_targets: dict[str, list[str]],
    resolve_spec,
    ensure_spec_ready_for_approval,
    resolve_runtime_pack,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    write_state,
    json_dumps: Callable[[object], str],
) -> int:
    try:
        if getattr(args, "spec", None):
            manifest, spec_path, frontmatter_status, _ = resolve_stack_manifest(
                args,
                root=root,
                stack_config_file=stack_config_file,
                resolve_spec=resolve_spec,
                ensure_spec_ready_for_approval=ensure_spec_ready_for_approval,
                resolve_runtime_pack=resolve_runtime_pack,
                rel=rel,
                utc_now=utc_now,
                persist=False,
                require_approved=False,
            )
            payload = {
                "stack_manifest": str(stack_config_file.name),
                "design": manifest,
                "source_spec": rel(spec_path) if spec_path is not None else "",
                "frontmatter_status": frontmatter_status,
            }
        else:
            manifest = design_stack_from_prompt(
                args.prompt,
                root=root,
                resolve_runtime_pack=resolve_runtime_pack,
            )
            draft_spec_path, suggested_manifest = draft_stack_spec_from_prompt(
                prompt=args.prompt,
                manifest=manifest,
                root_repo=root_repo,
                feature_specs=feature_specs,
                default_targets=default_targets,
                rel=rel,
                utc_now=utc_now,
                write_state=write_state,
                slug=getattr(args, "slug", None),
                title=getattr(args, "title", None),
                force=bool(getattr(args, "force", False)),
            )
            payload = {
                "draft_spec": rel(draft_spec_path),
                "design_hint": suggested_manifest,
                "source_prompt": args.prompt.strip(),
                "persisted_stack_manifest": False,
            }
    except StackDesignError as exc:
        return _emit_stack_error(str(exc), json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(payload.get("draft_spec", stack_config_file.name))
    return 0


def command_stack_plan(
    args,
    *,
    root: Path,
    stack_config_file: Path,
    workspace_config_file: Path,
    load_workspace_config: Callable[[], dict[str, object]],
    resolve_spec,
    ensure_spec_ready_for_approval,
    resolve_capability_pack,
    resolve_runtime_pack,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    try:
        manifest, spec_path, frontmatter_status, persisted_manifest = resolve_stack_manifest(
            args,
            root=root,
            stack_config_file=stack_config_file,
            resolve_spec=resolve_spec,
            ensure_spec_ready_for_approval=ensure_spec_ready_for_approval,
            resolve_runtime_pack=resolve_runtime_pack,
            rel=rel,
            utc_now=utc_now,
            persist=bool(getattr(args, "spec", None)),
            require_approved=False,
        )
    except StackDesignError as exc:
        return _emit_stack_error(str(exc), json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
    current_repos = _current_repo_config(load_workspace_config)
    compose_text = (root / ".devcontainer" / "docker-compose.yml").read_text(encoding="utf-8")
    actions: list[dict[str, object]] = []

    for service in manifest.get("services", []):
        if not isinstance(service, dict):
            continue
        name = str(service.get("name", "")).strip()
        runtime = str(service.get("runtime", "")).strip()
        runtime_pack = resolve_runtime_pack(root, runtime, name, name)
        actions.append(
            {
                "type": "service",
                "name": name,
                "runtime": runtime,
                "runtime_kind": runtime_pack.get("runtime_kind"),
                "status": "existing" if f"\n  {name}:\n" in compose_text else "planned",
            }
        )

    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        name = str(project.get("name", "")).strip()
        runtime = str(project.get("runtime", "")).strip()
        runtime_pack = resolve_runtime_pack(root, runtime, name, str(project.get("path", name) or name))
        actions.append(
            {
                "type": "project",
                "name": name,
                "runtime": runtime,
                "runtime_kind": runtime_pack.get("runtime_kind"),
                "status": "existing" if name in current_repos else "planned",
                "capabilities": list(project.get("capabilities", [])),
                "service_bindings": list(project.get("service_bindings", [])),
            }
        )

    substitutions = {
        "primary_project": str(manifest.get("projects", [{}])[0].get("name", "api")) if manifest.get("projects") else "api",
        "primary_database": str(manifest.get("services", [{}])[0].get("name", "database")) if manifest.get("services") else "database",
    }
    for capability in requested_capabilities(manifest):
        pack, _ = resolve_capability_pack(root, capability)
        rendered = render_foundation_spec(
            pack,
            substitutions,
            _default_targets_for_manifest(manifest, root=root, resolve_runtime_pack=resolve_runtime_pack),
        )
        for spec_path, _ in rendered:
            absolute = root / spec_path
            actions.append(
                {
                    "type": "foundation-spec",
                    "name": capability,
                    "path": str(spec_path),
                    "status": "existing" if absolute.exists() else "planned",
                }
            )

    payload = {
        "stack_manifest": str(workspace_config_file.parent / stack_config_file.name),
        "source_prompt": manifest.get("source_prompt", ""),
        "source_spec": manifest.get("source_spec", ""),
        "frontmatter_status": frontmatter_status,
        "persisted_stack_manifest": persisted_manifest,
        "actions": actions,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(json_dumps(payload))
    return 0


def _default_targets_for_manifest(
    manifest: dict[str, object],
    *,
    root: Path,
    resolve_runtime_pack,
) -> list[str]:
    project_targets: list[str] = []
    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        path = str(project.get("path", project.get("name", "api"))).strip() or str(project.get("name", "api"))
        runtime = str(project.get("runtime", "")).strip()
        name = str(project.get("name", path)).strip() or path
        runtime_pack = resolve_runtime_pack(root, runtime, name, path)
        project_targets.extend(str(item).strip() for item in runtime_pack.get("default_targets", []) if str(item).strip())
    return project_targets or ["../../.devcontainer/**", "../../specs/**"]


def command_stack_apply(
    args,
    *,
    root: Path,
    root_repo: str,
    stack_config_file: Path,
    workspace_config_file: Path,
    load_workspace_config: Callable[[], dict[str, object]],
    load_skills_config: Callable[[], dict[str, object]],
    skills_entries,
    resolve_spec,
    ensure_spec_ready_for_approval,
    normalize_repo_path: Callable[[str], str],
    validate_identifier: Callable[[str, str], str],
    ensure_project_directory,
    repo_placeholder_text,
    resolve_runtime_pack,
    add_service_to_compose,
    add_standalone_service_to_compose,
    find_repo_compose_file,
    resolve_capability_pack,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
) -> int:
    try:
        manifest, spec_path, frontmatter_status, _ = resolve_stack_manifest(
            args,
            root=root,
            stack_config_file=stack_config_file,
            resolve_spec=resolve_spec,
            ensure_spec_ready_for_approval=ensure_spec_ready_for_approval,
            resolve_runtime_pack=resolve_runtime_pack,
            rel=rel,
            utc_now=utc_now,
            persist=bool(getattr(args, "spec", None)),
            require_approved=True,
        )
    except StackDesignError as exc:
        return _emit_stack_error(str(exc), json_mode=bool(getattr(args, "json", False)), json_dumps=json_dumps)
    results = {"services": [], "projects": [], "foundation_specs": []}

    for service in manifest.get("services", []):
        if not isinstance(service, dict):
            continue
        name = validate_identifier(str(service.get("name", "")).strip(), "nombre del servicio")
        runtime = str(service.get("runtime", "")).strip()
        runtime_pack = resolve_runtime_pack(root, runtime, name, name)
        if str(runtime_pack.get("runtime_kind", "project")) != "service":
            raise StackDesignError(f"El runtime `{runtime}` no es un runtime de servicio.")
        compose_text = (root / ".devcontainer" / "docker-compose.yml").read_text(encoding="utf-8")
        if f"\n  {name}:\n" in compose_text:
            results["services"].append({"name": name, "status": "skipped", "reason": "service already exists"})
            continue
        compose_config = runtime_pack.get("compose")
        if not isinstance(compose_config, dict):
            raise StackDesignError(f"El runtime `{runtime}` debe declarar `compose` para servicios standalone.")
        compose_overrides: dict[str, object] = {}
        service_env = _normalize_optional_mapping(service.get("env"), f"stack_services[{name}].env")
        if service_env:
            compose_overrides["environment"] = service_env
        service_ports = service.get("ports")
        if service_ports is not None:
            compose_overrides["ports"] = _normalize_optional_string_list(service_ports, f"stack_services[{name}].ports")
        service_volumes = _normalize_optional_string_list(service.get("volumes"), f"stack_services[{name}].volumes")
        if service_volumes:
            compose_overrides["volumes"] = service_volumes
        if compose_overrides:
            compose_config = _merge_dict(compose_config, compose_overrides)
        add_standalone_service_to_compose(root / ".devcontainer" / "docker-compose.yml", name, runtime, compose_config)
        results["services"].append({"name": name, "status": "added", "runtime": runtime})

    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        result = apply_project_definition(
            project,
            root=root,
            root_repo=root_repo,
            workspace_config_file=workspace_config_file,
            load_workspace_config=load_workspace_config,
            load_skills_config=load_skills_config,
            skills_entries=skills_entries,
            normalize_repo_path=normalize_repo_path,
            validate_identifier=validate_identifier,
            ensure_project_directory=ensure_project_directory,
            repo_placeholder_text=repo_placeholder_text,
            resolve_runtime_pack=resolve_runtime_pack,
            add_service_to_compose=add_service_to_compose,
            find_repo_compose_file=find_repo_compose_file,
            rel=rel,
        )
        results["projects"].append(result)

    substitutions = {
        "primary_project": str(manifest.get("projects", [{}])[0].get("name", "api")) if manifest.get("projects") else "api",
        "primary_database": str(manifest.get("services", [{}])[0].get("name", "database")) if manifest.get("services") else "database",
    }
    foundation_targets = _default_targets_for_manifest(
        manifest,
        root=root,
        resolve_runtime_pack=resolve_runtime_pack,
    )
    for capability in requested_capabilities(manifest):
        pack, _ = resolve_capability_pack(root, capability)
        for relative_path, text in render_foundation_spec(pack, substitutions, foundation_targets):
            destination = root / relative_path
            if destination.exists():
                results["foundation_specs"].append({"path": str(relative_path), "status": "skipped"})
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text, encoding="utf-8")
            results["foundation_specs"].append({"path": str(relative_path), "status": "created"})

    manifest["applied_at"] = utc_now()
    manifest["generated_specs"] = [item["path"] for item in results["foundation_specs"] if item["status"] == "created"]
    write_stack_manifest(stack_config_file, manifest)

    payload = {
        "stack_manifest": stack_config_file.name,
        "source_spec": rel(spec_path) if spec_path is not None else manifest.get("source_spec", ""),
        "frontmatter_status": frontmatter_status,
        "results": results,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(json_dumps(payload))
    return 0
