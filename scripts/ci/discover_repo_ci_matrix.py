#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flowctl.repo_ci_matrix import build_repo_ci_matrices, load_runtime_pack_map


def main() -> int:
    root = Path(".").resolve()
    workspace_config = json.loads((root / "workspace.config.json").read_text(encoding="utf-8"))
    runtime_packs = load_runtime_pack_map(root)
    payload = build_repo_ci_matrices(workspace_config, runtime_packs)
    print("generic_matrix=" + json.dumps(payload["generic"], separators=(",", ":")))
    print("delegated_matrix=" + json.dumps(payload["delegated"], separators=(",", ":")))
    print("has_generic=" + ("true" if payload["has_generic"] else "false"))
    print("has_delegated=" + ("true" if payload["has_delegated"] else "false"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
