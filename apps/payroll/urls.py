from django.urls import path
from django.views.generic import TemplateView

app_name = 'payroll'

urlpatterns = [
    path('', TemplateView.as_view(template_name='payroll/dashboard.html'), name='dashboard'),
]
