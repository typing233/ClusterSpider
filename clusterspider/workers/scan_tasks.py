import asyncio
import logging

import redis

from .celery_app import celery_app
from clusterspider.config import settings
from clusterspider.core import ModuleRegistry, ExecutionEngine, TargetType
from clusterspider.modules import ALL_MODULES
from clusterspider.graph.driver import get_driver, close_driver
from clusterspider.graph.ingest import GraphIngestor
from clusterspider.storage.freshness import FreshnessTracker

logger = logging.getLogger(__name__)


def _publish_progress(task_id: str, data: dict):
    try:
        r = redis.from_url(settings.redis_url)
        import json
        r.publish(f"scan_progress:{task_id}", json.dumps(data))
        r.close()
    except Exception as e:
        logger.debug(f"Failed to publish progress: {e}")


@celery_app.task(bind=True, name="clusterspider.workers.scan_tasks.run_scan")
def run_scan(self, target: str, target_type: str, user_id: str, module_names: list[str] | None = None):
    return asyncio.run(_run_scan_async(self, target, target_type, user_id, module_names))


async def _run_scan_async(task, target: str, target_type: str, user_id: str, module_names: list[str] | None):
    registry = ModuleRegistry()
    for module_cls in ALL_MODULES:
        m = module_cls()
        if module_names is None or m.name in module_names:
            registry.register(m)

    tt = TargetType(target_type)
    engine = ExecutionEngine(registry, max_concurrency=5)

    freshness = FreshnessTracker()
    driver = await get_driver()
    ingestor = GraphIngestor(driver)

    modules = [m for m in registry.list_modules() if m.accepts(tt)]
    total = len(modules)
    completed = 0
    results_summary = []

    _publish_progress(task.request.id, {
        "state": "STARTED",
        "total": total,
        "completed": 0,
        "current_module": "",
    })

    for module in modules:
        if freshness.is_fresh(module.name, target_type, target):
            completed += 1
            results_summary.append({"module": module.name, "status": "skipped_fresh"})
            continue

        _publish_progress(task.request.id, {
            "state": "PROGRESS",
            "total": total,
            "completed": completed,
            "current_module": module.name,
        })

        result = await engine.run_module(module, target, tt)
        completed += 1

        if result.success:
            await ingestor.ingest_result(result, user_id)
            freshness.mark_collected(module.name, target_type, target)
            results_summary.append({"module": module.name, "status": "success", "entities": len(result.entities)})
        else:
            results_summary.append({"module": module.name, "status": "failed", "error": result.error})

        task.update_state(state="PROGRESS", meta={
            "total": total,
            "completed": completed,
            "current_module": module.name,
        })

    _publish_progress(task.request.id, {
        "state": "COMPLETED",
        "total": total,
        "completed": completed,
        "current_module": "",
    })

    freshness.close()
    await close_driver()

    return {
        "target": target,
        "target_type": target_type,
        "modules_total": total,
        "modules_completed": completed,
        "results": results_summary,
    }


@celery_app.task(bind=True, name="clusterspider.workers.scan_tasks.run_single_module")
def run_single_module(self, module_name: str, target: str, target_type: str, user_id: str):
    return asyncio.run(_run_single_module_async(module_name, target, target_type, user_id))


async def _run_single_module_async(module_name: str, target: str, target_type: str, user_id: str):
    registry = ModuleRegistry()
    for module_cls in ALL_MODULES:
        m = module_cls()
        if m.name == module_name:
            registry.register(m)
            break

    module = registry.get_module(module_name)
    if not module:
        return {"error": f"Module {module_name} not found"}

    tt = TargetType(target_type)
    engine = ExecutionEngine(registry)
    result = await engine.run_module(module, target, tt)

    if result.success:
        driver = await get_driver()
        ingestor = GraphIngestor(driver)
        await ingestor.ingest_result(result, user_id)
        await close_driver()

    return result.to_dict()
