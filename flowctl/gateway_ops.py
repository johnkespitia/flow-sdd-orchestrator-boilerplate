from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def load_gateway_connection(*, root: Path, workspace_config: dict[str, object]) -> dict[str, str]:
    gateway = workspace_config.get("gateway")
    gateway_cfg = gateway if isinstance(gateway, dict) else {}
    connection = gateway_cfg.get("connection")
    connection_cfg = connection if isinstance(connection, dict) else {}
    mode = str(connection_cfg.get("mode", "") or "").strip().lower()
    base_url = str(connection_cfg.get("base_url", "") or "").strip()

    env_file = root / ".env.gateway"
    env_values: dict[str, str] = {}
    if env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_values[key.strip()] = value.strip()

    resolved_base_url = (
        os.environ.get("SOFTOS_GATEWAY_URL")
        or env_values.get("SOFTOS_GATEWAY_URL")
        or base_url
    ).strip()
    resolved_token = (
        os.environ.get("SOFTOS_GATEWAY_API_TOKEN")
        or env_values.get("SOFTOS_GATEWAY_API_TOKEN")
        or ""
    ).strip()

    return {
        "mode": mode,
        "base_url": resolved_base_url.rstrip("/"),
        "api_token": resolved_token,
    }


def _http_json(
    *,
    method: str,
    url: str,
    token: str,
    payload: dict[str, object] | None = None,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data: bytes | None = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Gateway HTTP {exc.code} en `{url}`: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"No pude conectar con gateway `{url}`: {exc}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Gateway devolvio JSON invalido desde `{url}`.") from exc
    if not isinstance(parsed, dict):
        raise SystemExit(f"Gateway devolvio una respuesta no soportada desde `{url}`.")
    return parsed


def _require_remote_gateway(connection: dict[str, str]) -> tuple[str, str]:
    if connection.get("mode") != "remote":
        raise SystemExit("El workspace no esta configurado en `gateway.connection.mode=remote`.")
    base_url = str(connection.get("base_url") or "").strip()
    if not base_url:
        raise SystemExit("No pude resolver `SOFTOS_GATEWAY_URL` ni `gateway.connection.base_url`.")
    return base_url, str(connection.get("api_token") or "")


def _default_actor() -> str:
    actor = str(os.environ.get("FLOW_ACTOR") or os.environ.get("USER") or "").strip()
    return actor or "unknown"


def _claim_state_from_state(state: dict[str, object], slug: str) -> dict[str, str]:
    claim = state.get("gateway_claim")
    if not isinstance(claim, dict):
        raise SystemExit(
            f"La spec `{slug}` no tiene claim remoto registrado. Usa `python3 ./flow gateway claim {slug}`."
        )
    payload = {
        "base_url": str(claim.get("base_url") or "").strip(),
        "spec_id": str(claim.get("spec_id") or "").strip(),
        "actor": str(claim.get("actor") or "").strip(),
        "lock_token": str(claim.get("lock_token") or "").strip(),
    }
    if not payload["base_url"] or not payload["spec_id"] or not payload["actor"] or not payload["lock_token"]:
        raise SystemExit(f"La spec `{slug}` no tiene metadata completa de claim remoto.")
    return payload


def _write_gateway_claim_state(
    *,
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    slug: str,
    spec_id: str,
    actor: str,
    lock_token: str,
    base_url: str,
) -> None:
    state = read_state(slug)
    state["gateway_claim"] = {
        "mode": "remote",
        "base_url": base_url,
        "spec_id": spec_id,
        "actor": actor,
        "lock_token": lock_token,
    }
    write_state(slug, state)


def _clear_gateway_claim_state(
    *,
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    slug: str,
) -> None:
    state = read_state(slug)
    state.pop("gateway_claim", None)
    write_state(slug, state)


def ensure_remote_claim_for_plan(
    *,
    root: Path,
    slug: str,
    read_state: Callable[[str], dict[str, object]],
    workspace_config: dict[str, object],
) -> None:
    connection = load_gateway_connection(root=root, workspace_config=workspace_config)
    if connection.get("mode") != "remote":
        return
    state = read_state(slug)
    claim = _claim_state_from_state(state, slug)
    spec_id = claim["spec_id"]
    actor = claim["actor"]
    lock_token = claim["lock_token"]
    base_url, token = _require_remote_gateway(connection)
    payload = _http_json(method="GET", url=f"{base_url}/v1/specs/{spec_id}", token=token)
    if str(payload.get("assignee") or "") != actor or str(payload.get("lock_token") or "") != lock_token:
        raise SystemExit(
            f"La spec `{slug}` ya no tiene claim remoto vigente para `{actor}`. Refresca o reclama de nuevo antes de planear."
        )


