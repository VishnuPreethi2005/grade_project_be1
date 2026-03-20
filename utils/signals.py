from django.core.signals import request_started 
from django.dispatch import receiver 
from .models import LogSetting 
import logging.config 
from django.conf import settings 
 
@receiver(request_started) 
def configure_logging(sender, **kwargs): 
    try: 
        setting = LogSetting.objects.first() 
        if setting: 
            settings.LOGGING['handlers']['rotating_file']['backupCount'] = setting.backup_count 
            logging.config.dictConfig(settings.LOGGING) 
    except Exception as e: 
        print(f"[WARNING] Failed to configure dynamic logging: {e}") 