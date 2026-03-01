"""
Accounting Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.views.generic import TemplateView, ListView, DetailView, CreateView
from django.contrib import messages
from decimal import Decimal
from .models import Account, JournalEntry, Budget, FiscalYear


class AccountingDashboardView(LoginRequiredMixin, TemplateView):
    """Accounting dashboard"""
    template_name = 'accounting/dashboard.html'


class AccountListView(LoginRequiredMixin, ListView):
    """List all accounts"""
    model = Account
    template_name = 'accounting/account_list.html'
    context_object_name = 'accounts'
    paginate_by = 50


class AccountDetailView(LoginRequiredMixin, DetailView):
    """Account detail with ledger"""
    model = Account
    template_name = 'accounting/account_detail.html'
    context_object_name = 'account'


class AccountCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Create new account"""
    model = Account
    template_name = 'accounting/account_form.html'
    fields = ['code', 'name', 'account_type', 'parent_account', 'description', 'allow_manual_entries']
    permission_required = 'accounting.add_account'
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class JournalEntryListView(LoginRequiredMixin, ListView):
    """List all journal entries"""
    model = JournalEntry
    template_name = 'accounting/journal_entry_list.html'
    context_object_name = 'entries'
    paginate_by = 25


class JournalEntryDetailView(LoginRequiredMixin, DetailView):
    """Journal entry detail"""
    model = JournalEntry
    template_name = 'accounting/journal_entry_detail.html'
    context_object_name = 'entry'


class JournalEntryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Create new journal entry"""
    model = JournalEntry
    template_name = 'accounting/journal_entry_form.html'
    fields = ['date', 'fiscal_year', 'description', 'reference']
    permission_required = 'accounting.add_journalentry'
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


@login_required
@permission_required('accounting.can_post_journal_entries')
def post_journal_entry(request, pk):
    """Post a journal entry"""
    entry = get_object_or_404(JournalEntry, pk=pk)
    try:
        entry.post(request.user)
        messages.success(request, f'Journal entry {entry.entry_number} posted successfully.')
    except Exception as e:
        messages.error(request, str(e))
    return redirect('accounting:journal_entry_detail', pk=pk)


class TrialBalanceView(LoginRequiredMixin, TemplateView):
    """Trial Balance Report"""
    template_name = 'accounting/trial_balance.html'


class BalanceSheetView(LoginRequiredMixin, TemplateView):
    """Balance Sheet Report"""
    template_name = 'accounting/balance_sheet.html'


class IncomeStatementView(LoginRequiredMixin, TemplateView):
    """Income Statement (P&L) Report"""
    template_name = 'accounting/income_statement.html'


class GeneralLedgerView(LoginRequiredMixin, TemplateView):
    """General Ledger Report"""
    template_name = 'accounting/general_ledger.html'


class BudgetListView(LoginRequiredMixin, ListView):
    """List all budgets"""
    model = Budget
    template_name = 'accounting/budget_list.html'
    context_object_name = 'budgets'


class BudgetDetailView(LoginRequiredMixin, DetailView):
    """Budget detail with variance analysis"""
    model = Budget
    template_name = 'accounting/budget_detail.html'
    context_object_name = 'budget'
