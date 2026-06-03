from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from clusterspider.auth.models import User
from clusterspider.api.dependencies import get_current_user
from clusterspider.workers.report_tasks import generate_report

router = APIRouter()


class ReportCreateRequest(BaseModel):
    target: str
    target_type: str = "domain"
    format: str = "html"


class ReportResponse(BaseModel):
    task_id: str
    status: str


@router.post("", response_model=ReportResponse, status_code=202)
async def create_report(data: ReportCreateRequest, user: User = Depends(get_current_user)):
    if data.format not in ("html", "pdf"):
        raise HTTPException(status_code=400, detail="format must be 'html' or 'pdf'")

    result = generate_report.delay(
        user_id=user.id,
        target=data.target,
        target_type=data.target_type,
        format=data.format,
    )

    return ReportResponse(task_id=result.id, status="PENDING")


@router.get("/{task_id}")
async def get_report_status(task_id: str, user: User = Depends(get_current_user)):
    from celery.result import AsyncResult
    result = AsyncResult(task_id, app=generate_report.app)

    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.status == "SUCCESS" else None,
    }


@router.get("/{task_id}/download")
async def download_report(task_id: str, user: User = Depends(get_current_user)):
    from celery.result import AsyncResult
    result = AsyncResult(task_id, app=generate_report.app)

    if result.status != "SUCCESS":
        raise HTTPException(status_code=404, detail="Report not ready")

    report_info = result.result
    file_path = report_info.get("path", "")
    format_type = report_info.get("format", "html")

    media_type = "application/pdf" if format_type == "pdf" else "text/html"
    filename = file_path.split("/")[-1] if "/" in file_path else file_path

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )
