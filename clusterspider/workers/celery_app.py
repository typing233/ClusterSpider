from celery import Celery

from clusterspider.config import settings

celery_app = Celery("clusterspider")

celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_routes={
        "clusterspider.workers.scan_tasks.*": {"queue": "scans"},
        "clusterspider.workers.report_tasks.*": {"queue": "reports"},
    },
    worker_concurrency=4,
    task_soft_time_limit=300,
    task_time_limit=360,
    result_expires=3600,
)

celery_app.autodiscover_tasks(["clusterspider.workers"])
