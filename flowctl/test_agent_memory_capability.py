from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from flowctl.specs import analyze_spec, build_spec_config
from flowctl.stack_design import available_capability_names, resolve_capability_pack


class AgentMemoryCapabilityTests(unittest.TestCase):
    @staticmethod
    def _root() -> Path:
        return Path(__file__).resolve().parents[1]

    def test_agent_memory_engram_capability_is_registered_and_resolvable(self) -> None:
        root = self._root()

        names = available_capability_names(root)
        pack, path = resolve_capability_pack(root, "agent-memory-engram")

        self.assertIn("agent-memory-engram", names)
        self.assertEqual(root / "capabilities" / "agent-memory-engram.capability.json", path)
        self.assertEqual("Agent Memory With Engram", pack["title"])
        self.assertIn(".agents/skills", pack["target_roots"])

    def test_agent_memory_manifest_entry_is_enabled_and_points_to_pack(self) -> None:
        root = self._root()
        manifest = json.loads((root / "workspace.capabilities.json").read_text(encoding="utf-8"))
        entry = manifest["capabilities"]["agent-memory-engram"]

        self.assertTrue(entry["enabled"])
        self.assertEqual("capabilities/agent-memory-engram.capability.json", entry["source"])

    def test_agent_memory_capability_declares_consultive_boundary(self) -> None:
        root = self._root()
        pack = json.loads((root / "capabilities" / "agent-memory-engram.capability.json").read_text(encoding="utf-8"))
        foundation_text = "\n".join(pack["foundation_specs"][0]["body"]).lower()

        self.assertIn("consultivo", foundation_text)
        self.assertIn("nunca guardar secretos", foundation_text)
        self.assertIn("specs/**", foundation_text)
        self.assertIn(".flow/reports/**", foundation_text)
        self.assertIn("ausencia de engram no debe bloquear", foundation_text)

    def test_agent_memory_skill_declares_safe_usage_rules(self) -> None:
        root = self._root()
        skill = (root / ".agents" / "skills" / "softos-agent-memory-playbook" / "SKILL.md").read_text(encoding="utf-8")
        lower = skill.lower()

        self.assertIn("name: softos-agent-memory-playbook", skill)
        self.assertIn("source of truth boundary", lower)
        self.assertIn("secrets", lower)
        self.assertIn("engram is unavailable", lower)
        self.assertIn("must not fail `flow` commands", lower)

    def test_agent_memory_is_project_scoped_in_devcontainer(self) -> None:
        root = self._root()
        dockerfile = (root / ".devcontainer" / "Dockerfile").read_text(encoding="utf-8")
        compose = (root / ".devcontainer" / "docker-compose.yml").read_text(encoding="utf-8")
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        workspace = json.loads((root / "workspace.config.json").read_text(encoding="utf-8"))

        self.assertIn("Gentleman-Programming/engram/releases/latest", dockerfile)
        self.assertIn("/usr/local/bin/engram", dockerfile)
        self.assertIn("ENGRAM_PROJECT", compose)
        self.assertIn("ENGRAM_DATA_DIR: /workspace/.flow/memory/engram", compose)
        self.assertIn(".flow/memory/*", gitignore)
        self.assertEqual("engram", workspace["memory"]["agent"]["provider"])
        self.assertEqual(".flow/memory/engram", workspace["memory"]["agent"]["data_dir"])

    def test_agent_memory_spec_targets_capability_manifest_and_skill(self) -> None:
        root = self._root()
        config = build_spec_config(
            root=root,
            specs_root=root / "specs",
            feature_specs=root / "specs" / "features",
            root_repo="sdd-workspace-boilerplate",
            default_targets={"sdd-workspace-boilerplate": ["../../specs/**/*.spec.md"]},
            repo_prefixes={"sdd-workspace-boilerplate": "../../"},
            target_roots={
                "sdd-workspace-boilerplate": {
                    ".agents",
                    "capabilities",
                    "docs",
                    "README.md",
                    "specs",
                    "workspace.capabilities.json",
                }
            },
            test_required_roots={"sdd-workspace-boilerplate": set()},
            test_hints={"sdd-workspace-boilerplate": ""},
            required_frontmatter_fields=("name", "description", "status", "targets"),
            test_ref_re=re.compile(r"\[@test\]\s+([^\s`]+)"),
            todo_re=re.compile(r"\bTODO\b"),
        )
        spec_path = root / "specs" / "features" / "softos-agent-memory-with-engram.spec.md"
        analysis = analyze_spec(spec_path, config=config)
        targets = set(analysis["targets"])

        self.assertIn("agent-memory-engram", analysis["required_capabilities"])
        self.assertIn("../../capabilities/agent-memory-engram.capability.json", targets)
        self.assertIn("../../workspace.capabilities.json", targets)
        self.assertIn("../../.agents/skills/softos-agent-memory-playbook/SKILL.md", targets)
        self.assertTrue(
            any(
                item.get("command") == "python3 ./flow ci spec specs/features/softos-agent-memory-with-engram.spec.md"
                for item in analysis["verification_matrix"]
                if isinstance(item, dict)
            )
        )


if __name__ == "__main__":
    unittest.main()
