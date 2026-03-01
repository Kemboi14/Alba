"""
URL Configuration for Alba Capital ERP System
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Core (authentication, dashboard)
    path('', include('apps.core.urls', namespace='core')),
    
    # Accounting Module
    path('accounting/', include('apps.accounting.urls', namespace='accounting')),
    
    # Loans Module
    path('loans/', include('apps.loans.urls', namespace='loans')),
    
    # Customer Portal
    path('portal/', include('apps.loans.portal_urls', namespace='portal')),
    
    # M-Pesa API Callbacks
    path('api/payments/', include('apps.loans.api_urls', namespace='payments_api')),
    
    # Investors Module
    path('investors/', include('apps.investors.urls', namespace='investors')),
    
    # Payroll Module
    path('payroll/', include('apps.payroll.urls', namespace='payroll')),
    
    # CRM Module
    path('crm/', include('apps.crm.urls', namespace='crm')),
    
    # Assets Module
    path('assets/', include('apps.assets.urls', namespace='assets')),
    
    # Reporting Module
    path('reports/', include('apps.reporting.urls', namespace='reporting')),
    
    # API endpoints
    path('api/', include('config.api_urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Django Debug Toolbar
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass

# Customize admin site
admin.site.site_header = "Alba Capital ERP Administration"
admin.site.site_title = "Alba Capital ERP"
admin.site.index_title = "Welcome to Alba Capital ERP System"
