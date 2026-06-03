import logging
from .module_base import BaseModule

logger = logging.getLogger(__name__)


class ModuleRegistry:
    def __init__(self):
        self._modules: dict[str, BaseModule] = {}

    def register(self, module: BaseModule) -> None:
        if module.name in self._modules:
            logger.warning(f"Module '{module.name}' already registered, overwriting")
        self._modules[module.name] = module
        logger.info(f"Registered module: {module.name}")

    def unregister(self, name: str) -> None:
        self._modules.pop(name, None)

    def get(self, name: str) -> BaseModule | None:
        return self._modules.get(name)

    def list_modules(self) -> list[BaseModule]:
        return list(self._modules.values())

    @property
    def count(self) -> int:
        return len(self._modules)
