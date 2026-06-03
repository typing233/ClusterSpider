import asyncio
import logging
from typing import Callable

from .module_base import BaseModule, ModuleResult, TargetType
from .registry import ModuleRegistry
from .task import Task, TaskState

logger = logging.getLogger(__name__)


class TaskQueue:
    """Lightweight asyncio.Queue-based task queue with concurrent workers."""

    def __init__(self, max_workers: int = 3):
        self._queue: asyncio.Queue[Task] = asyncio.Queue()
        self._max_workers = max_workers
        self._running = False
        self._workers: list[asyncio.Task] = []
        self._handler: Callable[[Task], asyncio.Future] | None = None
        self._processed: dict[str, Task] = {}

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def processed(self) -> dict[str, Task]:
        return self._processed

    def set_handler(self, handler: Callable):
        self._handler = handler

    async def put(self, task: Task):
        await self._queue.put(task)
        logger.debug(f"Task {task.id} queued (queue size: {self._queue.qsize()})")

    async def start(self):
        if self._running:
            return
        self._running = True
        for i in range(self._max_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
        logger.info(f"TaskQueue started with {self._max_workers} workers")

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("TaskQueue stopped")

    async def _worker(self, worker_id: int):
        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            logger.debug(f"Worker-{worker_id} picked up task {task.id}")
            try:
                if self._handler:
                    await self._handler(task)
                self._processed[task.id] = task
            except Exception as e:
                logger.error(f"Worker-{worker_id} error on task {task.id}: {e}")
                task.state = TaskState.FAILED
                self._processed[task.id] = task
            finally:
                self._queue.task_done()

    async def join(self):
        await self._queue.join()

    async def drain(self):
        """Process all queued tasks then stop."""
        await self.start()
        await self.join()
        await self.stop()


class ExecutionEngine:
    def __init__(self, registry: ModuleRegistry, max_concurrency: int = 10, queue_workers: int = 3):
        self.registry = registry
        self.max_concurrency = max_concurrency
        self._tasks: dict[str, Task] = {}
        self._queue = TaskQueue(max_workers=queue_workers)
        self._queue.set_handler(self._execute_task_internal)

    @property
    def task_queue(self) -> TaskQueue:
        return self._queue

    async def run_module(self, module: BaseModule, target: str, target_type: TargetType) -> ModuleResult:
        try:
            result = await asyncio.wait_for(
                module.execute(target, target_type),
                timeout=module.timeout,
            )
            if result.success:
                logger.info(f"Module '{module.name}' succeeded for {target}")
            else:
                logger.warning(f"Module '{module.name}' returned failure for {target}: {result.error}")
            return result
        except asyncio.TimeoutError:
            err = f"Timeout after {module.timeout}s"
            logger.error(f"Module '{module.name}' timed out for {target} ({module.timeout}s)")
            return ModuleResult(
                module_name=module.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=err,
            )
        except Exception as e:
            err = f"Unhandled exception: {type(e).__name__}: {e}"
            logger.error(f"Module '{module.name}' crashed for {target}: {err}")
            return ModuleResult(
                module_name=module.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=err,
            )

    async def _execute_task_internal(self, task: Task) -> Task:
        task.mark_running()
        self._tasks[task.id] = task
        logger.info(f"Task {task.id} started for {task.target} ({task.target_type.value})")

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
        logger.info(
            f"Task {task.id} completed: "
            f"{task.modules_completed} succeeded, {task.modules_failed} failed "
            f"(total: {task.modules_total})"
        )
        return task

    async def scan(self, target: str, target_type: TargetType) -> Task:
        """Execute a single scan immediately (bypass queue)."""
        task = Task(target=target, target_type=target_type)
        return await self._execute_task_internal(task)

    async def enqueue(self, target: str, target_type: TargetType) -> Task:
        """Submit a task to the queue for async processing."""
        task = Task(target=target, target_type=target_type)
        self._tasks[task.id] = task
        await self._queue.put(task)
        return task

    async def run_batch(self, targets: list[tuple[str, TargetType]]) -> list[Task]:
        """Enqueue multiple targets and wait for all to complete."""
        tasks = []
        for target, target_type in targets:
            t = await self.enqueue(target, target_type)
            tasks.append(t)
        await self._queue.drain()
        return [self._tasks[t.id] for t in tasks]

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)
