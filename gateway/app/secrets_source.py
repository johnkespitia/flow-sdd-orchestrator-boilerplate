from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SecretSource(Protocol):
    def get(self, key: str) -> str | None: ...


@dataclass(frozen=True)
class EnvSecretSource:
    def get(self, key: str) -> str | None:
        value = os.getenv(key)
        return value if value else None


@dataclass(frozen=True)
class JsonFileSecretSource:
    path: Path

    def get(self, key: str) -> str | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        value = payload.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None


def build_secret_source(*, workspace_root: Path) -> SecretSource:
    """
    Fuente central configurable:
    - `SOFTOS_GATEWAY_SECRETS_FILE` apunta a un JSON con secrets (preferido para despliegue central).
    - Fallback: variables de entorno.
    """
    file_path = os.getenv("SOFTOS_GATEWAY_SECRETS_FILE", "").strip()
    if not file_path:
        # Default recomendado: un artefacto materializado por un secret manager / pipeline.
        file_path = str(workspace_root / "gateway" / "data" / "secrets.json")
    return _ChainedSecretSource(
        sources=[
            JsonFileSecretSource(Path(file_path).resolve()),
            EnvSecretSource(),
        ]
    )


@dataclass(frozen=True)
class _ChainedSecretSource:
    sources: list[SecretSource]

    def get(self, key: str) -> str | None:
        for source in self.sources:
            value = source.get(key)
            if value:
                return value
        return None

