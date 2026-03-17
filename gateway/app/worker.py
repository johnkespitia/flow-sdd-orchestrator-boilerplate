from __future__ import annotations

import threading
import time

from .config import Settings
from .executor import run_flow_command
from .feedback import send_feedback
from .store import TaskStore


def _task_status(task: dict[str, object], result: dict[str, object]) -> str:
    if int(result["exit_code"]) != 0:
        return "failed"

    if task.get("intent") == "spec.review":
        parsed_output = result.get("parsed_output")
        if isinstance(parsed_output, dict) and not bool(parsed_output.get("ready_to_approve", False)):
            return "completed_with_findings"

    return "succeeded"


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
            try:
                send_feedback(self.settings, finished_task)
            except Exception:
                pass
