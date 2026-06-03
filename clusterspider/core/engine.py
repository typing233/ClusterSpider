import asyncio
import logging
from datetime import datetime

from .module_base import BaseModule, ModuleResult, TargetType
from .registry import ModuleRegistry
from .task import Task, TaskState

logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(self, registry: ModuleRegistry, max_concurrency: int = 10):
        self.registry = registry
        self.max_concurrency = max_concurrency
        self._tasks: dict[str, Task] = {}

    async def run_module(self, module: BaseModule, target: str, target_type: TargetType) -> ModuleResult:
        try:
            result = await asyncio.wait_for(
                module.execute(target, target_type),
                timeout=module.timeout,
            )
            logger.info(f"Module '{module.name}' completed for {target}")
            return result
        except asyncio.TimeoutError:
            logger.error(f"Module '{module.name}' timed out for {target}")
            return ModuleResult(
                module_name=module.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=f"Timeout after {module.timeout}s",
            )
        except Exception as e:
            logger.error(f"Module '{module.name}' failed for {target}: {e}")
            return ModuleResult(
                module_name=module.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=str(e),
            )

    async def execute_task(self, task: Task) -> Task:
        task.mark_running()
        self._tasks[task.id] = task
        logger.info(f"Task {task.id} started for {task.target}")

        modules = [m for m in self.registry.list_modules() if m.accepts(task.target_type)]
        task.modules_total = len(modules)

        if not modules:
            logger.warning(f"No modules available for target type: {task.target_type.value}")
            task.mark_completed()
            return task

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def run_with_semaphore(module: BaseModule):
            async with semaphore:
                return await self.run_module(module, task.target, task.target_type)

        coros = [run_with_semaphore(m) for m in modules]
        results = await asyncio.gather(*coros, return_exceptions=False)

        for result in results:
            task.add_result(result)

        task.mark_completed()
        logger.info(f"Task {task.id} completed: {task.modules_completed} ok, {task.modules_failed} failed")
        return task

    async def scan(self, target: str, target_type: TargetType) -> Task:
        task = Task(target=target, target_type=target_type)
        return await self.execute_task(task)

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)
