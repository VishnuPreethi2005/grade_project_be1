from django.db import models

class LogSetting(models.Model):
    """Stores the dynamic log rotation backup count."""
    backup_count = models.PositiveIntegerField(default=10)

    def __str__(self):
        return f"Log Settings (Keep {self.backup_count} logs)"

    class Meta:
        verbose_name_plural = "Log Settings" 
