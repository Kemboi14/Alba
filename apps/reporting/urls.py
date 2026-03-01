from django.urls import path
from django.views.generic import TemplateView

app_name = 'reporting'

urlpatterns = [
    path('', TemplateView.as_view(template_name='reporting/dashboard.html'), name='dashboard'),
]
