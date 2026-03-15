from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Optional


CONTRACT_BLOCK_RE = re.compile(r"```json\s+contract[^\n]*\n(.*?)```", flags=re.DOTALL)
TYPE_TOKEN_PATTERNS = {
    "string": re.compile(r"\b(string|text|varchar|uuid|email|datetime|date)\b", flags=re.IGNORECASE),
    "integer": re.compile(r"\b(integer|int|bigint)\b", flags=re.IGNORECASE),
    "number": re.compile(r"\b(number|numeric|float|double|decimal)\b", flags=re.IGNORECASE),
    "boolean": re.compile(r"\b(boolean|bool)\b", flags=re.IGNORECASE),
    "array": re.compile(r"\b(array|list)\b", flags=re.IGNORECASE),
    "object": re.compile(r"\b(object|map|dict)\b", flags=re.IGNORECASE),
}


def extract_contract_declarations(text: str) -> tuple[list[dict[str, object]], list[str]]:
    declarations: list[dict[str, object]] = []
    errors: list[str] = []
    for index, match in enumerate(CONTRACT_BLOCK_RE.finditer(text), start=1):
        raw_payload = match.group(1).strip()
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            errors.append(f"Bloque contract #{index} no contiene JSON valido: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"Bloque contract #{index} debe ser un objeto JSON.")
            continue
        name = str(payload.get("name", "")).strip()
        contract_type = str(payload.get("type", "")).strip()
        if not name or not contract_type:
            errors.append(f"Bloque contract #{index} debe declarar `name` y `type`.")
            continue
        declarations.append(payload)
    return declarations, errors


def validate_contract_declaration(
    declaration: dict[str, object],
    valid_repos: set[str],
) -> tuple[Optional[dict[str, object]], Optional[str]]:
    repo = str(declaration.get("repo", "")).strip()
    contract_type = str(declaration.get("type", "")).strip().lower()
    name = str(declaration.get("name", "")).strip()
    if repo not in valid_repos:
        return None, f"Contract `{name}` usa repo inexistente `{repo}`."
    if contract_type not in {"openapi", "asyncapi", "json-schema", "ui-flow"}:
        return None, f"Contract `{name}` usa type no soportado `{contract_type}`."

    patterns_raw = declaration.get("match", declaration.get("matches", []))
    if isinstance(patterns_raw, str):
        patterns = [patterns_raw]
    elif isinstance(patterns_raw, list):
        patterns = [str(item) for item in patterns_raw]
    else:
        patterns = []

    contains_raw = declaration.get("contains", [])
    if isinstance(contains_raw, str):
        contains = [contains_raw]
    elif isinstance(contains_raw, list):
        contains = [str(item) for item in contains_raw]
    else:
        contains = []

    normalized = dict(declaration)
    normalized["name"] = name
    normalized["type"] = contract_type
    normalized["repo"] = repo
    normalized["match"] = patterns
    normalized["contains"] = contains
    return normalized, None


def contract_match_files(repo_path: Path, patterns: list[str]) -> list[Path]:
    matched: list[Path] = []
    for pattern in patterns:
        candidate = repo_path / pattern
        if candidate.exists() and candidate.is_file():
            matched.append(candidate)
            continue
        matched.extend(path for path in repo_path.glob(pattern) if path.is_file())
    unique: list[Path] = []
    seen: set[str] = set()
    for path in matched:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def render_contract_artifacts(
    slug: str,
    declarations: list[dict[str, object]],
    output_root: Path,
    *,
    generated_at: str,
    relativize: Callable[[Path], str],
    write_json: Callable[[Path, dict[str, object]], None],
) -> list[dict[str, object]]:
    output_dir = output_root / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, object]] = []
    openapi_paths: dict[str, object] = {}
    asyncapi_channels: dict[str, object] = {}

    for declaration in declarations:
        contract_type = str(declaration["type"])
        name = slugify(str(declaration["name"]))
        if contract_type == "openapi":
            method = str(declaration.get("method", "get")).lower()
            path = str(declaration.get("path", f"/{name}"))
            response_schema = declaration.get("response_schema", {"type": "object"})
            openapi_paths.setdefault(path, {})[method] = {
                "summary": declaration["name"],
                "responses": {
                    "200": {
                        "description": "Generated from spec",
                        "content": {
                            "application/json": {
                                "schema": response_schema
                            }
                        },
                    }
                },
            }
            continue

        if contract_type == "asyncapi":
            channel = str(declaration.get("channel", name))
            asyncapi_channels[channel] = {
                "description": declaration["name"],
                "publish": {
                    "message": {
                        "payload": declaration.get("payload_schema", {"type": "object"})
                    }
                },
            }
            continue

        artifact_path = output_dir / f"{name}.json"
        write_json(artifact_path, declaration)
        artifacts.append({"name": declaration["name"], "type": contract_type, "path": relativize(artifact_path)})

    if openapi_paths:
        openapi_path = output_dir / "openapi.json"
        write_json(
            openapi_path,
            {
                "openapi": "3.1.0",
                "info": {"title": slug, "version": "generated"},
                "paths": openapi_paths,
            },
        )
        artifacts.append({"name": "openapi", "type": "openapi", "path": relativize(openapi_path)})

    if asyncapi_channels:
        asyncapi_path = output_dir / "asyncapi.json"
        write_json(
            asyncapi_path,
            {
                "asyncapi": "2.6.0",
                "info": {"title": slug, "version": "generated"},
                "channels": asyncapi_channels,
            },
        )
        artifacts.append({"name": "asyncapi", "type": "asyncapi", "path": relativize(asyncapi_path)})

    manifest_path = output_dir / "manifest.json"
    write_json(manifest_path, {"generated_at": generated_at, "feature": slug, "artifacts": artifacts})
    artifacts.append({"name": "manifest", "type": "manifest", "path": relativize(manifest_path)})
    return artifacts


