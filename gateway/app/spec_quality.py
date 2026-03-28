"""Lint mínimo para textos de specs inbound (T18)."""
from __future__ import annotations

import re
from typing import Any


def lint_inbound_spec_payload(payload: dict[str, Any]) -> list[str]:
    """Devuelve hallazgos no bloqueantes por defecto."""
    issues: list[str] = []
    title = str(payload.get("title", "") or "")
    desc = str(payload.get("description", "") or "")
    if "\t" in title:
        issues.append("title: contiene tabuladores; preferir espacios")
    if re.search(r"[ \t]+$", title, re.MULTILINE):
        issues.append("title: trailing whitespace")
    if len(title) > 200:
        issues.append("title: longitud inusual (>200 caracteres)")
    # Ortografía común (es)
    blob = f"{title}\n{desc}".lower()
    for wrong in ("recieve", "seperate", "acheive"):
        if wrong in blob:
            issues.append(f"posible typo: '{wrong}'")
    return issues
