from django.contrib import admin
from .models import Employee, PayrollRun, PayrollItem, LeaveType, LeaveApplication

admin.site.register(Employee)
admin.site.register(PayrollRun)
admin.site.register(PayrollItem)
admin.site.register(LeaveType)
admin.site.register(LeaveApplication)
