import os
from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

# Set the default Django settings module for Celery
# Use deployment_settings if WEBSITE_SITE_NAME is set (Azure deployment)
# Otherwise use local settings
settings_module = (
    "promptRightProd.deployment_settings"
    if "WEBSITE_SITE_NAME" in os.environ
    else "promptRightProd.settings"
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

app = Celery("promptRightProd")

# Load Celery settings from Django settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

# Configure Celery to use Django's logging configuration
@setup_logging.connect
def config_loggers(*args, **kwargs):
    from logging.config import dictConfig
    from django.conf import settings
    dictConfig(settings.LOGGING)

# Auto-discover tasks from all installed Django apps
app.autodiscover_tasks()

# Celery Beat - Schedule periodic tasks
app.conf.beat_schedule = {
    "assign_answers_every_3_days": {
        "task": "grade.tasks.assign_answers_task",
        # Every 3 days at 12:02 AM
        "schedule": crontab(minute=0, hour=0, day_of_month="*/3"),
    },
    "reassign_expired_answers_every_3_days": {
        "task": "grade.tasks.reassign_expired_answers_task",
        # Every 3 days at 12:02 AM
        "schedule": crontab(minute=0, hour=0, day_of_month="*/3"),
    },
}

# Optional: Add debugging/logging


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")


# Adjust worker settings for Windows
app.conf.update(
    worker_concurrency=1,  # Use only one worker process for debugging
    worker_pool="solo",  # Use solo pool for debugging on Windows
)