def schema_from_contract_declaration(declaration: dict[str, object]) -> dict[str, object]:
    contract_type = str(declaration.get("type", "")).strip().lower()
    if contract_type == "json-schema":
        schema = declaration.get("schema", {})
    elif contract_type == "openapi":
        schema = declaration.get("response_schema", {})
    elif contract_type == "asyncapi":
        schema = declaration.get("payload_schema", {})
    else:
        schema = {}
    return schema if isinstance(schema, dict) else {}


def normalize_schema_type(value: object) -> Optional[str]:
    if isinstance(value, list):
        for item in value:
            normalized = normalize_schema_type(item)
            if normalized and normalized != "null":
                return normalized
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    aliases = {
        "int": "integer",
        "float": "number",
        "double": "number",
        "decimal": "number",
        "bool": "boolean",
    }
    return aliases.get(normalized, normalized)


def flatten_schema_properties(schema: dict[str, object], prefix: str = "") -> list[dict[str, object]]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []

    required_raw = schema.get("required", [])
    required = {str(item) for item in required_raw} if isinstance(required_raw, list) else set()
    flattened: list[dict[str, object]] = []
    for key, child in properties.items():
        if not isinstance(child, dict):
            continue
        field_name = f"{prefix}.{key}" if prefix else str(key)
        field_type = normalize_schema_type(child.get("type"))
        flattened.append(
            {
                "name": field_name,
                "leaf_name": str(key),
                "type": field_type,
                "required": str(key) in required,
            }
        )
        if field_type == "object":
            flattened.extend(flatten_schema_properties(child, prefix=field_name))
    return flattened


def snake_to_camel(value: str) -> str:
    parts = value.split("_")
    if not parts:
        return value
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def contract_field_aliases(field_name: str) -> set[str]:
    leaf = field_name.split(".")[-1]
    aliases = {field_name, leaf, snake_to_camel(leaf), leaf.replace("_", "-")}
    return {alias for alias in aliases if alias}


def detect_types_in_snippet(text: str) -> set[str]:
    detected: set[str] = set()
    for type_name, pattern in TYPE_TOKEN_PATTERNS.items():
        if pattern.search(text):
            detected.add(type_name)
    return detected


def contract_type_compatible(expected: Optional[str], actual: str) -> bool:
    if expected is None:
        return True
    if expected == actual:
        return True
    if expected == "number" and actual in {"number", "integer"}:
        return True
    return False


def inspect_contract_field_in_files(
    field_name: str,
    matched_files: list[Path],
    *,
    read_text: Callable[[Path], str],
) -> tuple[bool, set[str]]:
    aliases = {alias.lower() for alias in contract_field_aliases(field_name)}
    present = False
    detected_types: set[str] = set()

    for path in matched_files:
        lines = read_text(path).splitlines()
        for index, line in enumerate(lines):
            normalized = line.lower()
            if not any(alias in normalized for alias in aliases):
                continue
            present = True
            snippet = "\n".join(lines[max(0, index - 1) : min(len(lines), index + 2)])
            detected_types.update(detect_types_in_snippet(snippet))
    return present, detected_types


def verify_contract_declaration(
    declaration: dict[str, object],
    matched_files: list[Path],
    *,
    read_text: Callable[[Path], str],
) -> list[str]:
    findings: list[str] = []
    schema = schema_from_contract_declaration(declaration)
    properties = flatten_schema_properties(schema)
    if not properties:
        return findings

    for property_payload in properties:
        field_name = str(property_payload["name"])
        expected_type = property_payload.get("type")
        present, detected_types = inspect_contract_field_in_files(field_name, matched_files, read_text=read_text)
        if not present:
            findings.append(f"Contract `{declaration['name']}` no encontro el campo `{field_name}` en la implementacion.")
            continue
        if expected_type and detected_types and not any(
            contract_type_compatible(str(expected_type), detected_type) for detected_type in detected_types
        ):
            findings.append(
                f"Contract `{declaration['name']}` declara `{field_name}` como `{expected_type}` "
                f"pero la implementacion sugiere `{', '.join(sorted(detected_types))}`."
            )
    return findings


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
