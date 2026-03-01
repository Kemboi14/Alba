"""
Accounting URL Configuration
"""
from django.urls import path
from . import views

app_name = 'accounting'

urlpatterns = [
    # Dashboard
    path('', views.AccountingDashboardView.as_view(), name='dashboard'),
    
    # Chart of Accounts
    path('accounts/', views.AccountListView.as_view(), name='account_list'),
    path('accounts/create/', views.AccountCreateView.as_view(), name='account_create'),
    path('accounts/<int:pk>/', views.AccountDetailView.as_view(), name='account_detail'),
    
    # Journal Entries
    path('journal-entries/', views.JournalEntryListView.as_view(), name='journal_entry_list'),
    path('journal-entries/create/', views.JournalEntryCreateView.as_view(), name='journal_entry_create'),
    path('journal-entries/<int:pk>/', views.JournalEntryDetailView.as_view(), name='journal_entry_detail'),
    path('journal-entries/<int:pk>/post/', views.post_journal_entry, name='journal_entry_post'),
    
    # Reports
    path('reports/trial-balance/', views.TrialBalanceView.as_view(), name='trial_balance'),
    path('reports/balance-sheet/', views.BalanceSheetView.as_view(), name='balance_sheet'),
    path('reports/income-statement/', views.IncomeStatementView.as_view(), name='income_statement'),
    path('reports/general-ledger/', views.GeneralLedgerView.as_view(), name='general_ledger'),
    
    # Budgets
    path('budgets/', views.BudgetListView.as_view(), name='budget_list'),
    path('budgets/<int:pk>/', views.BudgetDetailView.as_view(), name='budget_detail'),
]
