"""Lectura de `workspace.config.json` -> clave opcional `gateway` (T16/T17/T18)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_gateway_block(workspace_root: Path) -> dict[str, Any]:
    path = workspace_root / "workspace.config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    gw = data.get("gateway")
    return gw if isinstance(gw, dict) else {}
