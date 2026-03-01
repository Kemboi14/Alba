"""
Accounting Admin Configuration
"""
from django.contrib import admin
from .models import (
    FiscalYear, AccountType, Account, JournalEntry, JournalEntryLine,
    Budget, BankAccount, BankReconciliation
)


@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'is_active', 'is_closed']
    list_filter = ['is_active', 'is_closed']
    search_fields = ['name']


@admin.register(AccountType)
class AccountTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'normal_balance', 'description']


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'account_type', 'parent_account', 'is_active']
    list_filter = ['account_type', 'is_active', 'is_system_account']
    search_fields = ['code', 'name']
    ordering = ['code']


class JournalEntryLineInline(admin.TabularInline):
    model = JournalEntryLine
    extra = 2
    fields = ['account', 'description', 'debit_amount', 'credit_amount']


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ['entry_number', 'date', 'description', 'status', 'get_total_debit', 'created_by']
    list_filter = ['status', 'date', 'fiscal_year', 'source_module']
    search_fields = ['entry_number', 'description', 'reference']
    readonly_fields = ['entry_number', 'posted_at', 'posted_by']
    inlines = [JournalEntryLineInline]
    
    def get_total_debit(self, obj):
        return f"{obj.get_total_debit():,.2f}"
    get_total_debit.short_description = 'Total Debit'


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ['name', 'department', 'fiscal_year', 'budgeted_amount', 'status']
    list_filter = ['status', 'fiscal_year', 'department']
    search_fields = ['name', 'department']


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['account_name', 'account_number', 'bank_name', 'currency', 'is_active']
    list_filter = ['is_active', 'bank_name']
    search_fields = ['account_name', 'account_number', 'bank_name']


@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ['bank_account', 'reconciliation_date', 'statement_balance', 'book_balance', 'status']
    list_filter = ['status', 'reconciliation_date']
    search_fields = ['bank_account__account_number']
