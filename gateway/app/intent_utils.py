"""Utilidades compartidas entre parseo de intents y construcción de comandos `flow` (evita ciclos de import)."""
from __future__ import annotations

import re


class IntentError(ValueError):
    pass


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-")


def _normalize_description(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    normalized = "\n".join(line for line in lines if line)
    return normalized.strip()


def _normalize_acceptance_criteria(value: object) -> list[str]:
    if value is None:
        return []
    items: list[str] = []
    if isinstance(value, list):
        candidates = value
    else:
        candidates = [value]
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).replace("\r\n", "\n").replace("\r", "\n")
        for line in text.split("\n"):
            normalized = line.strip().lstrip("-* ").strip()
            if normalized:
                items.append(normalized)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
