"""
Investors URLs
"""
from django.urls import path
from . import views

app_name = 'investors'

urlpatterns = [
    path('', views.InvestorDashboardView.as_view(), name='dashboard'),
    path('accounts/', views.InvestmentAccountListView.as_view(), name='account_list'),
    path('accounts/<int:pk>/', views.InvestmentAccountDetailView.as_view(), name='account_detail'),
]
