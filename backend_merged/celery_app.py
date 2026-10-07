from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    "approval_system",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=["tasks.escalation", "tasks.notifications"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Beat Schedule - runs check_and_escalate every hour
celery_app.conf.beat_schedule = {
    "check-escalations-every-hour": {
        "task": "tasks.escalation.check_and_escalate",
        "schedule": crontab(),  # Every hour
    },
}