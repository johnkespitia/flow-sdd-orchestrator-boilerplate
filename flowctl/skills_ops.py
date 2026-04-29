from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Iterable


def skills_provider_config(payload: dict[str, object], provider: str) -> dict[str, object]:
    providers = payload.get("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("`providers` debe ser un objeto en workspace.skills.json.")
    config = providers.get(provider, {})
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ValueError(f"La configuracion del proveedor `{provider}` debe ser un objeto.")
    return config


def skills_provider_enabled(payload: dict[str, object], provider: str) -> bool:
    return bool(skills_provider_config(payload, provider).get("enabled", True))


def skills_provider_runtime_available(provider: str, *, workspace_executable_available: Callable[[str], bool]) -> bool:
    if provider == "tessl":
        return workspace_executable_available("tessl")
    if provider == "skills-sh":
        return workspace_executable_available("npx")
    return False


def command_has_flag(command: list[str], *flags: str) -> bool:
    return any(flag in command for flag in flags)


def tessl_skill_commands(entry: dict[str, object], *, rel: Callable[[Path], str]) -> list[list[str]]:
    source = str(entry["source"])
    local_source_path = entry.get("local_source_path")
    args = [str(item) for item in entry.get("args", [])]

    if entry["kind"] == "skill":
        if local_source_path is None:
            raise SystemExit(
                f"`{entry['name']}` usa `tessl skill import` y requiere un `source` local relativo al workspace."
            )
        source_arg = rel(local_source_path)
        lint_target = rel(local_source_path if local_source_path.is_dir() else local_source_path.parent)
        return [
            ["tessl", "skill", "import", "--force", *args, source_arg],
            ["tessl", "tile", "lint", lint_target],
        ]

    if local_source_path is not None:
        lint_target = rel(local_source_path if local_source_path.is_dir() else local_source_path.parent)
        return [["tessl", "tile", "lint", lint_target]]

    command = ["tessl", "install", *args]
    if not command_has_flag(command, "--yes"):
        command.append("--yes")
    command.append(source)
    return [command]


def skills_sh_commands(entry: dict[str, object]) -> list[list[str]]:
    command = [
        "npx", "-y", "skills", "add", str(entry["source"]),
        *[str(item) for item in entry.get("args", [])],
        "--yes",       # CLI skills: modo no interactivo
        "--project",   # scope explícito: instalar en ./.agents/skills/
        "--also", "cursor",  # agente destino: Cursor (evita prompt de 42 agentes)
    ]
    return [command]


def skill_entry_commands(entry: dict[str, object], *, rel: Callable[[Path], str]) -> list[list[str]]:
    provider = str(entry["provider"])
    if provider == "tessl":
        return tessl_skill_commands(entry, rel=rel)
    if provider == "skills-sh":
        return skills_sh_commands(entry)
    raise SystemExit(f"No conozco el provider `{provider}`.")


def skills_report_stamp(*, utc_now: Callable[[], str]) -> str:
    return utc_now().replace(":", "").replace("-", "").replace("+00:00", "Z")


def _resolve_skill_path(
    skill_name: str,
    *,
    root: Path,
    skills_entries_by_name: dict[str, dict[str, object]],
    rel: Callable[[Path], str],
) -> str | None:
    """
    Resuelve el path del skill a partir del nombre.
    - tessl con source local: .tessl/tiles/workspace/<tile>/
    - skills-sh con args --skill X: .agents/skills/X/
    """
    entry = skills_entries_by_name.get(skill_name)
    if not entry:
        return None
    provider = str(entry.get("provider", ""))
    if provider == "tessl":
        local_path = entry.get("local_source_path")
        if isinstance(local_path, Path) and local_path.exists():
            return rel(local_path)
        return None
    if provider == "skills-sh":
        args = entry.get("args") or []
        if not isinstance(args, list):
            return None
        for i, a in enumerate(args):
            if str(a).strip() == "--skill" and i + 1 < len(args):
                skill_id = str(args[i + 1]).strip()
                if skill_id:
                    agents_skill = root / ".agents" / "skills" / skill_id
                    if agents_skill.exists():
                        return rel(agents_skill)
                    return f".agents/skills/{skill_id}"
        return None
    return None


def command_skills_context(
    args,
    *,
    root: Path,
    load_workspace_config: Callable[[], dict[str, object]],
    load_skills_config: Callable[[], dict[str, object]],
    skills_entries: Callable[[dict[str, object]], tuple[list[dict[str, object]], list[str]]],
    resolve_runtime_pack,
    resolve_spec: Callable[[str], Path] | None,
    analyze_spec: Callable[[Path], dict[str, object]] | None,
    rel: Callable[[Path], str],
    json_dumps: Callable[[object], str],
) -> int:
    """
    Resuelve runtime y agent_skill_refs para un repo o para los repos afectados por una spec.
    Salida JSON para que la IA obtenga el contexto de skills sin parsear manifests.
    Incluye path de cada skill para que la IA los localice en .agents/skills/ o .tessl/tiles/.
    """
    workspace = load_workspace_config()
    repos_config = workspace.get("repos", {})
    if not isinstance(repos_config, dict):
        raise SystemExit("workspace.config.json debe definir `repos`.")

    repo_arg = getattr(args, "repo", None)
    spec_arg = getattr(args, "spec", None)

    if repo_arg:
        repo_name = str(repo_arg).strip()
        if repo_name not in repos_config:
            raise SystemExit(f"No existe el repo `{repo_name}` en workspace.config.json.")
        repo_list = [repo_name]
    elif spec_arg and resolve_spec and analyze_spec:
        spec_path = resolve_spec(str(spec_arg))
        analysis = analyze_spec(spec_path)
        target_index = analysis.get("target_index", {})
        if not isinstance(target_index, dict):
            target_index = {}
        repo_list = sorted(target_index.keys()) if target_index else []
        if not repo_list:
            # Spec sin targets o solo root; incluir root_repo
            root_repo = str(workspace.get("project", {}).get("root_repo", "workspace-root"))
            if root_repo in repos_config:
                repo_list = [root_repo]
    else:
        raise SystemExit("Indica --repo <repo> o --spec <spec>.")

    skills_payload = load_skills_config()
    entries, _errors = skills_entries(skills_payload)
    entries_by_name = {str(e.get("name", "")).strip(): e for e in entries if str(e.get("name", "")).strip()}

    contexts: list[dict[str, object]] = []
    for repo_name in repo_list:
        repo_entry = repos_config.get(repo_name, {})
        if not isinstance(repo_entry, dict):
            continue
        runtime = str(repo_entry.get("runtime", "")).strip()
        agent_skill_refs = repo_entry.get("agent_skill_refs")
        if isinstance(agent_skill_refs, list):
            agent_skill_refs = [str(s).strip() for s in agent_skill_refs if str(s).strip()]
        else:
            agent_skill_refs = []
        if not runtime:
            runtime = "generic"
        if not agent_skill_refs and runtime:
            try:
                pack = resolve_runtime_pack(root, runtime, repo_name, str(repo_entry.get("path", repo_name)))
                agent_skill_refs = list(pack.get("agent_skill_refs", []))
            except Exception:
                pass
        agent_skills = []
        for ref in agent_skill_refs:
            path = _resolve_skill_path(
                ref,
                root=root,
                skills_entries_by_name=entries_by_name,
                rel=rel,
            )
            agent_skills.append({"name": ref, "path": path})

        contexts.append({
            "repo": repo_name,
            "runtime": runtime,
            "agent_skill_refs": agent_skill_refs,
            "agent_skills": agent_skills,
        })

    payload = {"contexts": contexts}
    if getattr(args, "json", False):
        print(json_dumps(payload))
        return 0
    for ctx in contexts:
        skills_str = ", ".join(ctx["agent_skill_refs"]) or "none"
        print(f"{ctx['repo']}: runtime={ctx['runtime']}, skills={skills_str}")
    return 0


SKYLL_API_BASE = "https://api.skyll.app"


def _fetch_skyll_search(query: str, limit: int = 10) -> dict[str, object]:
    """Consulta Skyll API (skills.sh + registry) para buscar skills por término."""
    params = urllib.parse.urlencode({"q": query, "limit": min(limit, 50), "include_content": "false"})
    url = f"{SKYLL_API_BASE}/search?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def command_skills_discover(
    args,
    *,
    json_dumps: Callable[[object], str],
) -> int:
    """
    Busca skills en tessl.io y skills.sh (vía Skyll API) por término.
    Devuelve candidatos sin instalar. Usa --json para salida estructurada.
    """
    query = str(getattr(args, "query", "") or "").strip()
    if not query:
        raise SystemExit("Indica un término de búsqueda: flow skills discover <query>")

    limit = int(getattr(args, "limit", 10) or 10)
    limit = max(1, min(50, limit))

    try:
        data = _fetch_skyll_search(query, limit=limit)
    except urllib.error.URLError as exc:
        raise SystemExit(f"No se pudo conectar a Skyll API: {exc}") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Error al procesar respuesta de Skyll: {exc}") from exc

    skills_raw = data.get("skills") or []
    candidates: list[dict[str, object]] = []
    for s in skills_raw:
        if not isinstance(s, dict):
            continue
        source = str(s.get("source", "")).strip()
        skill_id = str(s.get("id", "")).strip()
        if not source or not skill_id:
            continue
        refs = s.get("refs") or {}
        skills_sh_url = str(refs.get("skills_sh", "") or "") if isinstance(refs, dict) else ""
        github_url = str(refs.get("github", "") or "") if isinstance(refs, dict) else ""
        # Repo root para npx skills add (sin /tree/... ni /skills/...)
        if github_url and "/tree/" in github_url:
            source_url = github_url.split("/tree/")[0]
        elif github_url:
            source_url = github_url
        else:
            source_url = f"https://github.com/{source}"
        install_count = s.get("install_count")
        if install_count is not None and not isinstance(install_count, (int, float)):
            install_count = 0
        relevance = s.get("relevance_score")
        if relevance is not None and not isinstance(relevance, (int, float)):
            relevance = None
        candidates.append({
            "source": source,
            "skill_id": skill_id,
            "identifier": f"{source}@{skill_id}",
            "source_url": source_url,
            "install_count": install_count,
            "relevance_score": relevance,
            "skills_sh_url": skills_sh_url,
            "github_url": github_url,
            "title": str(s.get("title", skill_id)),
            "description": str(s.get("description", "")).strip() or None,
        })

    payload = {
        "query": query,
        "count": len(candidates),
        "candidates": candidates,
        "install_hint": "flow skills add <name> --provider skills-sh --source <source_url> --arg=--skill --arg=<skill_id>",
    }

    if getattr(args, "json", False):
        print(json_dumps(payload))
        return 0

    print(f"Skills encontrados para '{query}' ({len(candidates)}):")
    for c in candidates:
        inst = c.get("install_count")
        inst_str = f" ({inst} installs)" if inst is not None else ""
        print(f"  - {c['identifier']}{inst_str}")
        print(f"    {c.get('skills_sh_url') or c.get('github_url') or ''}")
        desc = c.get("description")
        if desc:
            print(f"    {desc[:80]}{'...' if len(desc) > 80 else ''}")
    return 0


