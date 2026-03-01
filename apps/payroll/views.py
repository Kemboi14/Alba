from django.views.generic import TemplateView

class PayrollDashboardView(TemplateView):
    template_name = 'payroll/dashboard.html'
