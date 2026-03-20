from django.contrib import admin
from .models import LogSetting
from django.contrib.admin.models import LogEntry
# ---------------------- LogSetting Admin ---------------------- 
@admin.register(LogSetting) 
class LogSettingAdmin(admin.ModelAdmin): 
    """ """ 
    list_display = ['id', 'backup_count'] 
    list_editable = ['backup_count'] 
 
 
# ---------------------- LogEntry (History) Admin ---------------------- 
@admin.register(LogEntry) 
class LogEntryAdmin(admin.ModelAdmin): 
    """ """ 
    list_display = ['action_time', 'user', 'content_type', 'object_repr', 
'action_flag', 'change_message'] 
    list_filter = ['action_flag', 'user'] 
    search_fields = ['object_repr', 'change_message'] 