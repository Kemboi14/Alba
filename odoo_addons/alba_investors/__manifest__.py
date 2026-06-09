# -*- coding: utf-8 -*-
{
    "name": "Investors",
    "version": "19.0.1.0.2",
    "category": "Finance",
    "summary": "Investor profiles, investment accounts, compound interest accrual and monthly statement generation",
    "description": """
Investor Management
===================
Manages the full investor lifecycle:

* Investor profiles linked to Odoo contacts (res.partner)
* KYC management with verification workflow
* Investment accounts (fixed-term and open-ended)
* Monthly compound interest accrual via scheduled cron job
* Automated accounting journal entries for interest accrual
* Monthly investor statements auto-generated and emailed
* Portfolio value tracking per investor
* Integration with Alba Loans module for fund utilisation reporting
    """,
    "author": "Alba Capital",
    "website": "https://www.albacapital.co.ke",
    "license": "LGPL-3",
    "depends": [
        "base",
        "account",
        "mail",
        "contacts",
        "base_setup",
        "alba_loans",
    ],
    "data": [
        # Security — always first
        "security/security.xml",
        "security/ir.model.access.csv",
        # Master data / sequences / crons
        "data/sequence_data.xml",
        "data/cron_data.xml",
        "data/mail_template_data.xml",
        "data/system_parameters.xml",
        "data/investment_product_data.xml",
        # Reports
        "report/investor_reports.xml",
        "report/investment_statement_report.xml",
        "report/investor_statement_report_template.xml",
        # Wizards
        "wizard/generate_statement_wizard_views.xml",
        "wizard/investor_statement_preview_wizard_views.xml",
        "wizard/investment_withdraw_wizard_views.xml",
        "wizard/accrual_reverse_wizard_views.xml",
        # Views
        "views/investor_views.xml",
        "views/investment_statement_views.xml",
        "views/investment_product_views.xml",
        "views/investment_views.xml",
        "views/interest_accrual_views.xml",
        "views/currency_sync_views.xml",
        "views/investor_dashboard_views.xml",
        # Menus last
        "views/menus.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "application": True,
    "pre_init_hook": "pre_init_hook",
    "sequence": 20,
    "web_icon": "alba_investors,static/description/icon.png",
    "assets": {
        "web.assets_backend": [
            "alba_investors/static/lib/chart.js/chart.umd.min.js",
            "alba_investors/static/src/js/investor_dashboard.js",
            "alba_investors/static/src/xml/investor_dashboard.xml",
        ],
    },
}
