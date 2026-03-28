"""Clave semántica para deduplicación de intake (T20; dedupe en TaskStore.enqueue)."""
from __future__ import annotations

import json
from typing import Any


def semantic_intake_key(payload: dict[str, Any]) -> str:
    """Clave estable para correlación (mismo payload JSON canónico)."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)
