from __future__ import annotations

from celery import Celery

from api.config import get_settings


def _broker_url() -> str:
    return get_settings().celery_broker_url


def _result_backend() -> str:
    return get_settings().celery_result_backend


celery_app = Celery(
    "agno_aios",
    broker=_broker_url(),
    backend=_result_backend(),
)

celery_app.conf.update(
    task_track_started=True,
    timezone="UTC",
    beat_schedule={},
)
