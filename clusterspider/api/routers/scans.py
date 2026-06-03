import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import redis

from clusterspider.auth.models import User
from clusterspider.auth.jwt import verify_token
from clusterspider.api.dependencies import get_current_user, get_user_repo
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


class ScanHistoryItem(BaseModel):
    id: str
    task_id: str
    target: str
    target_type: str
    status: str
    modules_total: int
    modules_completed: int
    created_at: str
    finished_at: str | None


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

    # Persist scan record in user's history
    repo = get_user_repo()
    repo.create_scan_record(
        user_id=user.id,
        task_id=result.id,
        target=data.target,
        target_type=data.target_type,
        module_names=data.module_names,
    )

    return ScanResponse(
        task_id=result.id,
        target=data.target,
        target_type=data.target_type,
        status="PENDING",
    )


@router.get("", response_model=list[ScanHistoryItem])
async def list_scans(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
):
    repo = get_user_repo()
    rows = repo.get_scan_history(user.id, limit=limit, offset=offset)
    return [
        ScanHistoryItem(
            id=r["id"],
            task_id=r["task_id"],
            target=r["target"],
            target_type=r["target_type"],
            status=r["status"],
            modules_total=r.get("modules_total") or 0,
            modules_completed=r.get("modules_completed") or 0,
            created_at=r["created_at"],
            finished_at=r.get("finished_at"),
        )
        for r in rows
    ]


@router.get("/{task_id}")
async def get_scan(task_id: str, user: User = Depends(get_current_user)):
    # First check local DB for this user's scan
    repo = get_user_repo()
    scan_record = repo.get_scan_by_task_id(task_id, user.id)
    if not scan_record:
        raise HTTPException(status_code=404, detail="Scan not found")

    from celery.result import AsyncResult
    result = AsyncResult(task_id, app=run_scan.app)

    response = {
        "task_id": task_id,
        "target": scan_record["target"],
        "target_type": scan_record["target_type"],
        "status": result.status if result.status != "PENDING" else scan_record["status"],
        "created_at": scan_record["created_at"],
        "finished_at": scan_record.get("finished_at"),
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
async def scan_progress_stream(
    task_id: str,
    token: str = Query(..., description="JWT access token for SSE authentication"),
):
    """SSE endpoint. Uses query param ?token=<jwt> because EventSource cannot set headers."""
    payload = verify_token(token, expected_type="access")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    repo = get_user_repo()
    scan_record = repo.get_scan_by_task_id(task_id, user_id)
    if not scan_record:
        raise HTTPException(status_code=404, detail="Scan not found for this user")

    async def event_generator():
        r = redis.from_url(settings.redis_url)
        pubsub = r.pubsub()
        pubsub.subscribe(f"scan_progress:{task_id}")

        try:
            timeout_counter = 0
            while timeout_counter < 300:  # max 5 min
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"

                    parsed = json.loads(data)
                    if parsed.get("state") in ("COMPLETED", "FAILED"):
                        break
                    timeout_counter = 0
                else:
                    yield f": heartbeat\n\n"
                    timeout_counter += 1
                    await asyncio.sleep(1)
        finally:
            pubsub.unsubscribe()
            pubsub.close()
            r.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.delete("/{task_id}")
async def cancel_scan(task_id: str, user: User = Depends(get_current_user)):
    repo = get_user_repo()
    scan_record = repo.get_scan_by_task_id(task_id, user.id)
    if not scan_record:
        raise HTTPException(status_code=404, detail="Scan not found")

    from celery.result import AsyncResult
    result = AsyncResult(task_id, app=run_scan.app)
    result.revoke(terminate=True)

    repo.update_scan_status(task_id, "CANCELLED")

    return {"status": "cancelled", "task_id": task_id}
