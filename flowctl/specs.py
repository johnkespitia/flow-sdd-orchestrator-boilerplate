from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


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


def all_spec_paths(config: SpecConfig) -> list[Path]:
    return sorted(config.specs_root.rglob("*.spec.md"))


def parse_frontmatter(spec_path: Path) -> dict[str, object]:
    text = spec_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break

    if end is None:
        return {}

    data: dict[str, object] = {}
    current_key: Optional[str] = None

    for raw_line in lines[1:end]:
        line = raw_line.rstrip()
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()
            if value:
                data[key] = value
                current_key = None
            else:
                data[key] = []
                current_key = key
            continue

        if current_key and line.strip().startswith("- "):
            current = data.setdefault(current_key, [])
            if isinstance(current, list):
                current.append(line.strip()[2:].strip())

    return data


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

    top_level = Path(relative).parts[0]
    if top_level not in config.target_roots[repo]:
        allowed = ", ".join(sorted(config.target_roots[repo]))
        raise ValueError(
            f"Ruta invalida '{raw_path}': '{top_level}' no es un root permitido para {repo}. "
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
        if Path(relative).parts[0] in required_roots:
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


def analyze_spec(spec_path: Path, *, config: SpecConfig) -> dict[str, object]:
    text = spec_path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(spec_path)
    targets = list(frontmatter.get("targets", []))
    target_index, target_errors = collect_routed_paths(targets, config=config)
    test_refs = extract_test_references(text, config=config)
    backticked_test_refs = extract_backticked_test_references(text)
    test_index, test_errors = collect_routed_paths(test_refs, config=config)
    missing_frontmatter = [field for field in config.required_frontmatter_fields if not frontmatter.get(field)]

    return {
        "text": text,
        "frontmatter": frontmatter,
        "targets": targets,
        "target_index": target_index,
        "target_errors": target_errors,
        "test_refs": test_refs,
        "backticked_test_refs": backticked_test_refs,
        "test_index": test_index,
        "test_errors": test_errors,
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
) -> dict[str, object]:
    analysis = analyze_spec(spec_path, config=config)
    blockers: list[str] = []
    frontmatter = analysis["frontmatter"]

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
    value = frontmatter.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


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
            (config.root / relative_path).resolve()
            for relative_path in changed_files
            if relative_path.endswith(".spec.md") and (config.root / relative_path).exists()
        ]
        return sorted(dict.fromkeys(spec_paths))

    return all_spec_paths(config)
