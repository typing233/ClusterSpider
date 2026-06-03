from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TargetType(Enum):
    DOMAIN = "domain"
    IP = "ip"


@dataclass
class ModuleResult:
    module_name: str
    target: str
    target_type: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    entities: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "module_name": self.module_name,
            "target": self.target,
            "target_type": self.target_type,
            "success": self.success,
            "data": self.data,
            "entities": self.entities,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class BaseModule(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def supported_targets(self) -> list[TargetType]:
        ...

    @property
    def timeout(self) -> float:
        return 30.0

    def accepts(self, target_type: TargetType) -> bool:
        return target_type in self.supported_targets

    @abstractmethod
    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        ...
