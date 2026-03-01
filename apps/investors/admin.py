"""
Investors Admin
"""
from django.contrib import admin
from .models import Investor, InvestmentAccount, InvestmentTransaction, MonthlyInterestCalculation


@admin.register(Investor)
class InvestorAdmin(admin.ModelAdmin):
    list_display = ['investor_number', 'name', 'email', 'phone_number', 'is_active']
    search_fields = ['investor_number', 'name', 'email']


@admin.register(InvestmentAccount)
class InvestmentAccountAdmin(admin.ModelAdmin):
    list_display = ['account_number', 'investor', 'current_balance', 'monthly_interest_rate', 'is_active']
    list_filter = ['is_active']


@admin.register(InvestmentTransaction)
class InvestmentTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_number', 'account', 'transaction_type', 'amount', 'transaction_date']
    list_filter = ['transaction_type', 'transaction_date']
