from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flowctl.agent_executors import parse_agents_registry
from flowctl.agent_resources import (
    AVAILABILITY_STATES,
    AgentResourceError,
    default_availability_for_resource,
    filter_resources_for_selection,
    load_resource_registry,
    normalize_availability,
    order_resource_candidates,
    parse_resource_registry,
    resolve_free_model,
    resolve_go_model,
)


def _default_resources() -> dict[str, object]:
    return {
        "opencode-local": {
            "executor": "opencode-local",
            "capabilities": ["tool_calling", "write", "local_execution"],
            "capacity": 1,
            "cost_tier": "local",
            "selection_priority": 10,
            "model_resolution": "worker_profile",
            "data_sensitivity": "local-only",
        },
        "opencode-free": {
            "executor": "opencode",
            "capabilities": ["tool_calling", "write", "cloud_execution"],
            "capacity": 1,
            "cost_tier": "cloud/free",
            "selection_priority": 20,
            "model_resolution": "dynamic_free",
            "data_sensitivity": "cloud-eligible",
            "candidate_tie_break": "lexical",
        },
        "opencode-go": {
            "executor": "opencode",
            "capabilities": ["tool_calling", "write", "cloud_execution", "architecture"],
            "capacity": 1,
            "cost_tier": "cloud/paid-low",
            "selection_priority": 30,
            "model_resolution": "dynamic_go",
            "data_sensitivity": "cloud-eligible",
            "candidate_tie_break": "lexical",
        },
    }


def _base_agents() -> dict[str, object]:
    return {
        "schema_version": 1,
        "executors": {
            "codex": {"adapter": "codex", "executable": "codex", "argv": []},
            "cursor": {"adapter": "cursor", "executable": "agent", "argv": []},
            "opencode": {"adapter": "opencode", "executable": "opencode", "argv": []},
            "opencode-local": {
                "adapter": "opencode",
                "executable": "opencode-softos",
                "argv": [],
            },
        },
    }


def _base_agent_resources(*, resources: object | None = "default", schema_version: int = 1) -> dict[str, object]:
    payload: dict[str, object] = {"schema_version": schema_version}
    if resources == "default":
        payload["resources"] = _default_resources()
    elif resources is not None:
        payload["resources"] = resources
    return payload


def _config(
    *,
    agents: dict[str, object] | None = None,
    agent_resources: dict[str, object] | None = "default",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "project": {"display_name": "Test", "root_repo": "softos-agentic"},
        "repos": {"softos-agentic": {"path": ".", "kind": "root"}},
        "agents": agents if agents is not None else _base_agents(),
    }
    if agent_resources == "default":
        payload["agent_resources"] = _base_agent_resources()
    elif agent_resources is not None:
        payload["agent_resources"] = agent_resources
    return payload


