"""
Investors Views
"""
from django.views.generic import TemplateView, ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import InvestmentAccount


class InvestorDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'investors/dashboard.html'


class InvestmentAccountListView(LoginRequiredMixin, ListView):
    model = InvestmentAccount
    template_name = 'investors/account_list.html'
    context_object_name = 'accounts'


class InvestmentAccountDetailView(LoginRequiredMixin, DetailView):
    model = InvestmentAccount
    template_name = 'investors/account_detail.html'
    context_object_name = 'account'