def command_gateway_list(
    args,
    *,
    root: Path,
    workspace_config: dict[str, object],
    json_dumps: Callable[[object], str],
) -> int:
    connection = load_gateway_connection(root=root, workspace_config=workspace_config)
    base_url, token = _require_remote_gateway(connection)
    params: list[tuple[str, str]] = []
    if getattr(args, "state", None):
        params.append(("state", str(args.state)))
    if getattr(args, "assignee", None):
        params.append(("assignee", str(args.assignee)))
    query = f"?{urlencode(params)}" if params else ""
    payload = _http_json(method="GET", url=f"{base_url}/v1/specs{query}", token=token)
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    items = payload.get("items", [])
    if not isinstance(items, list) or not items:
        print("No hay specs remotas.")
        return 0
    for item in items:
        if not isinstance(item, dict):
            continue
        print(
            f"{item.get('spec_id')} state={item.get('state')} assignee={item.get('assignee') or '-'} "
            f"lock={item.get('lock_expires_at') or '-'}"
        )
    return 0


def command_gateway_heartbeat(
    args,
    *,
    root: Path,
    workspace_config: dict[str, object],
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    json_dumps: Callable[[object], str],
) -> int:
    connection = load_gateway_connection(root=root, workspace_config=workspace_config)
    _base_url, token = _require_remote_gateway(connection)
    slug = str(args.spec).strip().lower()
    claim = _claim_state_from_state(read_state(slug), slug)
    ttl_seconds = int(getattr(args, "ttl_seconds", 120) or 120)
    payload = _http_json(
        method="POST",
        url=f"{claim['base_url']}/v1/specs/{claim['spec_id']}/heartbeat",
        token=token,
        payload={
            "actor": claim["actor"],
            "lock_token": claim["lock_token"],
            "source": "slave",
            "reason": str(getattr(args, "reason", "") or "").strip() or "heartbeat-from-flow",
            "ttl_seconds": ttl_seconds,
        },
    )
    response = {
        "spec_id": claim["spec_id"],
        "actor": claim["actor"],
        "lock_expires_at": payload.get("lock_expires_at"),
        "state": payload.get("state"),
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(response))
    else:
        print(json.dumps(response, ensure_ascii=True))
    return 0


def command_gateway_transition(
    args,
    *,
    root: Path,
    workspace_config: dict[str, object],
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    json_dumps: Callable[[object], str],
) -> int:
    connection = load_gateway_connection(root=root, workspace_config=workspace_config)
    _base_url, token = _require_remote_gateway(connection)
    slug = str(args.spec).strip().lower()
    claim = _claim_state_from_state(read_state(slug), slug)
    payload = _http_json(
        method="POST",
        url=f"{claim['base_url']}/v1/specs/{claim['spec_id']}/transition",
        token=token,
        payload={
            "actor": claim["actor"],
            "to_state": str(args.to_state).strip(),
            "lock_token": claim["lock_token"],
            "source": "slave",
            "reason": str(getattr(args, "reason", "") or "").strip() or "transition-from-flow",
        },
    )
    response = {
        "spec_id": claim["spec_id"],
        "actor": claim["actor"],
        "state": payload.get("state"),
        "assignee": payload.get("assignee"),
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(response))
    else:
        print(json.dumps(response, ensure_ascii=True))
    return 0


def command_gateway_release(
    args,
    *,
    root: Path,
    workspace_config: dict[str, object],
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    json_dumps: Callable[[object], str],
) -> int:
    connection = load_gateway_connection(root=root, workspace_config=workspace_config)
    _base_url, token = _require_remote_gateway(connection)
    slug = str(args.spec).strip().lower()
    claim = _claim_state_from_state(read_state(slug), slug)
    payload = _http_json(
        method="POST",
        url=f"{claim['base_url']}/v1/specs/{claim['spec_id']}/release",
        token=token,
        payload={
            "actor": claim["actor"],
            "lock_token": claim["lock_token"],
            "source": "slave",
            "reason": str(getattr(args, "reason", "") or "").strip() or "release-from-flow",
        },
    )
    _clear_gateway_claim_state(read_state=read_state, write_state=write_state, slug=slug)
    response = {
        "spec_id": claim["spec_id"],
        "actor": claim["actor"],
        "state": payload.get("state"),
        "assignee": payload.get("assignee"),
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(response))
    else:
        print(json.dumps(response, ensure_ascii=True))
    return 0


