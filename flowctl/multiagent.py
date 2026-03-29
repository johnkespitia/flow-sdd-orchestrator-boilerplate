from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass
class SchedulerConfig:
    max_workers: int
    per_repo_capacity: int
    per_hot_area_capacity: int
    lock_ttl_seconds: int
    max_retries_execution: int


class LockBackend(Protocol):
    def acquire(
        self,
        *,
        lock_name: str,
        scope: str,
        repo: str,
        owner_run_id: str,
        owner_feature: str,
        owner_slice: str,
        ttl_seconds: int,
        details: str = "",
    ) -> dict[str, object]: ...

    def heartbeat(
        self,
        *,
        lock_name: str,
        owner_run_id: str,
        owner_feature: str,
        owner_slice: str,
        ttl_seconds: int,
        details: str = "",
    ) -> dict[str, object]: ...

    def release(
        self,
        *,
        lock_name: str,
        owner_run_id: str,
        owner_feature: str,
        owner_slice: str,
        details: str = "",
    ) -> dict[str, object]: ...

    def expire_stale(self) -> list[dict[str, object]]: ...

    def list_locks(self) -> list[dict[str, object]]: ...

    def list_events(self) -> list[dict[str, object]]: ...


def _hot_areas(slice_payload: dict[str, object]) -> list[str]:
    declared = [str(item).strip() for item in slice_payload.get("hot_areas", []) if str(item).strip()]
    if declared:
        return sorted(set(declared))
    explicit = str(slice_payload.get("hot_area", "")).strip()
    if explicit:
        return [explicit]
    patterns = [str(item) for item in slice_payload.get("owned_patterns", []) if str(item).strip()]
    result: list[str] = []
    for pattern in patterns:
        normalized = pattern.replace("\\", "/").strip("/")
        parts = [part for part in normalized.split("/") if part and part != "**"]
        if not parts:
            continue
        result.append("/".join(parts[:2]))
    return sorted(set(result))


def _semantic_locks(slice_payload: dict[str, object]) -> list[str]:
    declared = [str(item).strip() for item in slice_payload.get("semantic_locks", []) if str(item).strip()]
    if declared:
        return sorted(set(declared))
    inferred: set[str] = set()
    targets = [str(item) for item in slice_payload.get("owned_targets", []) if str(item).strip()]
    for target in targets:
        normalized = target.lower()
        if "migrations" in normalized:
            inferred.add("db:migrations")
        if "/api/" in normalized or "routes" in normalized:
            inferred.add("api:routes")
        if "contract" in normalized:
            inferred.add("contracts:schema")
    return sorted(inferred)


def _has_critical_overlap(a: dict[str, object], b: dict[str, object]) -> bool:
    a_targets = {str(item).strip() for item in a.get("owned_targets", []) if str(item).strip()}
    b_targets = {str(item).strip() for item in b.get("owned_targets", []) if str(item).strip()}
    if a_targets.intersection(b_targets):
        return True
    return False


def _global_lock_requests(job: dict[str, object]) -> list[dict[str, str]]:
    repo = str(job.get("repo", "")).strip()
    requests: list[dict[str, str]] = []
    for lock_name in job.get("semantic_locks", []):
        name = str(lock_name).strip()
        if not name:
            continue
        requests.append({"lock_name": f"semantic:{name}", "scope": "semantic", "repo": repo})
    hot_areas = [str(item).strip() for item in job.get("hot_areas", []) if str(item).strip()]
    if hot_areas:
        for hot_area in hot_areas:
            requests.append({"lock_name": f"hot-area:{repo}:{hot_area}", "scope": "hot_area", "repo": repo})
    else:
        requests.append({"lock_name": f"repo:{repo}", "scope": "repo", "repo": repo})
    return requests


