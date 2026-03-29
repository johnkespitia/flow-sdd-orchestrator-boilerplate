from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

EXECUTABLE_FRONTMATTER_STATUSES = {"approved"}
STRICT_CI_FRONTMATTER_STATUSES = {"approved", "released"}
DEPENDENCY_READY_FRONTMATTER_STATUSES = {"approved", "released"}
TERMINAL_FRONTMATTER_STATUSES = {"released"}


@dataclass(frozen=True)
class SpecConfig:
    root: Path
    specs_root: Path
    feature_specs: Path
    root_repo: str
    default_targets: dict[str, list[str]]
    repo_prefixes: dict[str, str]
    target_roots: dict[str, set[str]]
    test_required_roots: dict[str, set[str]]
    test_hints: dict[str, str]
    required_frontmatter_fields: tuple[str, ...]
    test_ref_re: re.Pattern[str]
    todo_re: re.Pattern[str]


def build_spec_config(
    *,
    root: Path,
    specs_root: Path,
    feature_specs: Path,
    root_repo: str,
    default_targets: dict[str, list[str]],
    repo_prefixes: dict[str, str],
    target_roots: dict[str, set[str]],
    test_required_roots: dict[str, set[str]],
    test_hints: dict[str, str],
    required_frontmatter_fields: tuple[str, ...],
    test_ref_re: re.Pattern[str],
    todo_re: re.Pattern[str],
) -> SpecConfig:
    return SpecConfig(
        root=root,
        specs_root=specs_root,
        feature_specs=feature_specs,
        root_repo=root_repo,
        default_targets=default_targets,
        repo_prefixes=repo_prefixes,
        target_roots=target_roots,
        test_required_roots=test_required_roots,
        test_hints=test_hints,
        required_frontmatter_fields=required_frontmatter_fields,
        test_ref_re=test_ref_re,
        todo_re=todo_re,
    )


def normalize_frontmatter_status(value: object) -> str:
    return str(value or "").strip().lower()


def frontmatter_status_allows_strict_ci(value: object) -> bool:
    return normalize_frontmatter_status(value) in STRICT_CI_FRONTMATTER_STATUSES


def frontmatter_status_allows_dependencies(value: object) -> bool:
    return normalize_frontmatter_status(value) in DEPENDENCY_READY_FRONTMATTER_STATUSES


def frontmatter_status_allows_execution(value: object) -> bool:
    return normalize_frontmatter_status(value) in EXECUTABLE_FRONTMATTER_STATUSES


def frontmatter_status_is_terminal(value: object) -> bool:
    return normalize_frontmatter_status(value) in TERMINAL_FRONTMATTER_STATUSES


def all_spec_paths(config: SpecConfig) -> list[Path]:
    return sorted(config.specs_root.rglob("*.spec.md"))


def _extract_frontmatter_block(text: str) -> Optional[str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return None
    return "\n".join(lines[1:end])


def parse_frontmatter(spec_path: Path) -> dict[str, object]:
    text = spec_path.read_text(encoding="utf-8")
    frontmatter_text = _extract_frontmatter_block(text)
    if frontmatter_text is None:
        return {}
    try:
        payload = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{spec_path} tiene frontmatter YAML invalido: {exc}") from exc
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{spec_path} debe declarar un objeto YAML en el frontmatter.")
    return {str(key): value for key, value in payload.items()}


def _string_list_field(frontmatter: dict[str, object], key: str) -> tuple[list[str], list[str]]:
    value = frontmatter.get(key)
    if value is None:
        return [], []
    if isinstance(value, str):
        candidate = value.strip()
        return ([candidate] if candidate else []), []
    if not isinstance(value, list):
        return [], [f"`{key}` debe declararse como lista YAML o string."]

    items: list[str] = []
    errors: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str):
            errors.append(f"`{key}` debe contener strings; el item #{index} no es valido.")
            continue
        candidate = item.strip()
        if candidate:
            items.append(candidate)
    return items, errors


def _object_list_field(frontmatter: dict[str, object], key: str) -> tuple[list[dict[str, Any]], list[str]]:
    value = frontmatter.get(key)
    if value is None:
        return [], []
    if not isinstance(value, list):
        return [], [f"`{key}` debe declararse como lista YAML."]

    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            errors.append(f"`{key}` debe contener objetos; el item #{index} no es valido.")
            continue
        items.append({str(field): field_value for field, field_value in item.items()})
    return items, errors


def _is_yaml_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _mapping_findings(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, dict):
        return [f"`{label}` debe declararse como objeto YAML."]

    findings: list[str] = []
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not key:
            findings.append(f"`{label}` no puede usar keys vacias.")
            continue
        if not _is_yaml_scalar(raw_value):
            findings.append(f"`{label}.{key}` debe usar un valor escalar YAML.")
    return findings


