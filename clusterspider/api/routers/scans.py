import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import redis

from clusterspider.auth.models import User
from clusterspider.api.dependencies import get_current_user
from clusterspider.config import settings
from clusterspider.workers.scan_tasks import run_scan

router = APIRouter()


class ScanCreateRequest(BaseModel):
    target: str
    target_type: str = "domain"
    module_names: list[str] | None = None


class ScanResponse(BaseModel):
    task_id: str
    target: str
    target_type: str
    status: str


@router.post("", response_model=ScanResponse, status_code=202)
async def create_scan(data: ScanCreateRequest, user: User = Depends(get_current_user)):
    valid_types = ["domain", "ip", "email", "username"]
    if data.target_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"target_type must be one of {valid_types}")

    result = run_scan.delay(
        target=data.target,
        target_type=data.target_type,
        user_id=user.id,
        module_names=data.module_names,
    )

    return ScanResponse(
        task_id=result.id,
        target=data.target,
        target_type=data.target_type,
        status="PENDING",
    )


@router.get("/{task_id}")
async def get_scan(task_id: str, user: User = Depends(get_current_user)):
    from celery.result import AsyncResult
    result = AsyncResult(task_id, app=run_scan.app)

    response = {
        "task_id": task_id,
        "status": result.status,
        "result": None,
    }

    if result.status == "PROGRESS":
        response["progress"] = result.info
    elif result.status == "SUCCESS":
        response["result"] = result.result
    elif result.status == "FAILURE":
        response["error"] = str(result.result)

    return response


@router.get("/{task_id}/stream")
async def scan_progress_stream(task_id: str, user: User = Depends(get_current_user)):
    async def event_generator():
        r = redis.from_url(settings.redis_url)
        pubsub = r.pubsub()
        pubsub.subscribe(f"scan_progress:{task_id}")

        try:
            while True:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"

                    parsed = json.loads(data)
                    if parsed.get("state") in ("COMPLETED", "FAILED"):
                        break
                else:
                    yield f": heartbeat\n\n"
                    await asyncio.sleep(1)
        finally:
            pubsub.unsubscribe()
            pubsub.close()
            r.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.delete("/{task_id}")
async def cancel_scan(task_id: str, user: User = Depends(get_current_user)):
    from celery.result import AsyncResult
    result = AsyncResult(task_id, app=run_scan.app)
    result.revoke(terminate=True)
    return {"status": "cancelled", "task_id": task_id}
