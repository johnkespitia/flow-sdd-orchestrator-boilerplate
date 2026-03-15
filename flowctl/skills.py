from __future__ import annotations

from pathlib import Path


def normalize_skill_provider(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "tessl": "tessl",
        "skills-sh": "skills-sh",
        "skills.sh": "skills-sh",
        "skills_sh": "skills-sh",
        "skills": "skills-sh",
    }
    if normalized not in aliases:
        allowed = ", ".join(sorted({"tessl", "skills-sh"}))
        raise ValueError(f"Proveedor de skills invalido `{value}`. Usa uno de: {allowed}.")
    return aliases[normalized]


def local_skill_source(root: Path, source: str) -> Path | None:
    raw = source.strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        raise ValueError("Las rutas de skills deben ser relativas al root del workspace.")
    resolved = (root / candidate).resolve()
    if resolved.exists():
        return resolved
    return None


def normalize_skill_entry(root: Path, raw: object, index: int) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError(f"La entrada #{index} debe ser un objeto.")

    name = str(raw.get("name", "")).strip()
    if not name:
        raise ValueError(f"La entrada #{index} debe declarar `name`.")

    provider = normalize_skill_provider(str(raw.get("provider", "")).strip())
    default_kind = "package" if provider == "skills-sh" else "tile"
    kind = str(raw.get("kind", default_kind)).strip().lower() or default_kind
    if provider == "tessl" and kind not in {"tile", "skill"}:
        raise ValueError(f"`{name}` usa provider `tessl`; `kind` debe ser `tile` o `skill`.")
    if provider == "skills-sh" and kind != "package":
        raise ValueError(f"`{name}` usa provider `skills-sh`; `kind` debe ser `package`.")

    source = str(raw.get("source", "")).strip()
    if not source:
        raise ValueError(f"`{name}` debe declarar `source`.")

    args_raw = raw.get("args", [])
    if args_raw is None:
        args_raw = []
    if not isinstance(args_raw, list) or not all(isinstance(item, str) for item in args_raw):
        raise ValueError(f"`{name}` debe declarar `args` como lista de strings si existe.")

    requires_raw = raw.get("requires", [])
    if requires_raw is None:
        requires_raw = []
    if not isinstance(requires_raw, list) or not all(isinstance(item, str) and item.strip() for item in requires_raw):
        raise ValueError(f"`{name}` debe declarar `requires` como lista de strings no vacios si existe.")

    local_source_path = local_skill_source(root, source)
    return {
        "name": name,
        "provider": provider,
        "kind": kind,
        "source": source,
        "enabled": bool(raw.get("enabled", True)),
        "required": bool(raw.get("required", False)),
        "sync": bool(raw.get("sync", True)),
        "args": list(args_raw),
        "requires": [item.strip() for item in requires_raw],
        "notes": str(raw.get("notes", "")).strip(),
        "local_source_path": local_source_path,
    }


def skills_entries(root: Path, payload: dict[str, object]) -> tuple[list[dict[str, object]], list[str]]:
    raw_entries = payload.get("entries", [])
    if not isinstance(raw_entries, list):
        return [], ["`entries` debe ser una lista en workspace.skills.json."]

    entries: list[dict[str, object]] = []
    errors: list[str] = []
    for index, raw in enumerate(raw_entries, start=1):
        try:
            entries.append(normalize_skill_entry(root, raw, index))
        except ValueError as exc:
            errors.append(str(exc))
    return entries, errors


def serialize_skill_entry(entry: dict[str, object], relativize) -> dict[str, object]:
    payload = {
        "name": entry["name"],
        "provider": entry["provider"],
        "kind": entry["kind"],
        "source": entry["source"],
        "enabled": entry["enabled"],
        "required": entry["required"],
        "sync": entry["sync"],
        "args": entry["args"],
        "requires": entry["requires"],
        "notes": entry["notes"],
    }
    local_source_path = entry.get("local_source_path")
    if isinstance(local_source_path, Path):
        payload["local_source_path"] = relativize(local_source_path)
    else:
        payload["local_source_path"] = None
    return payload