def command_skills_autoskills(
    args,
    *,
    root: Path,
    json_dumps: Callable[[object], str],
) -> int:
    """
    Wrapper opcional sobre `npx autoskills`.
    - Por defecto ejecuta en modo `--dry-run`.
    - Con `--apply`, instala skills detectadas en el agente indicado.
    """
    project_dir = Path(str(getattr(args, "path", ".") or ".")).expanduser()
    if not project_dir.is_absolute():
        project_dir = (root / project_dir).resolve()
    if not project_dir.exists() or not project_dir.is_dir():
        raise SystemExit(f"El path `{project_dir}` no existe o no es un directorio.")

    command = ["npx", "-y", "autoskills", "--yes"]
    if not bool(getattr(args, "apply", False)):
        command.append("--dry-run")
    agents = [str(a).strip() for a in (getattr(args, "agent", None) or []) if str(a).strip()]
    if agents:
        command.extend(["--agent", *agents])

    env = dict(os.environ)
    env["CI"] = env.get("CI", "1")
    try:
        completed = subprocess.run(
            command,
            cwd=project_dir,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
    except OSError as exc:
        raise SystemExit(f"No pude ejecutar `npx autoskills`: {exc}") from exc

    combined = (completed.stdout + "\n" + completed.stderr).strip()
    output_tail = "\n".join(combined.splitlines()[-80:]) if combined else ""
    payload = {
        "mode": "apply" if bool(getattr(args, "apply", False)) else "dry-run",
        "path": str(project_dir),
        "command": command,
        "returncode": int(completed.returncode),
        "output_tail": output_tail,
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
    else:
        print(f"autoskills mode={payload['mode']} path={payload['path']}")
        print(f"command: {' '.join(shlex.quote(part) for part in command)}")
        print(output_tail or "(sin salida)")
    return int(completed.returncode)


def command_skills_doctor(
    args,
    *,
    load_skills_config,
    skills_entries,
    normalize_skill_provider: Callable[[str], str],
    workspace_executable_available: Callable[[str], bool],
    rel: Callable[[Path], str],
    skills_config_file: Path,
    json_dumps: Callable[[object], str],
) -> int:
    payload = load_skills_config()
    entries, errors = skills_entries(payload)
    findings = list(errors)

    provider_names = {str(entry["provider"]) for entry in entries}
    for provider in payload.get("providers", {}).keys():
        try:
            provider_names.add(normalize_skill_provider(str(provider)))
        except ValueError as exc:
            findings.append(str(exc))

    data = {
        "manifest": skills_config_file.name,
        "providers": [],
        "entries": [],
        "findings": findings,
    }

    for provider in sorted(provider_names):
        enabled = skills_provider_enabled(payload, provider)
        runtime_ok = skills_provider_runtime_available(provider, workspace_executable_available=workspace_executable_available)
        status = "ok" if runtime_ok or not enabled else "missing"
        data["providers"].append({"name": provider, "status": status, "enabled": enabled})
        if enabled and not runtime_ok:
            findings.append(f"El runtime del proveedor `{provider}` no esta disponible.")

    for entry in entries:
        local_source_path = entry.get("local_source_path")
        origin = rel(local_source_path) if isinstance(local_source_path, Path) else str(entry["source"])
        state = "enabled" if entry["enabled"] else "disabled"
        sync_mode = "sync" if entry["sync"] else "manual"
        data["entries"].append(
            {
                "name": entry["name"],
                "state": state,
                "sync_mode": sync_mode,
                "provider": entry["provider"],
                "kind": entry["kind"],
                "origin": origin,
                "requires": list(entry.get("requires", [])),
            }
        )
        if entry["required"] and not entry["enabled"]:
            findings.append(f"`{entry['name']}` es requerida pero esta deshabilitada.")
        if entry["provider"] == "tessl" and entry["kind"] == "skill" and local_source_path is None:
            findings.append(
                f"`{entry['name']}` requiere un source local relativo al workspace para `tessl skill import`."
            )
        missing_commands = [command for command in entry.get("requires", []) if shutil.which(str(command)) is None]
        if missing_commands:
            findings.append(
                f"`{entry['name']}` requiere comandos faltantes: {', '.join(sorted(missing_commands))}."
            )

    data["findings"] = findings
    if bool(getattr(args, "json", False)):
        print(json_dumps(data))
        return 1 if findings else 0

    print("Skills doctor")
    print(f"- manifest: {'ok' if skills_config_file.is_file() else 'missing'} ({skills_config_file.name})")
    for provider in data["providers"]:
        print(f"- provider {provider['name']}: {provider['status']} ({'enabled' if provider['enabled'] else 'disabled'})")
    for entry in data["entries"]:
        print(
            f"- entry {entry['name']}: {entry['state']}, {entry['sync_mode']}, "
            f"{entry['provider']}, {entry['kind']} -> {entry['origin']}, "
            f"requires={','.join(entry['requires']) or 'none'}"
        )
    if findings:
        print("", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    return 0


def command_skills_list(args, *, load_skills_config, skills_entries, serialize_skill_entry, json_dumps: Callable[[object], str]) -> int:
    payload = load_skills_config()
    entries, errors = skills_entries(payload)
    if errors:
        raise SystemExit("\n".join(f"- {error}" for error in errors))

    serialized = [serialize_skill_entry(entry) for entry in entries]
    if args.json:
        print(json_dumps({"providers": payload["providers"], "entries": serialized}))
        return 0

    if not serialized:
        print("No hay skills registradas en workspace.skills.json.")
        return 0

    for entry in serialized:
        print(
            f"- {entry['name']}: provider={entry['provider']}, kind={entry['kind']}, "
            f"sync={'yes' if entry['sync'] else 'no'}, enabled={'yes' if entry['enabled'] else 'no'}, "
            f"source={entry['source']}, requires={','.join(entry['requires']) or 'none'}"
        )
    return 0


def command_skills_add(
    args,
    *,
    load_skills_config,
    write_skills_config: Callable[[dict[str, object]], None],
    normalize_skill_provider: Callable[[str], str],
    normalize_skill_entry,
    skills_config_file: Path,
) -> int:
    payload = load_skills_config()
    providers = payload.setdefault("providers", {})
    entries = payload.setdefault("entries", [])
    if not isinstance(providers, dict) or not isinstance(entries, list):
        raise SystemExit(f"{skills_config_file.name} debe definir `providers` y `entries`.")

    name = args.name.strip()
    if not name:
        raise SystemExit("Debes indicar un nombre para la entrada de skill.")
    if any(isinstance(item, dict) and str(item.get("name", "")).strip() == name for item in entries):
        raise SystemExit(f"Ya existe una entrada `{name}` en {skills_config_file.name}.")

    provider = normalize_skill_provider(args.provider)
    kind = args.kind or ("package" if provider == "skills-sh" else "tile")
    entry = {
        "name": name,
        "provider": provider,
        "kind": kind,
        "source": args.source.strip(),
        "enabled": not args.disabled,
        "required": args.required,
        "sync": not args.no_sync,
        "args": list(args.arg or []),
        "requires": list(args.require or []),
        "notes": args.notes or "",
    }

    try:
        normalize_skill_entry(entry, len(entries) + 1)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    providers.setdefault(provider, {"enabled": True})
    entries.append(entry)
    write_skills_config(payload)

    print(f"Skill agregada: {name}")
    print(f"- provider: {provider}")
    print(f"- kind: {kind}")
    print(f"- source: {entry['source']}")
    print(f"- requires: {', '.join(entry['requires']) if entry['requires'] else 'none'}")
    print(f"- config: {skills_config_file.name}")
    return 0


def _first(iterable: Iterable[object]) -> object | None:
    for item in iterable:
        return item
    return None


def command_skills_install(  # type: ignore[too-many-arguments]
    args,
    *,
    load_skills_config,
    write_skills_config: Callable[[dict[str, object]], None],
    normalize_skill_provider: Callable[[str], str],
    normalize_skill_entry,
    skills_config_file: Path,
) -> int:
    """
    Flujo de alto nivel:
    1. Recibe un identificador de skill (`identifier`) y un nombre opcional (`--name`).
    2. Si el provider no viene fijado, intenta construir dos candidatos:
       - Tessl (tile/package remoto o local).
       - skills-sh (package).
       Si ambos son validos, devuelve listado y exige `--provider` explicito.
    3. Registra/actualiza la entrada en `workspace.skills.json` si no existia.
    4. Si `--runtime` viene informado, delega la actualizacion del runtime al caller.
    """

    payload = load_skills_config()
    providers = payload.setdefault("providers", {})
    entries = payload.setdefault("entries", [])
    if not isinstance(providers, dict) or not isinstance(entries, list):
        raise SystemExit(f"{skills_config_file.name} debe definir `providers` y `entries`.")

    identifier = str(args.identifier).strip()
    if not identifier:
        raise SystemExit("Debes indicar un identificador de skill para instalar.")

    manifest_name = str(getattr(args, "name", "") or "").strip() or identifier

    # Si ya existe una entrada con ese nombre, reutilizarla en vez de crear una nueva.
    existing_raw = _first(
        item
        for item in entries
        if isinstance(item, dict) and str(item.get("name", "")).strip() == manifest_name
    )
    if existing_raw is not None:
        # Nada que registrar; dejamos que el caller actualice runtimes.
        print(f"Skill ya registrada en {skills_config_file.name}: {manifest_name}")
        return 0

    provider_arg = getattr(args, "provider", None)
    chosen_provider: str | None = None
    candidate_entries: list[dict[str, object]] = []

    def _build_candidate(provider_value: str) -> dict[str, object] | None:
        provider = normalize_skill_provider(provider_value)
        kind = "package" if provider == "skills-sh" else "tile"
        candidate = {
            "name": manifest_name,
            "provider": provider,
            "kind": kind,
            "source": identifier,
            "enabled": True,
            "required": False,
            "sync": True,
            "args": [],
            "requires": [],
            "notes": "",
        }
        # Usamos el normalizador para validar la entrada y derivar metadata como local_source_path.
        try:
            normalized = normalize_skill_entry(candidate, len(entries) + 1)
        except ValueError:
            return None
        return normalized

    if provider_arg:
        # Provider explicito: solo un candidato.
        normalized = _build_candidate(provider_arg)
        if normalized is None:
            raise SystemExit(f"No se pudo construir una entrada valida para provider `{provider_arg}`.")
        candidate_entries = [normalized]
    else:
        # Heuristica de resolucion: primero Tessl, luego skills-sh.
        tessl_candidate = _build_candidate("tessl")
        if tessl_candidate is not None:
            candidate_entries.append(tessl_candidate)
        skills_sh_candidate = _build_candidate("skills-sh")
        if skills_sh_candidate is not None:
            candidate_entries.append(skills_sh_candidate)

    if not candidate_entries:
        raise SystemExit(
            f"No se pudo resolver `{identifier}` como skill valido ni en Tessl ni en skills.sh."
        )

    if len(candidate_entries) > 1 and not provider_arg:
        print("Se encontraron multiples posibles providers para este identificador:")
        for entry in candidate_entries:
            print(
                f"- {entry['provider']}: name={entry['name']}, kind={entry['kind']}, source={entry['source']}"
            )
        print(
            "\nReintenta con `--provider tessl` o `--provider skills-sh` para desambiguar."
        )
        return 1

    chosen = candidate_entries[0]
    chosen_provider = str(chosen["provider"])

    providers.setdefault(chosen_provider, {"enabled": True})
    # Reinsertamos sin `local_source_path` para mantener el shape original del manifest.
    raw_entry = {
        "name": chosen["name"],
        "provider": chosen["provider"],
        "kind": chosen["kind"],
        "source": chosen["source"],
        "enabled": chosen["enabled"],
        "required": chosen["required"],
        "sync": chosen["sync"],
        "args": chosen["args"],
        "requires": chosen["requires"],
        "notes": chosen["notes"],
    }
    entries.append(raw_entry)
    write_skills_config(payload)

    print(f"Skill instalada en {skills_config_file.name}: {chosen['name']}")
    print(f"- provider: {chosen_provider}")
    print(f"- source: {chosen['source']}")
    print(f"- kind: {chosen['kind']}")

    # La actualizacion de runtime corre a cargo del wrapper en `flow`, que recibe `args.runtime`.
    return 0


def command_skills_sync(
    args,
    *,
    require_dirs: Callable[[], None],
    load_skills_config,
    skills_entries,
    normalize_skill_provider: Callable[[str], str],
    rel: Callable[[Path], str],
    capture_workspace_tool,
    utc_now: Callable[[], str],
    write_json: Callable[[Path, dict[str, object]], None],
    skills_report_root: Path,
    format_findings: Callable[[list[str]], list[str]],
    workspace_executable_available: Callable[[str], bool],
) -> int:
    require_dirs()
    payload = load_skills_config()
    entries, errors = skills_entries(payload)
    if errors:
        raise SystemExit("\n".join(f"- {error}" for error in errors))

    provider_filter = normalize_skill_provider(args.provider) if args.provider else None
    name_filter = {name.strip() for name in args.name or [] if name.strip()}
    selected: list[dict[str, object]] = []
    findings: list[str] = []

    for entry in entries:
        if provider_filter and entry["provider"] != provider_filter:
            continue
        if name_filter and entry["name"] not in name_filter:
            continue
        if not entry["enabled"]:
            if entry["name"] in name_filter:
                findings.append(f"`{entry['name']}` esta deshabilitada y no se sincronizo.")
            continue
        if not entry["sync"] and not name_filter:
            continue
        selected.append(entry)

    if not selected:
        if findings:
            raise SystemExit("\n".join(findings))
        print("No hay skills elegibles para sincronizar.")
        return 0

    executions: list[dict[str, object]] = []
    for entry in selected:
        provider = str(entry["provider"])
        if not skills_provider_enabled(payload, provider):
            findings.append(f"El proveedor `{provider}` esta deshabilitado para `{entry['name']}`.")
            continue
        if not skills_provider_runtime_available(provider, workspace_executable_available=workspace_executable_available):
            findings.append(f"El runtime del proveedor `{provider}` no esta disponible para `{entry['name']}`.")
            continue
        missing_commands = [command for command in entry.get("requires", []) if shutil.which(str(command)) is None]
        if missing_commands:
            findings.append(
                f"`{entry['name']}` no se sincronizo porque faltan comandos requeridos: {', '.join(sorted(missing_commands))}."
            )
            continue

        try:
            commands = skill_entry_commands(entry, rel=rel)
        except SystemExit as exc:
            findings.append(str(exc))
            continue

        for command in commands:
            record = {
                "name": entry["name"],
                "provider": provider,
                "kind": entry["kind"],
                "source": entry["source"],
                "command": command,
            }
            if args.dry_run:
                record["returncode"] = 0
                record["output_tail"] = "dry-run"
            else:
                execution = capture_workspace_tool(command)
                record["returncode"] = int(execution["returncode"])
                record["output_tail"] = execution["output_tail"]
            executions.append(record)

    stamp = skills_report_stamp(utc_now=utc_now)
    json_path = skills_report_root / f"sync-{stamp}.json"
    md_path = skills_report_root / f"sync-{stamp}.md"
    report_payload = {
        "generated_at": utc_now(),
        "dry_run": bool(args.dry_run),
        "provider": provider_filter,
        "names": sorted(name_filter),
        "executions": executions,
        "findings": findings,
    }
    write_json(json_path, report_payload)

    lines = [
        "# Skills Sync Report",
        "",
        f"- Generated at: `{report_payload['generated_at']}`",
        f"- Dry run: `{report_payload['dry_run']}`",
        f"- Provider filter: `{provider_filter or 'all'}`",
        f"- Name filter: `{', '.join(sorted(name_filter)) if name_filter else 'all'}`",
        "",
        "## Executions",
        "",
    ]
    if executions:
        for execution in executions:
            lines.append(
                f"- `{execution['name']}` ({execution['provider']}/{execution['kind']}): "
                f"`{' '.join(shlex.quote(part) for part in execution['command'])}` -> `{execution['returncode']}`"
            )
    else:
        lines.append("- Ninguna.")
    lines.extend(["", "## Findings", ""])
    lines.extend(format_findings(findings))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(rel(json_path))
    print(rel(md_path))
    if findings:
        return 1
    return 1 if any(int(execution["returncode"]) != 0 for execution in executions) else 0