class ResourceRegistryValidationTests(unittest.TestCase):
    def test_parses_three_logical_resources_distinct_from_executors(self) -> None:
        resources = parse_resource_registry(_config())
        self.assertEqual(["opencode-free", "opencode-go", "opencode-local"], list(resources))
        self.assertEqual("opencode-local", resources["opencode-local"].executor_id)
        self.assertEqual("opencode", resources["opencode-free"].executor_id)
        self.assertEqual("opencode", resources["opencode-go"].executor_id)
        self.assertEqual(1, resources["opencode-local"].capacity)
        self.assertEqual("worker_profile", resources["opencode-local"].model_resolution)
        self.assertEqual("dynamic_free", resources["opencode-free"].model_resolution)
        self.assertEqual("dynamic_go", resources["opencode-go"].model_resolution)
        # Free and Go share one underlying executor without collapsing resource identity.
        self.assertEqual(
            resources["opencode-free"].executor_id,
            resources["opencode-go"].executor_id,
        )
        self.assertNotEqual(
            resources["opencode-free"].resource_id,
            resources["opencode-go"].resource_id,
        )

    def test_workspace_config_loads_canonical_resources(self) -> None:
        root = Path(__file__).resolve().parents[2]
        resources = load_resource_registry(root / "workspace.config.json")
        self.assertEqual({"opencode-local", "opencode-free", "opencode-go"}, set(resources))
        self.assertEqual(1, resources["opencode-local"].capacity)
        self.assertEqual("opencode", resources["opencode-free"].executor_id)

    def test_canonical_workspace_config_passes_agents_registry_unchanged(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workspace_config = json.loads((root / "workspace.config.json").read_text(encoding="utf-8"))
        self.assertNotIn("resources", workspace_config["agents"])
        self.assertIn("agent_resources", workspace_config)
        registry = parse_agents_registry(workspace_config)
        self.assertIn("opencode", registry)
        self.assertIn("opencode-local", registry)
        self.assertEqual("opencode", registry["opencode"].adapter)
        resources = parse_resource_registry(workspace_config)
        self.assertEqual({"opencode-local", "opencode-free", "opencode-go"}, set(resources))

    def test_full_config_passes_agents_registry_without_stripping(self) -> None:
        full = _config()
        registry = parse_agents_registry(full)
        self.assertIn("opencode", registry)
        self.assertIn("opencode-local", registry)
        resources = parse_resource_registry(full)
        self.assertEqual({"opencode-local", "opencode-free", "opencode-go"}, set(resources))

    def test_missing_required_resource_fails(self) -> None:
        agent_resources = _base_agent_resources()
        del agent_resources["resources"]["opencode-go"]  # type: ignore[index]
        with self.assertRaisesRegex(AgentResourceError, "Faltan logical resources"):
            parse_resource_registry(_config(agent_resources=agent_resources))

    def test_invalid_schema_version_fails(self) -> None:
        agent_resources = _base_agent_resources(schema_version=2)
        with self.assertRaisesRegex(AgentResourceError, "schema_version"):
            parse_resource_registry(_config(agent_resources=agent_resources))

    def test_unknown_resource_field_fails(self) -> None:
        agent_resources = _base_agent_resources()
        agent_resources["resources"]["opencode-local"]["region"] = "us"  # type: ignore[index]
        with self.assertRaisesRegex(AgentResourceError, "Campo desconocido"):
            parse_resource_registry(_config(agent_resources=agent_resources))

    def test_forbidden_credential_and_identity_fields_are_rejected(self) -> None:
        forbidden_values = {
            "token": "secret-token",
            "credential": "x",
            "auth": {"configured": True},
            "provider": "lmstudio",
            "model": "bonsai-27b",
            "api_key": "sk-test",
        }
        for field, value in forbidden_values.items():
            with self.subTest(field=field):
                agent_resources = _base_agent_resources()
                agent_resources["resources"]["opencode-free"][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(AgentResourceError, "Campo prohibido"):
                    parse_resource_registry(_config(agent_resources=agent_resources))

    def test_executor_reference_must_exist(self) -> None:
        agent_resources = _base_agent_resources()
        agent_resources["resources"]["opencode-free"]["executor"] = "missing-executor"  # type: ignore[index]
        with self.assertRaisesRegex(AgentResourceError, "executor inexistente"):
            parse_resource_registry(_config(agent_resources=agent_resources))

    def test_capacity_validation(self) -> None:
        agent_resources = _base_agent_resources()
        agent_resources["resources"]["opencode-free"]["capacity"] = 0  # type: ignore[index]
        with self.assertRaisesRegex(AgentResourceError, "capacity"):
            parse_resource_registry(_config(agent_resources=agent_resources))

        agent_resources = _base_agent_resources()
        agent_resources["resources"]["opencode-local"]["capacity"] = 2  # type: ignore[index]
        with self.assertRaisesRegex(AgentResourceError, "opencode-local.capacity"):
            parse_resource_registry(_config(agent_resources=agent_resources))

    def test_local_model_resolution_must_remain_worker_owned(self) -> None:
        agent_resources = _base_agent_resources()
        agent_resources["resources"]["opencode-local"]["model_resolution"] = "dynamic_free"  # type: ignore[index]
        with self.assertRaisesRegex(AgentResourceError, "worker_profile"):
            parse_resource_registry(_config(agent_resources=agent_resources))

    def test_duplicate_resource_keys_fail_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workspace.config.json"
            # Intentional duplicate JSON key inside agent_resources.resources.
            path.write_text(
                """
                {
                  "agents": {
                    "schema_version": 1,
                    "executors": {
                      "opencode": {"adapter": "opencode", "executable": "opencode", "argv": []},
                      "opencode-local": {"adapter": "opencode", "executable": "opencode-softos", "argv": []}
                    }
                  },
                  "agent_resources": {
                    "schema_version": 1,
                    "resources": {
                      "opencode-local": {
                        "executor": "opencode-local",
                        "capabilities": ["write"],
                        "capacity": 1,
                        "cost_tier": "local",
                        "selection_priority": 10,
                        "model_resolution": "worker_profile",
                        "data_sensitivity": "local-only"
                      },
                      "opencode-local": {
                        "executor": "opencode-local",
                        "capabilities": ["write"],
                        "capacity": 1,
                        "cost_tier": "local",
                        "selection_priority": 10,
                        "model_resolution": "worker_profile",
                        "data_sensitivity": "local-only"
                      }
                    }
                  }
                }
                """,
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AgentResourceError, "duplicada"):
                load_resource_registry(path)


class AvailabilityAndSelectionTests(unittest.TestCase):
    def test_all_ten_availability_states_normalize(self) -> None:
        self.assertEqual(10, len(AVAILABILITY_STATES))
        for state in sorted(AVAILABILITY_STATES):
            with self.subTest(state=state):
                self.assertEqual(state, normalize_availability(state))
                self.assertEqual(state, normalize_availability(state.lower()))

    def test_unknown_evidence_normalizes_to_unknown_and_is_not_selectable(self) -> None:
        self.assertEqual("UNKNOWN", normalize_availability("not-a-real-state"))
        self.assertEqual("UNKNOWN", normalize_availability(""))
        self.assertEqual("UNKNOWN", normalize_availability(None))
        self.assertEqual("UNKNOWN", normalize_availability({"nested": True}))

        resources = parse_resource_registry(_config())
        filtered = filter_resources_for_selection(
            resources,
            availability={
                "opencode-local": "UNKNOWN",
                "opencode-free": "AVAILABLE",
                "opencode-go": "AUTH_UNCONFIGURED",
            },
        )
        self.assertEqual(["opencode-free"], filtered)

    def test_filter_unavailable_and_incompatible_before_priority(self) -> None:
        resources = parse_resource_registry(_config())
        availability = {
            "opencode-local": "AVAILABLE",
            "opencode-free": "AVAILABLE",
            "opencode-go": "AVAILABLE",
        }
        filtered = filter_resources_for_selection(
            resources,
            availability=availability,
            required_capabilities=["architecture"],
        )
        # Capability filter runs before priority: only go has architecture.
        self.assertEqual(["opencode-go"], filtered)

        ordered = order_resource_candidates(
            filtered,
            resources,
            preferred_order=["opencode-local", "opencode-free", "opencode-go"],
        )
        self.assertEqual(["opencode-go"], ordered)

    def test_deterministic_ordering_and_tie_break(self) -> None:
        resources = parse_resource_registry(_config())
        availability = {
            "opencode-local": "AVAILABLE",
            "opencode-free": "AVAILABLE",
            "opencode-go": "BUSY",
        }
        filtered = filter_resources_for_selection(resources, availability=availability)
        self.assertEqual(
            ["opencode-local", "opencode-free"],
            order_resource_candidates(filtered, resources),
        )
        self.assertEqual(
            ["opencode-local", "opencode-free"],
            order_resource_candidates(
                filtered,
                resources,
                preferred_order=["opencode-local", "opencode-free", "opencode-go"],
            ),
        )

    def test_local_only_sensitivity_filter(self) -> None:
        resources = parse_resource_registry(_config())
        availability = {
            "opencode-local": "AVAILABLE",
            "opencode-free": "AVAILABLE",
            "opencode-go": "AVAILABLE",
        }
        filtered = filter_resources_for_selection(
            resources,
            availability=availability,
            data_sensitivity="local-only",
        )
        self.assertEqual(["opencode-local"], filtered)

    def test_go_defaults_to_auth_unconfigured_without_evidence(self) -> None:
        resources = parse_resource_registry(_config())
        go = resources["opencode-go"]
        self.assertEqual("AUTH_UNCONFIGURED", default_availability_for_resource(go))
        self.assertEqual(
            "AVAILABLE",
            default_availability_for_resource(go, auth_evidence="AVAILABLE"),
        )
        self.assertEqual(
            "AUTH_FAILED",
            default_availability_for_resource(go, auth_evidence="auth_failed"),
        )
        self.assertEqual(
            "UNKNOWN",
            default_availability_for_resource(go, auth_evidence="weird-evidence"),
        )


class DynamicModelResolutionTests(unittest.TestCase):
    def test_resolve_free_model_uses_injectable_discovery_and_lexical_tie_break(self) -> None:
        result = resolve_free_model(
            discover=lambda: ["zeta-free", "alpha-free", "paid-pro", "alpha-free"],
        )
        self.assertEqual("AVAILABLE", result.availability)
        self.assertEqual("alpha-free", result.model_id)

    def test_resolve_free_model_without_candidates_is_model_unavailable(self) -> None:
        result = resolve_free_model(discover=lambda: ["paid-pro", "enterprise"])
        self.assertEqual("MODEL_UNAVAILABLE", result.availability)
        self.assertIsNone(result.model_id)

    def test_resolve_free_discovery_error_is_unknown(self) -> None:
        def boom() -> list[str]:
            raise RuntimeError("network")

        result = resolve_free_model(discover=boom)
        self.assertEqual("UNKNOWN", result.availability)
        self.assertIsNone(result.model_id)

    def test_resolve_go_requires_auth_evidence_then_discovers_dynamically(self) -> None:
        unconfigured = resolve_go_model(discover=lambda: ["go-model-b", "go-model-a"])
        self.assertEqual("AUTH_UNCONFIGURED", unconfigured.availability)
        self.assertIsNone(unconfigured.model_id)

        resolved = resolve_go_model(
            discover=lambda: ["go-model-b", "go-model-a"],
            auth_evidence="AVAILABLE",
        )
        self.assertEqual("AVAILABLE", resolved.availability)
        self.assertEqual("go-model-a", resolved.model_id)

    def test_no_persistent_concrete_model_policy_in_registry_metadata(self) -> None:
        resources = parse_resource_registry(_config())
        serialized = json.dumps(
            {
                resource_id: {
                    "executor": item.executor_id,
                    "model_resolution": item.model_resolution,
                    "cost_tier": item.cost_tier,
                }
                for resource_id, item in resources.items()
            }
        )
        for banned in ("bonsai", "lmstudio", "prism-ml", "granite", "gpt-", "claude"):
            self.assertNotIn(banned, serialized.lower())


if __name__ == "__main__":
    unittest.main()