def command_gateway_reassign(
    args,
    *,
    root: Path,
    workspace_config: dict[str, object],
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    json_dumps: Callable[[object], str],
) -> int:
    connection = load_gateway_connection(root=root, workspace_config=workspace_config)
    _base_url, token = _require_remote_gateway(connection)
    slug = str(args.spec).strip().lower()
    claim = _claim_state_from_state(read_state(slug), slug)
    to_actor = str(args.to_actor).strip()
    if not to_actor:
        raise SystemExit("La reasignacion requiere `to_actor` no vacio.")
    ttl_seconds = int(getattr(args, "ttl_seconds", 120) or 120)
    payload = _http_json(
        method="POST",
        url=f"{claim['base_url']}/v1/specs/{claim['spec_id']}/reassign",
        token=token,
        payload={
            "actor": claim["actor"],
            "to_actor": to_actor,
            "lock_token": claim["lock_token"],
            "source": "slave",
            "reason": str(getattr(args, "reason", "") or "").strip() or f"reassign-to-{to_actor}",
            "ttl_seconds": ttl_seconds,
        },
    )
    next_lock = str(payload.get("lock_token") or "").strip()
    if not next_lock:
        raise SystemExit(f"Gateway no devolvio `lock_token` nuevo al reasignar `{claim['spec_id']}`.")
    _write_gateway_claim_state(
        read_state=read_state,
        write_state=write_state,
        slug=slug,
        spec_id=claim["spec_id"],
        actor=to_actor,
        lock_token=next_lock,
        base_url=claim["base_url"],
    )
    response = {
        "spec_id": claim["spec_id"],
        "from_actor": claim["actor"],
        "to_actor": to_actor,
        "lock_token": next_lock,
        "state": payload.get("state"),
        "assignee": payload.get("assignee"),
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(response))
    else:
        print(json.dumps(response, ensure_ascii=True))
    return 0


def command_gateway_fetch_spec(
    args,
    *,
    root: Path,
    workspace_config: dict[str, object],
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    json_dumps: Callable[[object], str],
) -> int:
    connection = load_gateway_connection(root=root, workspace_config=workspace_config)
    base_url, token = _require_remote_gateway(connection)
    spec_id = str(args.spec).strip().lower()
    payload = _http_json(method="GET", url=f"{base_url}/v1/specs/{spec_id}/source", token=token)
    path_text = str(payload.get("path") or "").strip()
    content = str(payload.get("content") or "")
    if not path_text or not content:
        raise SystemExit(f"Gateway no devolvio `path`/`content` validos para `{spec_id}`.")
    try:
        relative = Path(path_text).relative_to("/workspace")
    except ValueError:
        relative = Path("specs/features") / f"{spec_id}.spec.md"
    local_path = root / relative
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(content, encoding="utf-8")
    state = read_state(spec_id)
    remote_sync = state.get("gateway_remote_spec")
    sync_payload = remote_sync if isinstance(remote_sync, dict) else {}
    sync_payload.update(
        {
            "base_url": base_url,
            "spec_id": spec_id,
            "path": str(relative),
            "updated_at": str(payload.get("updated_at") or ""),
            "content_sha256": str(payload.get("content_sha256") or ""),
        }
    )
    state["spec_path"] = str(relative)
    state["gateway_remote_spec"] = sync_payload
    write_state(spec_id, state)
    response = {"spec_id": spec_id, "path": str(relative), "updated_at": sync_payload["updated_at"]}
    if bool(getattr(args, "json", False)):
        print(json_dumps(response))
    else:
        print(str(relative))
    return 0


def command_gateway_claim(
    args,
    *,
    root: Path,
    workspace_config: dict[str, object],
    read_state: Callable[[str], dict[str, object]],
    write_state: Callable[[str, dict[str, object]], None],
    json_dumps: Callable[[object], str],
) -> int:
    connection = load_gateway_connection(root=root, workspace_config=workspace_config)
    base_url, token = _require_remote_gateway(connection)
    spec_id = str(args.spec).strip().lower()
    actor = str(getattr(args, "actor", "") or "").strip() or _default_actor()
    ttl_seconds = int(getattr(args, "ttl_seconds", 120) or 120)
    payload = _http_json(
        method="POST",
        url=f"{base_url}/v1/specs/{spec_id}/claim",
        token=token,
        payload={
            "actor": actor,
            "source": "slave",
            "reason": str(getattr(args, "reason", "") or "").strip() or "claim-from-flow",
            "ttl_seconds": ttl_seconds,
        },
    )
    lock_token = str(payload.get("lock_token") or "").strip()
    if not lock_token:
        raise SystemExit(f"Gateway no devolvio `lock_token` al reclamar `{spec_id}`.")
    _write_gateway_claim_state(
        read_state=read_state,
        write_state=write_state,
        slug=spec_id,
        spec_id=spec_id,
        actor=actor,
        lock_token=lock_token,
        base_url=base_url,
    )
    fetch_args = type("FetchArgs", (), {"spec": spec_id, "json": False})()
    command_gateway_fetch_spec(
        fetch_args,
        root=root,
        workspace_config=workspace_config,
        read_state=read_state,
        write_state=write_state,
        json_dumps=json_dumps,
    )
    response = {
        "spec_id": spec_id,
        "actor": actor,
        "lock_token": lock_token,
        "state": payload.get("state"),
        "assignee": payload.get("assignee"),
        "lock_expires_at": payload.get("lock_expires_at"),
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(response))
    else:
        print(json.dumps(response, ensure_ascii=True))
    return 0
