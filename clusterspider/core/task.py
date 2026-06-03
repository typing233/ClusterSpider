import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .module_base import ModuleResult, TargetType


class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    target: str
    target_type: TargetType
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: TaskState = TaskState.PENDING
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    results: list[ModuleResult] = field(default_factory=list)
    modules_total: int = 0
    modules_completed: int = 0
    modules_failed: int = 0

    def mark_running(self):
        self.state = TaskState.RUNNING
        self.started_at = datetime.utcnow().isoformat()

    def mark_completed(self):
        self.state = TaskState.COMPLETED
        self.finished_at = datetime.utcnow().isoformat()

    def add_result(self, result: ModuleResult):
        self.results.append(result)
        if result.success:
            self.modules_completed += 1
        else:
            self.modules_failed += 1

    @property
    def progress(self) -> str:
        done = self.modules_completed + self.modules_failed
        return f"{done}/{self.modules_total}"

    def summary(self) -> dict:
        return {
            "task_id": self.id,
            "target": self.target,
            "target_type": self.target_type.value,
            "state": self.state.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "modules_total": self.modules_total,
            "modules_completed": self.modules_completed,
            "modules_failed": self.modules_failed,
            "results": [r.to_dict() for r in self.results],
        }
