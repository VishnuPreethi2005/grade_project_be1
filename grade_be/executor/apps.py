import logging
import os
from logging.handlers import TimedRotatingFileHandler
from django.apps import AppConfig
from django.conf import settings


class ExecutorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'executor'

    # def ready(self):
    #     # Avoid DB access during app loading (especially in tests/migrations)
    #     default_retention = 7
    #     retention_days = default_retention

    #     try:
    #         from .models import SiteSettings
    #         setting = SiteSettings.objects.first()
    #         if setting and setting.log_retention_days:
    #             retention_days = setting.log_retention_days
    #     except Exception:
    #         pass  # Safe fallback to default_retention

    #     log_dir = os.path.join(settings.BASE_DIR, 'logs')
    #     os.makedirs(log_dir, exist_ok=True)
    #     log_path = os.path.join(log_dir, 'django_ai_generation.log')

    #     handler = TimedRotatingFileHandler(
    #         filename=log_path,
    #         when='midnight',
    #         interval=1,
    #         backupCount=retention_days,
    #         encoding='utf-8',
    #         delay=True  # <- fixes file lock on Windows
    #     )
    #     handler.setLevel(logging.DEBUG)
    #     handler.setFormatter(logging.Formatter(
    #         '{asctime} [{levelname}] {name}: {message}', style='{'
    #     ))

    #     logger = logging.getLogger('executor')
    #     logger.handlers.clear()  # remove old handlers
    #     logger.addHandler(handler)
    #     logger.setLevel(logging.DEBUG)
    #     logger.propagate = False