def run_slice_scheduler(
    *,
    feature_slug: str,
    plan_payload: dict[str, object],
    start_slice_callable: Callable[[str], int],
    utc_now: Callable[[], str],
    config: SchedulerConfig,
    lock_backend: LockBackend | None = None,
    owner_run_id: str | None = None,
) -> dict[str, object]:
    effective_run_id = str(owner_run_id or feature_slug).strip() or feature_slug
    slices = [item for item in plan_payload.get("slices", []) if isinstance(item, dict)]
    jobs: dict[str, dict[str, object]] = {}
    for payload in slices:
        name = str(payload.get("name", "")).strip()
        if not name:
            continue
        jobs[name] = {
            "slice": name,
            "repo": str(payload.get("repo", "")).strip(),
            "depends_on": [str(dep).strip() for dep in payload.get("depends_on", []) if str(dep).strip()],
            "hot_areas": _hot_areas(payload),
            "semantic_locks": _semantic_locks(payload),
            "owned_targets": [str(item) for item in payload.get("owned_targets", [])],
            "status": "pending",
            "attempt": 0,
            "worker": None,
            "started_at": None,
            "finished_at": None,
            "failure_reason": None,
            "wait_reasons": [],
            "acquired_locks": [],
        }
    # preflight overlap graph
    overlap_pairs: set[tuple[str, str]] = set()
    names = sorted(jobs)
    for idx, left in enumerate(names):
        for right in names[idx + 1 :]:
            if _has_critical_overlap(jobs[left], jobs[right]):
                overlap_pairs.add((left, right))

    state_lock = threading.Lock()
    dlq: list[dict[str, object]] = []
    waits: list[dict[str, object]] = []
    lock_table: dict[str, dict[str, object]] = {}
    lock_events: list[dict[str, object]] = []
    running_by_repo: dict[str, int] = {}
    running_by_hot_area: dict[str, int] = {}
    running_jobs: set[str] = set()
    completed = 0
    failed = False
    started_at = utc_now()

    def _lock_event(event: str, lock_name: str, owner: str, reason: str) -> None:
        lock_events.append(
            {
                "event": event,
                "lock": lock_name,
                "owner": owner,
                "reason": reason,
                "at": utc_now(),
            }
        )

    def _acquire_locks(job: dict[str, object], now_epoch: float) -> tuple[bool, str]:
        if lock_backend is not None:
            released: list[str] = []
            for expired in lock_backend.expire_stale():
                released.append(str(expired.get("lock_name", "")).strip())
            for lock_name in released:
                _lock_event("expire", lock_name, "expired-owner", "ttl-expired")
            acquired_requests: list[dict[str, str]] = []
            for request in _global_lock_requests(job):
                result = lock_backend.acquire(
                    lock_name=request["lock_name"],
                    scope=request["scope"],
                    repo=request["repo"],
                    owner_run_id=effective_run_id,
                    owner_feature=feature_slug,
                    owner_slice=str(job["slice"]),
                    ttl_seconds=config.lock_ttl_seconds,
                    details="scheduler-acquire",
                )
                if bool(result.get("granted")):
                    acquired_requests.append(request)
                    _lock_event("acquire", request["lock_name"], str(job["slice"]), "global-lock")
                    continue
                owner = ":".join(
                    [
                        str(result.get("owner_run_id", "")).strip(),
                        str(result.get("owner_feature", "")).strip(),
                        str(result.get("owner_slice", "")).strip(),
                    ]
                ).strip(":")
                _lock_event("denied", request["lock_name"], str(job["slice"]), f"owned-by:{owner or 'unknown'}")
                for acquired in acquired_requests:
                    lock_backend.release(
                        lock_name=acquired["lock_name"],
                        owner_run_id=effective_run_id,
                        owner_feature=feature_slug,
                        owner_slice=str(job["slice"]),
                        details="rollback-partial-acquire",
                    )
                    _lock_event("release", acquired["lock_name"], str(job["slice"]), "rollback-partial-acquire")
                return False, f"wait-global-lock:{request['lock_name']}"
            job["acquired_locks"] = acquired_requests
            return True, ""
        for lock_name, lock_payload in list(lock_table.items()):
            expires_at = float(lock_payload.get("expires_epoch", 0.0) or 0.0)
            if expires_at <= now_epoch:
                owner = str(lock_payload.get("owner", "")).strip()
                if owner in running_jobs:
                    lock_payload["expires_epoch"] = now_epoch + float(config.lock_ttl_seconds)
                    lock_payload["reason"] = "heartbeat-renew"
                else:
                    lock_table.pop(lock_name, None)
                    _lock_event("expire", lock_name, owner, "ttl-expired")
        for lock_name in job["semantic_locks"]:
            current = lock_table.get(lock_name)
            if current is not None and str(current.get("owner")) != job["slice"]:
                _lock_event("denied", lock_name, job["slice"], f"owned-by:{current.get('owner')}")
                return False, f"semantic-lock:{lock_name}"
        for lock_name in job["semantic_locks"]:
            lock_table[lock_name] = {
                "owner": job["slice"],
                "reason": "slice-execution",
                "expires_epoch": now_epoch + float(config.lock_ttl_seconds),
            }
            _lock_event("acquire", lock_name, str(job["slice"]), "slice-execution")
        return True, ""

    def _release_locks(job: dict[str, object]) -> None:
        if lock_backend is not None:
            for request in list(job.get("acquired_locks", [])):
                lock_backend.release(
                    lock_name=str(request["lock_name"]),
                    owner_run_id=effective_run_id,
                    owner_feature=feature_slug,
                    owner_slice=str(job["slice"]),
                    details="slice-finished",
                )
                _lock_event("release", str(request["lock_name"]), str(job["slice"]), "global-lock")
            job["acquired_locks"] = []
            return
        for lock_name in list(lock_table):
            if str(lock_table[lock_name].get("owner")) == job["slice"]:
                _lock_event("release", lock_name, str(job["slice"]), "slice-finished")
                lock_table.pop(lock_name, None)

    def _heartbeat_running_locks(now_epoch: float) -> None:
        if lock_backend is not None:
            for job_name in list(running_jobs):
                job = jobs.get(job_name)
                if not isinstance(job, dict):
                    continue
                for request in job.get("acquired_locks", []):
                    result = lock_backend.heartbeat(
                        lock_name=str(request["lock_name"]),
                        owner_run_id=effective_run_id,
                        owner_feature=feature_slug,
                        owner_slice=str(job["slice"]),
                        ttl_seconds=config.lock_ttl_seconds,
                        details="scheduler-heartbeat",
                    )
                    _lock_event("heartbeat", str(request["lock_name"]), str(job["slice"]), str(result.get("status", "heartbeat")))
            return
        for lock_name, lock_payload in lock_table.items():
            owner = str(lock_payload.get("owner", "")).strip()
            if owner in running_jobs:
                lock_payload["expires_epoch"] = now_epoch + float(config.lock_ttl_seconds)
                lock_payload["reason"] = "heartbeat-renew"

    def _mark_dependency_blocked() -> int:
        blocked_count = 0
        for job_name in sorted(jobs):
            job = jobs[job_name]
            if job["status"] != "pending":
                continue
            failed_parent = ""
            for parent in job["depends_on"]:
                parent_job = jobs.get(parent)
                if not isinstance(parent_job, dict):
                    continue
                if str(parent_job.get("status")) in {"failed", "blocked"}:
                    failed_parent = parent
                    break
            if failed_parent:
                job["status"] = "blocked"
                job["finished_at"] = utc_now()
                job["failure_reason"] = f"dependency-failed:{failed_parent}"
                blocked_count += 1
        return blocked_count

    def _can_run(job: dict[str, object]) -> tuple[bool, str]:
        # DAG gate
        for parent in job["depends_on"]:
            parent_job = jobs.get(parent)
            if parent_job is None:
                continue
            if parent_job["status"] != "passed":
                return False, f"dag-wait:{parent}"
        # repo/hot-area capacities
        repo = str(job["repo"])
        if running_by_repo.get(repo, 0) >= config.per_repo_capacity:
            return False, f"repo-capacity:{repo}"
        for hot_area in job["hot_areas"]:
            if running_by_hot_area.get(hot_area, 0) >= config.per_hot_area_capacity:
                return False, f"hot-area-capacity:{hot_area}"
        # overlap block
        for left, right in overlap_pairs:
            if job["slice"] == left and right in running_jobs:
                return False, f"overlap:{right}"
            if job["slice"] == right and left in running_jobs:
                return False, f"overlap:{left}"
        ok, reason = _acquire_locks(job, time.time())
        if not ok:
            return False, reason
        return True, ""

    def _mark_wait(job: dict[str, object], reason: str) -> None:
        entry = {"slice": job["slice"], "reason": reason, "at": utc_now()}
        waits.append(entry)
        job["wait_reasons"].append(reason)

    def _worker_run(job_name: str, worker_id: int) -> tuple[int, str]:
        rc = start_slice_callable(job_name)
        return rc, f"worker-{worker_id}"

    futures: dict[Future[tuple[int, str]], str] = {}
    with ThreadPoolExecutor(max_workers=max(1, config.max_workers), thread_name_prefix="flow-scheduler-worker") as executor:
        while completed < len(jobs):
            with state_lock:
                _heartbeat_running_locks(time.time())
                # finalize completed futures
                done_futures = [future for future in futures if future.done()]
                for future in done_futures:
                    name = futures.pop(future)
                    rc, worker_name = future.result()
                    job = jobs[name]
                    job["finished_at"] = utc_now()
                    running_jobs.discard(name)
                    running_by_repo[job["repo"]] = max(0, running_by_repo.get(job["repo"], 0) - 1)
                    for hot_area in job["hot_areas"]:
                        running_by_hot_area[hot_area] = max(0, running_by_hot_area.get(hot_area, 0) - 1)
                    _release_locks(job)
                    if rc == 0:
                        job["status"] = "passed"
                        job["worker"] = worker_name
                        completed += 1
                    else:
                        if int(job["attempt"]) >= config.max_retries_execution + 1:
                            job["status"] = "failed"
                            job["failure_reason"] = f"execution-failed:{rc}"
                            dlq.append({"slice": name, "reason": job["failure_reason"], "attempt": job["attempt"]})
                            completed += 1
                            failed = True
                        else:
                            job["status"] = "pending"
                            job["failure_reason"] = f"retry-scheduled:{rc}"
                blocked_now = _mark_dependency_blocked()
                if blocked_now:
                    completed += blocked_now
                    failed = True
                # schedule pending jobs
                for name in sorted(jobs):
                    if name in running_jobs:
                        continue
                    job = jobs[name]
                    if job["status"] != "pending":
                        continue
                    can_run, reason = _can_run(job)
                    if not can_run:
                        _mark_wait(job, reason)
                        continue
                    job["status"] = "running"
                    job["attempt"] = int(job["attempt"]) + 1
                    job["started_at"] = utc_now()
                    running_jobs.add(name)
                    running_by_repo[job["repo"]] = running_by_repo.get(job["repo"], 0) + 1
                    for hot_area in job["hot_areas"]:
                        running_by_hot_area[hot_area] = running_by_hot_area.get(hot_area, 0) + 1
                    worker_id = len(futures) + 1
                    future = executor.submit(_worker_run, name, worker_id)
                    futures[future] = name
            time.sleep(0.01)

    finished_at = utc_now()
    if lock_backend is not None:
        lock_report = [
            {
                "lock": str(item.get("lock_name", "")),
                "owner": ":".join(
                    [
                        str(item.get("owner_run_id", "")).strip(),
                        str(item.get("owner_feature", "")).strip(),
                        str(item.get("owner_slice", "")).strip(),
                    ]
                ).strip(":"),
                "reason": str(item.get("scope", "")),
            }
            for item in lock_backend.list_locks()
        ]
        event_report = [
            {
                "event": str(item.get("event_type", "")),
                "lock": str(item.get("lock_name", "")),
                "owner": ":".join(
                    [
                        str(item.get("actor_run_id", "")).strip(),
                        str(item.get("feature_slug", "")).strip(),
                        str(item.get("slice_name", "")).strip(),
                    ]
                ).strip(":"),
                "reason": str(item.get("details", "")),
                "at": str(item.get("timestamp", "")),
            }
            for item in lock_backend.list_events()
        ]
    else:
        lock_report = [
            {"lock": lock_name, "owner": payload["owner"], "reason": payload["reason"]}
            for lock_name, payload in sorted(lock_table.items())
        ]
        event_report = lock_events
    return {
        "feature": feature_slug,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": "failed" if failed else "passed",
        "queue_size": len(jobs),
        "capacity": {
            "max_workers": config.max_workers,
            "per_repo_capacity": config.per_repo_capacity,
            "per_hot_area_capacity": config.per_hot_area_capacity,
        },
        "jobs": [jobs[name] for name in sorted(jobs)],
        "waits": waits,
        "locks": lock_report,
        "lock_events": event_report,
        "dlq": dlq,
        "traceability": [
            {"feature": feature_slug, "slice": job["slice"], "worker": job["worker"], "status": job["status"]}
            for job in sorted(jobs.values(), key=lambda item: str(item["slice"]))
        ],
    }