def _string_list_findings(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return [f"`{label}` debe declararse como lista."]

    findings: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            findings.append(f"`{label}` item #{index} debe ser un string no vacio.")
    return findings


def _string_or_int_list_findings(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return [f"`{label}` debe declararse como lista."]

    findings: list[str] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            findings.append(f"`{label}` item #{index} debe ser string o entero.")
            continue
        if isinstance(item, str) and not item.strip():
            findings.append(f"`{label}` item #{index} no puede ser un string vacio.")
    return findings


def _string_field(value: Any, label: str) -> tuple[str, list[str]]:
    if value is None:
        return "", []
    if not isinstance(value, str):
        return "", [f"`{label}` debe declararse como string."]
    return value.strip(), []


def _bool_field(value: Any, label: str) -> tuple[bool, list[str]]:
    if value is None:
        return False, []
    if isinstance(value, bool):
        return value, []
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "1"}:
            return True, []
        if normalized in {"false", "no", "off", "0"}:
            return False, []
    return False, [f"`{label}` debe declararse como booleano."]


def _schema_version(frontmatter: dict[str, object]) -> tuple[int, list[str]]:
    value = frontmatter.get("schema_version")
    if value is None:
        return 1, []
    if isinstance(value, bool):
        return 1, ["`schema_version` debe ser un entero."]
    if isinstance(value, int):
        version = value
    elif isinstance(value, str) and value.strip().isdigit():
        version = int(value.strip())
    else:
        return 1, ["`schema_version` debe ser un entero."]
    if version < 1:
        return version, ["`schema_version` debe ser mayor o igual a 1."]
    return version, []


def replace_frontmatter_status(spec_path: Path, status: str) -> None:
    text = spec_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"{spec_path} no tiene frontmatter YAML.")

    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise SystemExit(f"{spec_path} tiene frontmatter invalido.")

    frontmatter = parts[1]
    body = parts[2]
    if re.search(r"^status:\s*.+$", frontmatter, flags=re.MULTILINE):
        frontmatter = re.sub(
            r"^status:\s*.+$",
            f"status: {status}",
            frontmatter,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        frontmatter += f"status: {status}\n"
    spec_path.write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")


def repo_prefix_examples(config: SpecConfig) -> str:
    prefixes = [f"'{prefix}'" for prefix in config.repo_prefixes.values()]
    return ", ".join(prefixes)


def path_matches_any_root(relative: str, roots: set[str]) -> bool:
    normalized = relative.strip("/").replace("\\", "/")
    if not normalized:
        return False
    for root in roots:
        candidate = str(root).strip("/").replace("\\", "/")
        if not candidate:
            continue
        if normalized == candidate or normalized.startswith(f"{candidate}/"):
            return True
    return False


def classify_routed_path(raw_path: str, *, config: SpecConfig) -> tuple[str, str]:
    value = raw_path.strip()
    if not value:
        raise ValueError("Se encontro una ruta vacia en la spec.")

    for repo, prefix in config.repo_prefixes.items():
        if value.startswith(prefix):
            relative = value[len(prefix) :]
            break
    else:
        if not value.startswith("../../"):
            configured_prefixes = repo_prefix_examples(config)
            raise ValueError(
                f"Ruta invalida '{raw_path}': debe empezar con '../../', "
                f"o alguno de los prefijos configurados: {configured_prefixes}."
            )
        repo = config.root_repo
        relative = value[len("../../") :]

    relative = relative.strip("/")
    if not relative:
        raise ValueError(f"Ruta invalida '{raw_path}': falta la ruta relativa despues del repo.")

    if not path_matches_any_root(relative, config.target_roots[repo]):
        allowed = ", ".join(sorted(config.target_roots[repo]))
        raise ValueError(
            f"Ruta invalida '{raw_path}': '{relative}' no coincide con un root permitido para {repo}. "
            f"Roots permitidos: {allowed}."
        )

    return repo, relative.replace("\\", "/")


def collect_routed_paths(
    paths: list[str],
    *,
    config: SpecConfig,
) -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    indexed: dict[str, list[dict[str, str]]] = {}
    errors: list[str] = []

    for raw_path in paths:
        try:
            repo, relative = classify_routed_path(raw_path, config=config)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        indexed.setdefault(repo, []).append({"raw": raw_path, "relative": relative})

    return indexed, errors


def require_routed_paths(
    paths: list[str],
    label: str,
    *,
    config: SpecConfig,
) -> dict[str, list[dict[str, str]]]:
    if not paths:
        raise SystemExit(f"La spec debe declarar al menos un {label}.")

    indexed, errors = collect_routed_paths(paths, config=config)
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(f"{label.capitalize()} invalidos:\n{joined}")

    return indexed


def repo_entries_require_tests(config: SpecConfig, repo: str, entries: list[dict[str, str]]) -> bool:
    required_roots = config.test_required_roots.get(repo, set())
    if not required_roots:
        return False

    for entry in entries:
        relative = str(entry.get("relative", "")).strip("/")
        if not relative:
            continue
        if path_matches_any_root(relative, required_roots):
            return True

    return False


def repos_missing_test_refs(
    config: SpecConfig,
    target_index: dict[str, list[dict[str, str]]],
    test_index: dict[str, list[dict[str, str]]],
) -> list[str]:
    missing: list[str] = []
    for repo, entries in target_index.items():
        if repo == config.root_repo:
            continue
        if not repo_entries_require_tests(config, repo, entries):
            continue
        if not test_index.get(repo):
            missing.append(repo)
    return missing


def extract_test_references(text: str, *, config: SpecConfig) -> list[str]:
    return config.test_ref_re.findall(text)


def extract_backticked_test_references(text: str) -> list[str]:
    return re.findall(r"`\[@test\]\s+([^`\n]+)`", text)


def count_todos(text: str, *, config: SpecConfig) -> int:
    return len(config.todo_re.findall(text))


def render_test_plan_hints(config: SpecConfig, repos: list[str]) -> str:
    lines: list[str] = []
    for repo in repos:
        hint = config.test_hints.get(repo)
        if hint:
            lines.append(f"- [@test] {hint}")

    if not lines:
        lines.append("- Evidencia de verificacion del workspace: review manual o check operativo.")

    return "\n".join(lines)


def extract_markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    target = heading.strip().lower()
    start_index: Optional[int] = None
    for index, line in enumerate(lines):
        if line.strip().lower() == f"## {target}":
            start_index = index + 1
            break
    if start_index is None:
        return ""

    end_index = len(lines)
    for index in range(start_index, len(lines)):
        if lines[index].startswith("## "):
            end_index = index
            break
    return "\n".join(lines[start_index:end_index]).strip()


def parse_slice_breakdown(
    text: str,
    *,
    config: SpecConfig,
    declared_targets: list[str],
) -> tuple[list[dict[str, object]], list[str], bool]:
    section = extract_markdown_section(text, "Slice Breakdown")
    if not section:
        return [], ["Falta la seccion `## Slice Breakdown` con un bloque YAML."], False

    block_match = re.search(r"```ya?ml\s*\n(?P<body>.*?)(?:\n```)", section, flags=re.DOTALL | re.IGNORECASE)
    if block_match is None:
        return [], ["La seccion `## Slice Breakdown` debe incluir un bloque ```yaml```."], True

    body = block_match.group("body")
    try:
        payload = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        return [], [f"El bloque YAML de `## Slice Breakdown` es invalido: {exc}"], True

    if not isinstance(payload, list):
        return [], ["`## Slice Breakdown` debe declarar una lista YAML de slices."], True

    findings: list[str] = []
    slices: list[dict[str, object]] = []
    seen_names: set[str] = set()
    declared_target_set = {item.strip() for item in declared_targets if item.strip()}

    for index, raw_item in enumerate(payload, start=1):
        if not isinstance(raw_item, dict):
            findings.append(f"`Slice Breakdown` item #{index} debe ser un objeto YAML.")
            continue

        item = {str(key): value for key, value in raw_item.items()}
        name, name_errors = _string_field(item.get("name"), f"slice_breakdown[{index}].name")
        findings.extend(name_errors)
        if not name:
            findings.append(f"`slice_breakdown[{index}].name` no puede ser vacio.")
            continue
        if name in seen_names:
            findings.append(f"El nombre de slice `{name}` esta duplicado en `Slice Breakdown`.")
            continue
        seen_names.add(name)

        targets, target_errors = _string_list_field(item, "targets")
        findings.extend(f"`slice {name}`: {error}" for error in target_errors)
        if not targets:
            findings.append(f"La slice `{name}` debe declarar al menos un target.")
            continue

        hot_area, hot_area_errors = _string_field(item.get("hot_area"), f"slice_breakdown[{index}].hot_area")
        findings.extend(hot_area_errors)
        if not hot_area:
            findings.append(f"La slice `{name}` debe declarar `hot_area`.")

        depends_on, depends_on_errors = _string_list_field(item, "depends_on")
        findings.extend(f"`slice {name}`: {error}" for error in depends_on_errors)
        semantic_locks, semantic_lock_errors = _string_list_field(item, "semantic_locks")
        findings.extend(f"`slice {name}`: {error}" for error in semantic_lock_errors)

        target_index, routing_errors = collect_routed_paths(targets, config=config)
        findings.extend(f"La slice `{name}` tiene target invalido: {error}" for error in routing_errors)
        if routing_errors:
            continue
        if len(target_index) != 1:
            findings.append(f"La slice `{name}` debe pertenecer a un solo repo.")
            continue

        repo = next(iter(target_index))
        if any(target not in declared_target_set for target in targets):
            findings.append(f"La slice `{name}` solo puede usar targets declarados en el frontmatter principal.")
            continue

        slices.append(
            {
                "name": name,
                "repo": repo,
                "targets": targets,
                "target_index": target_index,
                "hot_area": hot_area,
                "depends_on": depends_on,
                "semantic_locks": semantic_locks,
            }
        )

    valid_names = {str(item.get("name", "")).strip() for item in slices}
    for item in slices:
        for dependency in item.get("depends_on", []):
            if dependency not in valid_names:
                findings.append(
                    f"La slice `{item['name']}` depende de `{dependency}`, pero esa slice no existe en `Slice Breakdown`."
                )

    return slices, findings, True


def _analysis_target_roots(analysis: dict[str, object]) -> set[str]:
    roots: set[str] = set()
    for entries in analysis.get("target_index", {}).values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            relative = str(entry.get("relative", "")).strip("/")
            if not relative:
                continue
            roots.add(relative.split("/", 1)[0])
    return roots


def slice_governance_policy(analysis: dict[str, object]) -> dict[str, object]:
    frontmatter = analysis.get("frontmatter", {})
    schema_version = int(analysis.get("schema_version", 1) or 1)
    applies = schema_version >= 3
    single_slice_reason = str(analysis.get("single_slice_reason", "") or "").strip()
    multi_domain = bool(analysis.get("multi_domain", False))
    phases = [str(item).strip() for item in analysis.get("phases", []) if str(item).strip()]
    repo_count = len(analysis.get("target_index", {}))
    target_roots = _analysis_target_roots(analysis)
    target_count = len([item for item in analysis.get("targets", []) if str(item).strip()])

    min_slice_count = 1
    reasons: list[str] = []
    if applies:
        min_slice_count = 2
        reasons.append("`schema_version: 3` requiere multi-slice por defecto.")
        if repo_count > min_slice_count:
            min_slice_count = repo_count
            reasons.append("La spec afecta multiples repos.")
        if multi_domain:
            min_slice_count = max(min_slice_count, 2)
            reasons.append("`multi_domain: true` requiere al menos 2 slices.")
        if phases:
            min_slice_count = max(min_slice_count, 2 if len(phases) == 1 else 3)
            reasons.append("La spec declara `phases`, por lo que no debe quedar en una sola slice.")
        if len(target_roots) >= 3 or target_count >= 5:
            min_slice_count = max(min_slice_count, 3)
            reasons.append("El alcance toca varios target roots o demasiados targets.")

    return {
        "applies": applies,
        "schema_version": schema_version,
        "single_slice_reason": single_slice_reason,
        "multi_domain": multi_domain,
        "phases": phases,
        "target_roots": sorted(target_roots),
        "target_count": target_count,
        "repo_count": repo_count,
        "min_slice_count": min_slice_count,
        "reasons": reasons,
    }


def slice_governance_findings(
    analysis: dict[str, object],
    *,
    planned_slices: Optional[list[dict[str, object]]] = None,
) -> list[str]:
    policy = slice_governance_policy(analysis)
    if not bool(policy["applies"]):
        return []

    findings: list[str] = []
    findings.extend(str(item) for item in analysis.get("slice_breakdown_errors", []))

    declared_slices = [
        item for item in analysis.get("slice_breakdown", []) if isinstance(item, dict)
    ]
    candidate_slices = planned_slices if planned_slices is not None else declared_slices
    candidate_slices = [item for item in candidate_slices if isinstance(item, dict)]
    slice_count = len(candidate_slices)
    single_slice_reason = str(policy["single_slice_reason"]).strip()

    if slice_count == 0:
        findings.append("La spec debe declarar slices operativas en `## Slice Breakdown`.")
        return findings

    if slice_count < int(policy["min_slice_count"]):
        if slice_count == 1 and single_slice_reason:
            pass
        else:
            reasons = "; ".join(str(item) for item in policy["reasons"]) or "politica multi-slice del workspace"
            findings.append(
                f"El plan/spec solo declara `{slice_count}` slice(s), pero la gobernanza exige al menos "
                f"`{policy['min_slice_count']}`. Razones: {reasons}."
            )

    if slice_count == 1 and not single_slice_reason:
        findings.append(
            "Una spec `schema_version: 3` no puede quedar en una sola slice sin `single_slice_reason`."
        )

    if single_slice_reason and single_slice_reason.lower().startswith("todo"):
        findings.append("`single_slice_reason` no puede quedar en placeholder.")

    names = [str(item.get("name", "")).strip() for item in candidate_slices if str(item.get("name", "")).strip()]
    if len(names) != len(set(names)):
        findings.append("El plan tiene slices con nombres duplicados.")

    repo_hot_areas: dict[tuple[str, str], list[str]] = {}
    for item in candidate_slices:
        repo = str(item.get("repo", "")).strip()
        hot_area = str(item.get("hot_area", "")).strip()
        name = str(item.get("name", "")).strip() or "<sin-nombre>"
        if repo and hot_area:
            repo_hot_areas.setdefault((repo, hot_area), []).append(name)
        elif len(candidate_slices) > 1:
            findings.append(f"La slice `{name}` debe declarar `hot_area` para permitir concurrencia gobernada.")

    for (repo, hot_area), owners in sorted(repo_hot_areas.items()):
        if len(owners) > 1:
            findings.append(
                f"Las slices `{', '.join(sorted(owners))}` comparten `hot_area={hot_area}` en `{repo}`; "
                "deben separarse para evitar serializacion."
            )

    if declared_slices and planned_slices is not None:
        declared_names = {str(item.get("name", "")).strip() for item in declared_slices if str(item.get("name", "")).strip()}
        planned_names = {str(item.get("name", "")).strip() for item in candidate_slices if str(item.get("name", "")).strip()}
        if declared_names != planned_names:
            findings.append("El plan generado no coincide con las slices declaradas en `## Slice Breakdown`.")

    return findings


def analyze_spec(spec_path: Path, *, config: SpecConfig) -> dict[str, object]:
    text = spec_path.read_text(encoding="utf-8")
    frontmatter_errors: list[str] = []
    try:
        frontmatter = parse_frontmatter(spec_path)
    except ValueError as exc:
        frontmatter = {}
        frontmatter_errors.append(str(exc))

    schema_version, schema_errors = _schema_version(frontmatter)
    frontmatter_errors.extend(schema_errors)
    targets, target_type_errors = _string_list_field(frontmatter, "targets")
    depends_on, depends_on_errors = _string_list_field(frontmatter, "depends_on")
    required_runtimes, required_runtimes_errors = _string_list_field(frontmatter, "required_runtimes")
    required_services, required_services_errors = _string_list_field(frontmatter, "required_services")
    required_capabilities, required_capabilities_errors = _string_list_field(frontmatter, "required_capabilities")
    single_slice_reason, single_slice_reason_errors = _string_field(frontmatter.get("single_slice_reason"), "single_slice_reason")
    phases, phases_errors = _string_list_field(frontmatter, "phases")
    multi_domain, multi_domain_errors = _bool_field(frontmatter.get("multi_domain"), "multi_domain")
    stack_projects, stack_projects_errors = _object_list_field(frontmatter, "stack_projects")
    stack_services, stack_services_errors = _object_list_field(frontmatter, "stack_services")
    stack_capabilities, stack_capabilities_errors = _string_list_field(frontmatter, "stack_capabilities")
    infra_targets, infra_targets_errors = _string_list_field(frontmatter, "infra_targets")
    frontmatter_errors.extend(target_type_errors)
    frontmatter_errors.extend(depends_on_errors)
    frontmatter_errors.extend(required_runtimes_errors)
    frontmatter_errors.extend(required_services_errors)
    frontmatter_errors.extend(required_capabilities_errors)
    frontmatter_errors.extend(single_slice_reason_errors)
    frontmatter_errors.extend(phases_errors)
    frontmatter_errors.extend(multi_domain_errors)
    frontmatter_errors.extend(stack_projects_errors)
    frontmatter_errors.extend(stack_services_errors)
    frontmatter_errors.extend(stack_capabilities_errors)
    frontmatter_errors.extend(infra_targets_errors)
    target_index, target_errors = collect_routed_paths(targets, config=config)
    slice_breakdown, slice_breakdown_errors, has_slice_breakdown = parse_slice_breakdown(
        text,
        config=config,
        declared_targets=targets,
    )
    test_refs = extract_test_references(text, config=config)
    backticked_test_refs = extract_backticked_test_references(text)
    test_index, test_errors = collect_routed_paths(test_refs, config=config)
    missing_frontmatter = [field for field in config.required_frontmatter_fields if not frontmatter.get(field)]

    return {
        "spec_path": spec_path,
        "text": text,
        "frontmatter": frontmatter,
        "frontmatter_errors": frontmatter_errors,
        "schema_version": schema_version,
        "targets": targets,
        "target_index": target_index,
        "target_errors": target_errors,
        "test_refs": test_refs,
        "backticked_test_refs": backticked_test_refs,
        "test_index": test_index,
        "test_errors": test_errors,
        "depends_on": depends_on,
        "required_runtimes": required_runtimes,
        "required_services": required_services,
        "required_capabilities": required_capabilities,
        "single_slice_reason": single_slice_reason,
        "phases": phases,
        "multi_domain": multi_domain,
        "stack_projects": stack_projects,
        "stack_services": stack_services,
        "stack_capabilities": stack_capabilities,
        "infra_targets": infra_targets,
        "slice_breakdown": slice_breakdown,
        "slice_breakdown_errors": slice_breakdown_errors,
        "has_slice_breakdown": has_slice_breakdown,
        "todo_count": count_todos(text, config=config),
        "missing_frontmatter": missing_frontmatter,
    }


def test_reference_findings(
    analysis: dict[str, object],
    *,
    config: SpecConfig,
    repo_root: Callable[[str], Path],
    validate_test_reference_patterns: Callable[[str, Path, list[str]], tuple[list[str], list[str], list[str]]],
) -> list[str]:
    findings: list[str] = []
    test_index = analysis["test_index"]
    for repo, entries in test_index.items():
        if repo == config.root_repo:
            continue
        repo_path = repo_root(repo)
        patterns = [str(entry["relative"]) for entry in entries]
        _, missing, invalid = validate_test_reference_patterns(repo, repo_path, patterns)
        findings.extend(f"La referencia `[@test] {pattern}` no existe en `{repo}`." for pattern in missing)
        findings.extend(invalid)
    return findings


def ensure_spec_ready_for_approval(
    spec_path: Path,
    *,
    config: SpecConfig,
    repo_root: Callable[[str], Path],
    validate_test_reference_patterns: Callable[[str, Path, list[str]], tuple[list[str], list[str], list[str]]],
    available_project_runtime_names: Callable[[], list[str]],
    available_service_runtime_names: Callable[[], list[str]],
    available_capability_names: Callable[[], list[str]],
    resolve_runtime_pack,
    resolve_spec: Callable[[str], Path],
) -> dict[str, object]:
    analysis = analyze_spec(spec_path, config=config)
    blockers: list[str] = []
    frontmatter = analysis["frontmatter"]

    blockers.extend(str(error) for error in analysis["frontmatter_errors"])
    for field in analysis["missing_frontmatter"]:
        blockers.append(f"Falta el campo de frontmatter `{field}`.")

    blockers.extend(str(error) for error in analysis["target_errors"])
    blockers.extend(str(error) for error in analysis["test_errors"])
    blockers.extend(
        "No uses `[@test]` dentro de backticks; declara la referencia como texto plano."
        for _ in analysis.get("backticked_test_refs", [])
    )
    blockers.extend(
        test_reference_findings(
            analysis,
            config=config,
            repo_root=repo_root,
            validate_test_reference_patterns=validate_test_reference_patterns,
        )
    )
    blockers.extend(
        spec_dependency_findings(
            analysis,
            config=config,
            available_project_runtime_names=available_project_runtime_names,
            available_service_runtime_names=available_service_runtime_names,
            available_capability_names=available_capability_names,
            resolve_runtime_pack=resolve_runtime_pack,
            resolve_spec=resolve_spec,
            parse_frontmatter=parse_frontmatter,
        )
    )
    blockers.extend(slice_governance_findings(analysis))

    description = str(frontmatter.get("description", "")).strip().lower()
    if not description or description.startswith("todo"):
        blockers.append("`description` debe describir el resultado observable sin placeholders.")

    if analysis["todo_count"]:
        blockers.append("La spec aun contiene `TODO`; cierralos antes de aprobar.")

    missing_repo_tests = repos_missing_test_refs(config, analysis["target_index"], analysis["test_index"])
    if missing_repo_tests:
        blockers.append(
            "Faltan referencias `[@test]` para: " + ", ".join(sorted(missing_repo_tests)) + "."
        )

    if blockers:
        joined = "\n".join(f"- {blocker}" for blocker in blockers)
        raise SystemExit(f"La spec no esta lista para aprobar:\n{joined}")

    return analysis


def format_findings(findings: list[str]) -> list[str]:
    if not findings:
        return ["- Sin hallazgos."]
    return [f"- {finding}" for finding in findings]


def frontmatter_list(frontmatter: dict[str, object], key: str) -> list[str]:
    items, _ = _string_list_field(frontmatter, key)
    return items


def spec_dependency_findings(
    analysis: dict[str, object],
    *,
    config: SpecConfig,
    available_project_runtime_names: Callable[[], list[str]],
    available_service_runtime_names: Callable[[], list[str]],
    available_capability_names: Callable[[], list[str]],
    resolve_runtime_pack,
    resolve_spec: Callable[[str], Path],
    parse_frontmatter: Callable[[Path], dict[str, object]],
) -> list[str]:
    findings: list[str] = []

    try:
        project_runtimes = set(available_project_runtime_names())
    except Exception as exc:
        findings.append(f"No pude cargar el catalogo de runtimes de proyecto: {exc}")
        project_runtimes = set()
    try:
        service_runtimes = set(available_service_runtime_names())
    except Exception as exc:
        findings.append(f"No pude cargar el catalogo de runtimes de servicio: {exc}")
        service_runtimes = set()
    try:
        capabilities = set(available_capability_names())
    except Exception as exc:
        findings.append(f"No pude cargar el catalogo de capabilities: {exc}")
        capabilities = set()

    for runtime in analysis.get("required_runtimes", []):
        if runtime not in project_runtimes:
            findings.append(f"El runtime requerido `{runtime}` no esta instalado como runtime de proyecto.")
    for runtime in analysis.get("required_services", []):
        if runtime not in service_runtimes:
            findings.append(f"El servicio requerido `{runtime}` no esta instalado como runtime de servicio.")
    for capability in analysis.get("required_capabilities", []):
        if capability not in capabilities:
            findings.append(f"La capability requerida `{capability}` no esta instalada o esta deshabilitada.")

    declared_services: set[str] = set()
    declared_service_runtimes: dict[str, str] = {}
    for index, service in enumerate(analysis.get("stack_services", []), start=1):
        if not isinstance(service, dict):
            continue
        name = str(service.get("name", "")).strip()
        runtime = str(service.get("runtime", "")).strip()
        if not name:
            findings.append(f"`stack_services` item #{index} debe declarar `name`.")
        if not runtime:
            findings.append(f"`stack_services` item #{index} debe declarar `runtime`.")
        if name in declared_services:
            findings.append(f"`stack_services` contiene un nombre duplicado: `{name}`.")
        if runtime and runtime not in service_runtimes:
            findings.append(f"`stack_services` declara un runtime no instalado: `{runtime}`.")
        findings.extend(_mapping_findings(service.get("env"), f"stack_services[{name or index}].env"))
        findings.extend(_string_or_int_list_findings(service.get("ports"), f"stack_services[{name or index}].ports"))
        findings.extend(_string_list_findings(service.get("volumes"), f"stack_services[{name or index}].volumes"))
        if name:
            declared_services.add(name)
            declared_service_runtimes[name] = runtime

    declared_projects: set[str] = set()
    for index, project in enumerate(analysis.get("stack_projects", []), start=1):
        if not isinstance(project, dict):
            continue
        name = str(project.get("name", "")).strip()
        runtime = str(project.get("runtime", "")).strip()
        path = str(project.get("path", name)).strip() if (project.get("path") is not None or name) else ""
        if not name:
            findings.append(f"`stack_projects` item #{index} debe declarar `name`.")
        if not runtime:
            findings.append(f"`stack_projects` item #{index} debe declarar `runtime`.")
        if name in declared_projects:
            findings.append(f"`stack_projects` contiene un nombre duplicado: `{name}`.")
        if runtime and runtime not in project_runtimes:
            findings.append(f"`stack_projects` declara un runtime no instalado: `{runtime}`.")
        if project.get("port") is not None and not isinstance(project.get("port"), int):
            findings.append(f"`stack_projects` item `{name or index}` debe declarar `port` como entero.")
        if isinstance(project.get("port"), int) and int(project["port"]) <= 0:
            findings.append(f"`stack_projects` item `{name or index}` debe usar un `port` positivo.")
        if path and Path(path).is_absolute():
            findings.append(f"`stack_projects` item `{name or index}` no puede usar un `path` absoluto.")
        compose_service = project.get("compose_service")
        if compose_service is not None and (not isinstance(compose_service, str) or not compose_service.strip()):
            findings.append(
                f"`stack_projects` item `{name or index}` debe declarar `compose_service` como string no vacio."
            )
        repo_code = project.get("repo_code")
        if repo_code is not None and (not isinstance(repo_code, str) or not repo_code.strip()):
            findings.append(
                f"`stack_projects` item `{name or index}` debe declarar `repo_code` como string no vacio."
            )
        findings.extend(_string_list_findings(project.get("aliases"), f"stack_projects[{name or index}].aliases"))
        findings.extend(_mapping_findings(project.get("env"), f"stack_projects[{name or index}].env"))
        findings.extend(
            _string_list_findings(project.get("default_targets"), f"stack_projects[{name or index}].default_targets")
        )
        findings.extend(
            _string_list_findings(project.get("target_roots"), f"stack_projects[{name or index}].target_roots")
        )
        use_existing_dir = project.get("use_existing_dir")
        if use_existing_dir is not None and not isinstance(use_existing_dir, bool):
            findings.append(
                f"`stack_projects` item `{name or index}` debe declarar `use_existing_dir` como booleano."
            )

        project_capabilities = project.get("capabilities", [])
        if project_capabilities is not None and not isinstance(project_capabilities, list):
            findings.append(
                f"`stack_projects` item `{name or index}` debe declarar `capabilities` como lista."
            )
        elif isinstance(project_capabilities, list):
            for capability in project_capabilities:
                candidate = str(capability).strip()
                if candidate and candidate not in capabilities:
                    findings.append(
                        f"`stack_projects` item `{name or index}` requiere la capability no instalada `{candidate}`."
                    )

        service_bindings = project.get("service_bindings", [])
        runtime_pack: dict[str, Any] | None = None
        if runtime and runtime in project_runtimes and name and path and not Path(path).is_absolute():
            try:
                candidate_pack = resolve_runtime_pack(runtime, name, path)
                if isinstance(candidate_pack, dict):
                    runtime_pack = candidate_pack
            except Exception as exc:
                findings.append(
                    f"No pude resolver el runtime pack `{runtime}` para `stack_projects[{name or index}]`: {exc}"
                )
        if service_bindings is not None and not isinstance(service_bindings, list):
            findings.append(
                f"`stack_projects` item `{name or index}` debe declarar `service_bindings` como lista."
            )
        elif isinstance(service_bindings, list):
            for service_name in service_bindings:
                candidate = str(service_name).strip()
                if candidate and candidate not in declared_services:
                    findings.append(
                        f"`stack_projects` item `{name or index}` referencia un servicio no declarado: `{candidate}`."
                    )
                    continue
                if candidate and runtime_pack is not None:
                    bindings = runtime_pack.get("bindings", {})
                    service_runtime = declared_service_runtimes.get(candidate, "")
                    if (
                        isinstance(bindings, dict)
                        and service_runtime
                        and service_runtime not in bindings
                        and candidate not in bindings
                    ):
                        findings.append(
                            f"`stack_projects` item `{name or index}` no tiene binding declarado entre "
                            f"`{runtime}` y `{service_runtime}`."
                        )

        if name:
            declared_projects.add(name)

    for capability in analysis.get("stack_capabilities", []):
        if capability not in capabilities:
            findings.append(f"`stack_capabilities` declara una capability no instalada: `{capability}`.")

    current_spec_path = analysis.get("spec_path")
    current_spec = current_spec_path.resolve() if isinstance(current_spec_path, Path) else None
    resolved_dependencies: list[Path] = []
    for dependency in analysis.get("depends_on", []):
        try:
            dependency_path = resolve_spec(dependency)
        except SystemExit:
            findings.append(f"`depends_on` referencia una spec inexistente: `{dependency}`.")
            continue
        if current_spec and dependency_path.resolve() == current_spec:
            findings.append("`depends_on` no puede referenciar la misma spec.")
            continue
        try:
            dependency_frontmatter = parse_frontmatter(dependency_path)
        except ValueError as exc:
            findings.append(f"La spec dependiente `{dependency}` tiene frontmatter invalido: {exc}")
            continue
        dependency_status = str(dependency_frontmatter.get("status", "")).strip() or "missing"
        if not frontmatter_status_allows_dependencies(dependency_status):
            findings.append(
                f"`depends_on` requiere specs listas (`approved` o `released`): `{dependency}` esta en `{dependency_status}`."
            )
        resolved_dependencies.append(dependency_path.resolve())

    if current_spec is not None:
        try:
            relative_current = current_spec.relative_to(config.specs_root.resolve())
        except ValueError:
            relative_current = None

        if relative_current is not None and relative_current.parts and relative_current.parts[0] == "features":
            foundation_specs = sorted((config.specs_root / "000-foundation").rglob("*.spec.md"))
            domain_specs = sorted((config.specs_root / "domains").rglob("*.spec.md"))

            def dependency_bucket(path: Path) -> str:
                try:
                    rel = path.relative_to(config.specs_root.resolve())
                except ValueError:
                    return ""
                if not rel.parts:
                    return ""
                return rel.parts[0]

            dependency_buckets = {dependency_bucket(path) for path in resolved_dependencies}

            raw_text = str(analysis.get("text", "")).lower()
            explicit_no_domain_exception = bool(
                re.search(r"no aplica\s+ningun?\s+domain\s+porque", raw_text)
                or re.search(r"no aplica\s+domain\s+porque", raw_text)
            )

            if foundation_specs and "000-foundation" not in dependency_buckets:
                findings.append(
                    "Feature specs deben referenciar al menos una spec de `specs/000-foundation/**` en `depends_on`."
                )
            if domain_specs and "domains" not in dependency_buckets and not explicit_no_domain_exception:
                findings.append(
                    "Feature specs deben referenciar al menos una spec de `specs/domains/**` en `depends_on`, "
                    "o justificar explicitamente la excepcion en la seccion `Domains Aplicables`."
                )

    return findings


def resolve_spec(identifier: str, *, config: SpecConfig, slugify: Callable[[str], str]) -> Path:
    raw = Path(identifier)
    if raw.exists():
        return raw.resolve()

    slug = slugify(raw.stem.replace(".spec", ""))
    candidates = list(config.specs_root.rglob(f"{slug}.spec.md"))
    if not candidates:
        raise SystemExit(f"No encontre una spec para '{identifier}'.")
    return candidates[0]


def spec_slug(spec_path: Path) -> str:
    return spec_path.name.replace(".spec.md", "")


def _path_is_under(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def render_targets(config: SpecConfig, repos: list[str]) -> str:
    lines: list[str] = []
    for repo in repos:
        for target in config.default_targets[repo]:
            lines.append(f"  - {target}")
    return "\n".join(lines)


def select_spec_paths(
    *,
    config: SpecConfig,
    resolve_spec: Callable[[str], Path],
    git_diff_name_only: Callable[[Path, Optional[str], Optional[str]], tuple[list[str], Optional[str]]],
    spec_identifier: Optional[str] = None,
    all_specs: bool = False,
    changed: bool = False,
    base: Optional[str] = None,
    head: Optional[str] = None,
) -> list[Path]:
    if spec_identifier:
        return [resolve_spec(spec_identifier)]

    if all_specs:
        return all_spec_paths(config)

    if changed:
        changed_files, error = git_diff_name_only(config.root, base=base, head=head)
        if error:
            raise SystemExit(f"No pude resolver specs cambiadas: {error}")
        spec_paths = [
            candidate.resolve()
            for relative_path in changed_files
            for candidate in [config.root / relative_path]
            if relative_path.endswith(".spec.md")
            and candidate.exists()
            and _path_is_under(config.specs_root, candidate)
        ]
        return sorted(dict.fromkeys(spec_paths))

    return all_spec_paths(config)
