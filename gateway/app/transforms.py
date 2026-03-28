"""Reglas de transformación declarativas por fuente (T16)."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .gateway_config import load_gateway_block


def apply_source_transforms(source: str, payload: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    gw = load_gateway_block(workspace_root)
    rules = gw.get("transforms", {})
    if not isinstance(rules, dict):
        return payload
    chain = rules.get(source) or rules.get(str(source).lower())
    if not isinstance(chain, list) or not chain:
        return payload
    out = copy.deepcopy(payload)
    for rule in chain:
        if not isinstance(rule, dict):
            continue
        op = str(rule.get("op", "")).strip().lower()
        field = str(rule.get("field", "")).strip()
        if not field or field not in out:
            continue
        if op == "strip_prefix":
            prefix = str(rule.get("prefix", ""))
            val = out[field]
            if isinstance(val, str) and val.startswith(prefix):
                out[field] = val[len(prefix) :].lstrip()
        elif op == "strip_suffix":
            suffix = str(rule.get("suffix", ""))
            val = out[field]
            if isinstance(val, str) and val.endswith(suffix):
                out[field] = val[: -len(suffix)].rstrip()
        elif op == "set_default":
            if out[field] in (None, "", []):
                out[field] = rule.get("value")
    return out
