# -*- coding: utf-8 -*-
{
    "name": "SMS",
    "version": "19.0.1.1.0",
    "category": "Technical",
    "summary": "Outbound SMS notifications and bulk campaigns for loans, collections, repayments and investor communications",
    "description": """
Bulk SMS Module
================

Adds a fully configurable outbound SMS layer on top of the Alba Capital loan
and investor management modules.  All SMS activity is purely additive — the
core ``alba_loans`` and ``alba_investors`` modules are never modified.

Key Features
------------

Provider Management
  * Multi-provider support: Africa's Talking, Twilio, Vonage/Nexmo, and any
    generic HTTP-based SMS gateway.
  * All credentials stored in ``alba.sms.provider`` and configurable entirely
    from the Odoo UI — no code changes required to onboard a new provider.
  * Generic HTTP adapter with configurable auth method (header, query param,
    Basic Auth) and arbitrary extra_params JSON for provider-specific fields.
  * Kenyan phone number normalisation reused from ``mpesa_config.py``.

Template Engine
  * ``alba.sms.template`` — reusable message templates using simple
    ``{placeholder}`` substitution (no Jinja — safe for non-technical admins).
  * Built-in placeholders: ``{customer_name}``, ``{loan_number}``, ``{amount}``,
    ``{due_date}``, ``{days_overdue}``, ``{outstanding_balance}``,
    ``{maturity_date}``, ``{company_name}``, ``{investor_name}``,
    ``{investment_number}``, ``{interest_amount}``.
  * Default templates seeded at install for all major events.

Automated Hooks (zero changes to core modules)
  * Loan overdue reminders — hooks into ``cron_send_overdue_alerts()``
  * Loan maturity reminders — hooks into ``cron_send_maturity_reminders()``
  * Payment confirmation — hooks into ``alba.loan.repayment.action_post()``
  * Loan disbursement notice — hooks into the disburse wizard
  * Application approved / rejected — hooks into ``action_approve()`` /
    ``action_reject()``
  * Collection stage reminder — **uses the existing ``sms_template`` field**
    on ``alba.loan.collection.stage`` that was already wired but never called
  * Investor interest credited — hooks into ``alba.interest.accrual.action_post()``

Bulk SMS Campaigns
  * ``alba.sms.batch`` — target audiences: all active customers, overdue loans
    by PAR bucket, NPL loans, maturing loans, all investors, or any custom
    Odoo domain filter.
  * Batch lines generated per recipient with per-line message preview.
  * Send immediately or schedule for off-peak hours.
  * Background cron processes scheduled batches in pages of 100.
  * Real-time sent / failed / delivered counters on the batch dashboard.

Delivery Receipts (DLR)
  * Public webhook endpoint at ``/alba/sms/dlr`` updates log status to
    ``delivered`` when the provider sends a callback.

Audit Trail
  * ``alba.sms.log`` — mirrors ``alba.webhook.log`` pattern; records every
    outbound SMS with provider message ID, status, error, and link back to
    the source Odoo record.

Security Groups
  * ``group_sms_user``    — view SMS logs and batch results (read-only)
  * ``group_sms_officer`` — send ad-hoc SMS, create and run batch campaigns
  * ``group_sms_admin``   — configure providers, manage templates, view API
                             credentials, full log access
    """,
    "author": "Alba Capital",
    "website": "https://www.albacapital.co.ke",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "alba_loans",
        "alba_investors",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        # ── Security — always first ──────────────────────────────────────────
        "security/security.xml",
        "security/ir.model.access.csv",
        # ── Default templates and system parameters ──────────────────────────
        "data/sms_template_data.xml",
        # ── Scheduled actions (crons) ────────────────────────────────────────
        "data/cron_data.xml",
        # ── Provider seed data (noupdate) ────────────────────────────────────
        "data/sms_provider_onfon.xml",
        # ── Window actions (must load before views that reference them) ───────
        "views/actions.xml",
        # ── Model views ──────────────────────────────────────────────────────
        "views/sms_provider_views.xml",
        "views/sms_template_views.xml",
        "views/sms_log_views.xml",
        "views/sms_batch_views.xml",
        # ── Menus (after all actions are defined) ────────────────────────────
        "views/menus.xml",
        # ── Wizards ──────────────────────────────────────────────────────────
        "wizard/bulk_sms_wizard_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "application": True,
    "sequence": 40,
    "web_icon": "alba_sms,static/description/icon.png",
}
