from django.contrib import admin
from .models import SavedReport, ReportSchedule

admin.site.register(SavedReport)
admin.site.register(ReportSchedule)
