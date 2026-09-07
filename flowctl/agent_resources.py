"""Logical OpenCode resource registry (PU-1 metadata contract).

Preserves the separation:
Logical Resource != Executor != Provider != Model != Capability != Credential

This module owns resource metadata, availability normalization, capability
filtering, deterministic candidate ordering, and injectable Free/Go model
discovery. It does not own process overlays, environment propagation, or CLI
resource flags (those are outside PU-1).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from flowctl.agent_executors import (
    EXECUTOR_ID_PATTERN,
    AgentExecutor,
    AgentRegistryError,
    load_json_object_with_duplicate_detection,
    parse_agents_registry,
)

RESOURCES_SCHEMA_VERSION = 1
REQUIRED_RESOURCE_IDS = ("opencode-local", "opencode-free", "opencode-go")

AVAILABILITY_STATES = frozenset(
    {
        "AVAILABLE",
        "BUSY",
        "CAPACITY_EXHAUSTED",
        "QUOTA_EXHAUSTED",
        "AUTH_UNCONFIGURED",
        "AUTH_FAILED",
        "MODEL_UNAVAILABLE",
        "PROVIDER_DOWN",
        "COOLDOWN",
        "UNKNOWN",
    }
)
SELECTABLE_AVAILABILITY_STATES = frozenset({"AVAILABLE"})

COST_TIERS = frozenset({"local", "cloud/free", "cloud/paid-low"})
MODEL_RESOLUTION_POLICIES = frozenset({"worker_profile", "dynamic_free", "dynamic_go"})
DATA_SENSITIVITY_CLASSES = frozenset({"local-only", "cloud-eligible"})
CANDIDATE_TIE_BREAKS = frozenset({"lexical"})

RESOURCE_FIELDS = frozenset(
    {
        "executor",
        "capabilities",
        "capacity",
        "cost_tier",
        "selection_priority",
        "model_resolution",
        "data_sensitivity",
        "candidate_tie_break",
    }
)
FORBIDDEN_RESOURCE_FIELDS = frozenset(
    {
        "token",
        "tokens",
        "credential",
        "credentials",
        "secret",
        "secrets",
        "api_key",
        "api_keys",
        "password",
        "passwd",
        "auth",
        "authorization",
        "provider",
        "providers",
        "model",
        "models",
        "provider_id",
        "model_id",
        "openai_api_key",
        "anthropic_api_key",
    }
)

DiscoverModelsFn = Callable[[], Sequence[str]]


class AgentResourceError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AgentResource:
    resource_id: str
    executor_id: str
    capabilities: frozenset[str]
    capacity: int
    cost_tier: str
    selection_priority: int
    model_resolution: str
    data_sensitivity: str
    candidate_tie_break: str = "lexical"


@dataclass(frozen=True)
class ModelResolutionResult:
    availability: str
    model_id: Optional[str] = None
    reason: Optional[str] = None


def normalize_availability(evidence: object) -> str:
    """Map runtime evidence to the V1 availability vocabulary.

    Unknown or unrecognized evidence becomes UNKNOWN and is not selectable.
    """
    if evidence is None:
        return "UNKNOWN"
    if isinstance(evidence, bytes):
        try:
            evidence = evidence.decode("utf-8")
        except UnicodeDecodeError:
            return "UNKNOWN"
    if not isinstance(evidence, str):
        return "UNKNOWN"
    normalized = evidence.strip().upper()
    if not normalized:
        return "UNKNOWN"
    if normalized in AVAILABILITY_STATES:
        return normalized
    return "UNKNOWN"


def is_selectable_availability(state: object) -> bool:
    return normalize_availability(state) in SELECTABLE_AVAILABILITY_STATES


def parse_resource_registry(
    workspace_config: Mapping[str, object],
    *,
    executors: Optional[Mapping[str, AgentExecutor]] = None,
) -> dict[str, AgentResource]:
    agent_resources = workspace_config.get("agent_resources")
    if agent_resources is None:
        raise AgentResourceError("workspace.config.json debe definir la seccion `agent_resources`.")
    if not isinstance(agent_resources, dict):
        raise AgentResourceError("`agent_resources` debe ser un objeto.")

    schema_version = agent_resources.get("schema_version")
    if type(schema_version) is not int or schema_version != RESOURCES_SCHEMA_VERSION:
        raise AgentResourceError(
            f"`agent_resources.schema_version` debe ser {RESOURCES_SCHEMA_VERSION}; "
            f"recibido `{schema_version!r}`."
        )

    resources_raw = agent_resources.get("resources")
    if not isinstance(resources_raw, dict) or not resources_raw:
        raise AgentResourceError("`agent_resources.resources` debe ser un objeto no vacio.")

    if executors is None:
        try:
            executors = parse_agents_registry(workspace_config)
        except AgentRegistryError as exc:
            raise AgentResourceError(exc.message) from exc

    resources: dict[str, AgentResource] = {}
    for resource_id, entry in resources_raw.items():
        resource_id_str = str(resource_id)
        if not EXECUTOR_ID_PATTERN.fullmatch(resource_id_str):
            raise AgentResourceError(
                f"ID de resource invalido `{resource_id_str}`; debe coincidir con ^[a-z0-9][a-z0-9-]*$."
            )
        if resource_id_str in resources:
            raise AgentResourceError(f"ID de resource duplicado: `{resource_id_str}`.")
        if not isinstance(entry, dict):
            raise AgentResourceError(f"`agent_resources.resources.{resource_id_str}` debe ser un objeto.")

        forbidden = sorted(set(entry) & FORBIDDEN_RESOURCE_FIELDS)
        if forbidden:
            raise AgentResourceError(
                f"Campo prohibido en `agent_resources.resources.{resource_id_str}`: `{forbidden[0]}` "
                "(credencial/auth/provider/model concretos no son metadata de resource)."
            )

        unknown_fields = set(entry) - RESOURCE_FIELDS
        if unknown_fields:
            field = sorted(unknown_fields)[0]
            raise AgentResourceError(
                f"Campo desconocido en `agent_resources.resources.{resource_id_str}`: `{field}`."
            )

        executor_id = entry.get("executor")
        if not isinstance(executor_id, str) or not executor_id.strip():
            raise AgentResourceError(
                f"`agent_resources.resources.{resource_id_str}.executor` debe ser un string no vacio."
            )
        executor_id = executor_id.strip()
        if executor_id not in executors:
            raise AgentResourceError(
                f"`agent_resources.resources.{resource_id_str}.executor` referencia executor inexistente "
                f"`{executor_id}`."
            )

        capabilities_raw = entry.get("capabilities")
        if not isinstance(capabilities_raw, list) or not capabilities_raw:
            raise AgentResourceError(
                f"`agent_resources.resources.{resource_id_str}.capabilities` debe ser un arreglo no vacio."
            )
        capabilities: list[str] = []
        for index, item in enumerate(capabilities_raw):
            if not isinstance(item, str) or not item.strip():
                raise AgentResourceError(
                    f"`agent_resources.resources.{resource_id_str}.capabilities[{index}]` "
                    "debe ser un string no vacio."
                )
            capability = item.strip()
            if capability in capabilities:
                raise AgentResourceError(
                    f"`agent_resources.resources.{resource_id_str}.capabilities` duplica `{capability}`."
                )
            capabilities.append(capability)

        capacity = entry.get("capacity")
        if type(capacity) is not int or isinstance(capacity, bool) or capacity < 1:
            raise AgentResourceError(
                f"`agent_resources.resources.{resource_id_str}.capacity` debe ser un entero >= 1; "
                f"recibido `{capacity!r}`."
            )
        if resource_id_str == "opencode-local" and capacity != 1:
            raise AgentResourceError("`agent_resources.resources.opencode-local.capacity` debe ser 1.")

        cost_tier = entry.get("cost_tier")
        if not isinstance(cost_tier, str) or cost_tier not in COST_TIERS:
            raise AgentResourceError(
                f"`agent_resources.resources.{resource_id_str}.cost_tier` invalido: `{cost_tier!r}`."
            )

        selection_priority = entry.get("selection_priority")
        if type(selection_priority) is not int or isinstance(selection_priority, bool):
            raise AgentResourceError(
                f"`agent_resources.resources.{resource_id_str}.selection_priority` debe ser un entero; "
                f"recibido `{selection_priority!r}`."
            )

        model_resolution = entry.get("model_resolution")
        if not isinstance(model_resolution, str) or model_resolution not in MODEL_RESOLUTION_POLICIES:
            raise AgentResourceError(
                f"`agent_resources.resources.{resource_id_str}.model_resolution` invalido: "
                f"`{model_resolution!r}`."
            )
        if resource_id_str == "opencode-local" and model_resolution != "worker_profile":
            raise AgentResourceError(
                "`agent_resources.resources.opencode-local.model_resolution` debe ser `worker_profile` "
                "(el worker/profile del repositorio posee model/provider)."
            )
        if resource_id_str == "opencode-free" and model_resolution != "dynamic_free":
            raise AgentResourceError(
                "`agent_resources.resources.opencode-free.model_resolution` debe ser `dynamic_free`."
            )
        if resource_id_str == "opencode-go" and model_resolution != "dynamic_go":
            raise AgentResourceError(
                "`agent_resources.resources.opencode-go.model_resolution` debe ser `dynamic_go`."
            )

        data_sensitivity = entry.get("data_sensitivity")
        if not isinstance(data_sensitivity, str) or data_sensitivity not in DATA_SENSITIVITY_CLASSES:
            raise AgentResourceError(
                f"`agent_resources.resources.{resource_id_str}.data_sensitivity` invalido: "
                f"`{data_sensitivity!r}`."
            )

        tie_break = entry.get("candidate_tie_break", "lexical")
        if not isinstance(tie_break, str) or tie_break not in CANDIDATE_TIE_BREAKS:
            raise AgentResourceError(
                f"`agent_resources.resources.{resource_id_str}.candidate_tie_break` invalido: "
                f"`{tie_break!r}`."
            )

        resources[resource_id_str] = AgentResource(
            resource_id=resource_id_str,
            executor_id=executor_id,
            capabilities=frozenset(capabilities),
            capacity=capacity,
            cost_tier=cost_tier,
            selection_priority=selection_priority,
            model_resolution=model_resolution,
            data_sensitivity=data_sensitivity,
            candidate_tie_break=tie_break,
        )

    missing = [resource_id for resource_id in REQUIRED_RESOURCE_IDS if resource_id not in resources]
    if missing:
        raise AgentResourceError(
            "Faltan logical resources requeridos en `agent_resources.resources`: "
            + ", ".join(f"`{item}`" for item in missing)
            + "."
        )

    _assert_no_concrete_identity_branching(resources)
    return dict(sorted(resources.items()))


def load_resource_registry(path: Path) -> dict[str, AgentResource]:
    try:
        workspace_config = load_json_object_with_duplicate_detection(path)
    except AgentRegistryError as exc:
        raise AgentResourceError(exc.message) from exc
    return parse_resource_registry(workspace_config)


def default_availability_for_resource(
    resource: AgentResource,
    *,
    evidence: object = None,
    auth_evidence: object = None,
) -> str:
    """Return normalized availability for a resource given optional runtime evidence.

    `opencode-go` / `dynamic_go` defaults to AUTH_UNCONFIGURED when no supported
    auth evidence is supplied. Credentials themselves are never accepted here.
    """
    if resource.model_resolution == "dynamic_go":
        if auth_evidence is None:
            return "AUTH_UNCONFIGURED"
        return normalize_availability(auth_evidence)
    if evidence is None:
        return "UNKNOWN"
    return normalize_availability(evidence)


def filter_resources_for_selection(
    resources: Mapping[str, AgentResource],
    *,
    availability: Mapping[str, object],
    required_capabilities: Optional[Sequence[str]] = None,
    data_sensitivity: Optional[str] = None,
) -> list[str]:
    """Filter unavailable or incompatible resources before priority/model resolution."""
    required = tuple(item.strip() for item in (required_capabilities or ()) if str(item).strip())
    selected: list[str] = []
    for resource_id, resource in sorted(resources.items()):
        state = normalize_availability(availability.get(resource_id))
        if state not in SELECTABLE_AVAILABILITY_STATES:
            continue
        if required and not set(required).issubset(resource.capabilities):
            continue
        if data_sensitivity == "local-only" and resource.data_sensitivity != "local-only":
            continue
        selected.append(resource_id)
    return selected


def order_resource_candidates(
    candidate_ids: Sequence[str],
    resources: Mapping[str, AgentResource],
    *,
    preferred_order: Optional[Sequence[str]] = None,
) -> list[str]:
    """Deterministic candidate ordering with lexical resource-id tie-break.

    When `preferred_order` is provided (policy table), preserve that relative
    order for ids still present after filtering. Otherwise sort by
    selection_priority ascending, then resource_id.
    """
    present = [resource_id for resource_id in candidate_ids if resource_id in resources]
    if preferred_order is not None:
        preferred = [resource_id for resource_id in preferred_order if resource_id in present]
        remainder = sorted(resource_id for resource_id in present if resource_id not in preferred)
        return preferred + remainder
    return sorted(
        present,
        key=lambda resource_id: (resources[resource_id].selection_priority, resource_id),
    )


def resolve_free_model(
    *,
    discover: DiscoverModelsFn,
    tie_break: str = "lexical",
) -> ModelResolutionResult:
    """Dynamically resolve a Free-tier model via injectable discovery.

    Only currently discovered `*-free` candidates are eligible. No concrete model
    name is persisted as policy. Deterministic lexical tie-break is the V1 default.
    """
    if tie_break not in CANDIDATE_TIE_BREAKS:
        raise AgentResourceError(f"candidate_tie_break invalido: `{tie_break!r}`.")
    try:
        discovered = list(discover())
    except Exception as exc:  # noqa: BLE001 - discovery boundary maps failures to availability
        return ModelResolutionResult(
            availability="UNKNOWN",
            reason=f"discovery_error:{exc.__class__.__name__}",
        )

    candidates: list[str] = []
    for item in discovered:
        if not isinstance(item, str):
            continue
        model_id = item.strip()
        if model_id.endswith("-free"):
            candidates.append(model_id)

    if not candidates:
        return ModelResolutionResult(
            availability="MODEL_UNAVAILABLE",
            reason="MODEL_UNAVAILABLE",
        )

    if tie_break == "lexical":
        ordered = sorted(set(candidates))
    else:  # pragma: no cover - guarded above
        ordered = sorted(set(candidates))
    return ModelResolutionResult(availability="AVAILABLE", model_id=ordered[0])


def resolve_go_model(
    *,
    discover: DiscoverModelsFn,
    auth_evidence: object = None,
    auth_discover: Optional[Callable[[], object]] = None,
    tie_break: str = "lexical",
) -> ModelResolutionResult:
    """Dynamically resolve a Go-tier model after supported auth evidence exists."""
    if auth_evidence is None and auth_discover is not None:
        try:
            auth_evidence = auth_discover()
        except Exception as exc:  # noqa: BLE001 - discovery boundary maps failures to availability
            return ModelResolutionResult(
                availability="UNKNOWN",
                reason=f"auth_discovery_error:{exc.__class__.__name__}",
            )

    auth_state = "AUTH_UNCONFIGURED" if auth_evidence is None else normalize_availability(auth_evidence)
    if auth_state == "AUTH_UNCONFIGURED":
        return ModelResolutionResult(availability="AUTH_UNCONFIGURED", reason="auth_unconfigured")
    if auth_state != "AVAILABLE":
        return ModelResolutionResult(availability=auth_state, reason="auth_not_available")

    if tie_break not in CANDIDATE_TIE_BREAKS:
        raise AgentResourceError(f"candidate_tie_break invalido: `{tie_break!r}`.")
    try:
        discovered = list(discover())
    except Exception as exc:  # noqa: BLE001 - discovery boundary maps failures to availability
        return ModelResolutionResult(
            availability="UNKNOWN",
            reason=f"discovery_error:{exc.__class__.__name__}",
        )

    candidates = []
    for item in discovered:
        if not isinstance(item, str):
            continue
        model_id = item.strip()
        if model_id:
            candidates.append(model_id)

    if not candidates:
        return ModelResolutionResult(
            availability="MODEL_UNAVAILABLE",
            reason="MODEL_UNAVAILABLE",
        )

    ordered = sorted(set(candidates))
    return ModelResolutionResult(availability="AVAILABLE", model_id=ordered[0])


def _assert_no_concrete_identity_branching(resources: Mapping[str, AgentResource]) -> None:
    """Core metadata must not encode concrete provider/model routing branches."""
    for resource in resources.values():
        if resource.model_resolution == "worker_profile":
            continue
        if resource.model_resolution not in {"dynamic_free", "dynamic_go"}:
            raise AgentResourceError(
                f"Resource `{resource.resource_id}` usa model_resolution concreto no permitido."
            )
