from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def require_dirs(directories: list[Path]) -> None:
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def relpath(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def state_path(state_root: Path, slug: str) -> Path:
    return state_root / f"{slug}.json"


def read_state(state_root: Path, slug: str) -> dict[str, object]:
    path = state_path(state_root, slug)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(state_root: Path, slug: str, payload: dict[str, object], *, now: str | None = None) -> None:
    payload["updated_at"] = now or utc_now()
    state_path(state_root, slug).write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
