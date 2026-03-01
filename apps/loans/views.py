"""
Loans Views
"""
from django.views.generic import TemplateView, ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import LoanApplication, Loan, Customer


class LoanDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'loans/dashboard.html'


class LoanApplicationListView(LoginRequiredMixin, ListView):
    model = LoanApplication
    template_name = 'loans/application_list.html'
    context_object_name = 'applications'
    paginate_by = 25


class LoanApplicationDetailView(LoginRequiredMixin, DetailView):
    model = LoanApplication
    template_name = 'loans/application_detail.html'
    context_object_name = 'application'


class LoanListView(LoginRequiredMixin, ListView):
    model = Loan
    template_name = 'loans/loan_list.html'
    context_object_name = 'loans'
    paginate_by = 25


class LoanDetailView(LoginRequiredMixin, DetailView):
    model = Loan
    template_name = 'loans/loan_detail.html'
    context_object_name = 'loan'


class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = 'loans/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 25


class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = 'loans/customer_detail.html'
    context_object_name = 'customer'
