from __future__ import annotations

import threading
import time

from .config import Settings
from .executor import run_flow_command
from .feedback import send_feedback, send_feedback_event
from .store import TaskStore


def _task_status(task: dict[str, object], result: dict[str, object]) -> str:
    if int(result["exit_code"]) != 0:
        return "failed"

    if task.get("intent") == "spec.review":
        parsed_output = result.get("parsed_output")
        if isinstance(parsed_output, dict) and not bool(parsed_output.get("ready_to_approve", False)):
            return "completed_with_findings"

    return "succeeded"


def _flow_confirmed_closed(task: dict[str, object], result: dict[str, object]) -> bool:
    # Only execution intents should emit the "closed" lifecycle event.
    intent = str(task.get("intent") or "").strip()
    if intent not in {"workflow.execute_feature"}:
        return False

    parsed = result.get("parsed_output")
    if isinstance(parsed, dict):
        status = str(parsed.get("status", "")).strip().lower()
        if status in {"closed", "done", "released"}:
            return True
        items = parsed.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and str(item.get("status", "")).strip().lower() in {"closed", "done", "released"}:
                    return True
    return False


class TaskWorker:
    def __init__(self, settings: Settings, store: TaskStore) -> None:
        self.settings = settings
        self.store = store
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="softos-gateway-worker", daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            task = self.store.claim_next()
            if task is None:
                time.sleep(self.settings.worker_poll_interval)
                continue

            self.store.append_task_event(
                task_id=task["task_id"],
                event="execution_started",
                source="worker",
                status="started",
                payload={"intent": task["intent"]},
            )
            try:
                send_feedback_event(
                    self.settings,
                    event="execution_started",
                    source="worker",
                    status="started",
                    payload={"task_id": task["task_id"], "intent": task["intent"]},
                    response_target=task.get("response_target") if isinstance(task.get("response_target"), dict) else None,
                )
            except Exception:
                pass
            result = run_flow_command(self.settings, task["command"])
            status = _task_status(task, result)
            finished_task = self.store.finish(
                task["task_id"],
                status=status,
                exit_code=result["exit_code"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                parsed_output=result["parsed_output"],
            )
            if status.startswith("succeeded") and str(task.get("intent")) == "spec.review":
                self.store.append_task_event(
                    task_id=task["task_id"],
                    event="review_requested",
                    source="worker",
                    status=status,
                    payload={},
                )
                try:
                    send_feedback_event(
                        self.settings,
                        event="review_requested",
                        source="worker",
                        status=status,
                        payload={"task_id": task["task_id"]},
                        response_target=task.get("response_target") if isinstance(task.get("response_target"), dict) else None,
                    )
                except Exception:
                    pass
            if status.startswith("succeeded") and str(task.get("intent")) == "spec.approve":
                self.store.append_task_event(
                    task_id=task["task_id"],
                    event="approved",
                    source="worker",
                    status=status,
                    payload={},
                )
                try:
                    send_feedback_event(
                        self.settings,
                        event="approved",
                        source="worker",
                        status=status,
                        payload={"task_id": task["task_id"]},
                        response_target=task.get("response_target") if isinstance(task.get("response_target"), dict) else None,
                    )
                except Exception:
                    pass
            if status.startswith("succeeded") and str(task.get("intent")) == "workflow.intake":
                try:
                    send_feedback_event(
                        self.settings,
                        event="created",
                        source="worker",
                        status=status,
                        payload={"task_id": task["task_id"]},
                        response_target=task.get("response_target") if isinstance(task.get("response_target"), dict) else None,
                    )
                except Exception:
                    pass
            if status.startswith("failed"):
                try:
                    send_feedback_event(
                        self.settings,
                        event="execution_failed",
                        source="worker",
                        status=status,
                        payload={"task_id": task["task_id"]},
                        response_target=task.get("response_target") if isinstance(task.get("response_target"), dict) else None,
                    )
                except Exception:
                    pass
            elif status.startswith("succeeded"):
                try:
                    send_feedback_event(
                        self.settings,
                        event="execution_succeeded",
                        source="worker",
                        status=status,
                        payload={"task_id": task["task_id"]},
                        response_target=task.get("response_target") if isinstance(task.get("response_target"), dict) else None,
                    )
                except Exception:
                    pass
            if status.startswith("succeeded") and _flow_confirmed_closed(task, result):
                self.store.append_task_event(
                    task_id=task["task_id"],
                    event="closed",
                    source="worker",
                    status="confirmed",
                    payload={"by": "flow"},
                )
                try:
                    send_feedback_event(
                        self.settings,
                        event="closed",
                        source="worker",
                        status="confirmed",
                        payload={"task_id": task["task_id"], "by": "flow"},
                        response_target=task.get("response_target") if isinstance(task.get("response_target"), dict) else None,
                    )
                except Exception:
                    pass
            try:
                send_feedback(self.settings, finished_task)
            except Exception:
                pass
