# -*- coding: utf-8 -*-
"""
post_init_hook — runs after a fresh install of alba_loans.
The same logic lives in migrations/19.0.1.1.0/post-migrate.py for upgrades.

Why this is necessary:
  Odoo 19 convert.py wraps every <record> tag in try/except during upgrade
  mode.  When `ir.actions.act_window` is created with res_model pointing to a
  *new* TransientModel (one that didn't exist in the previous version), the
  string-based _check_model constraint raises an exception that is silently
  swallowed, and no ir.model.data entry is written.  menus.xml then fails with
  "External ID not found".

  The migration / post_init_hook approach runs Python ORM code AFTER all XML
  data files have been processed, so the TransientModels are fully registered
  and the constraint no longer fires.
"""

_MODULE = "alba_loans"

_WIZARD_SPECS = [
    {
        "action_xmlid": "action_alba_report_par_wizard",
        "menu_xmlid": "menu_alba_report_par_pdf",
        "action_name": "PAR Report",
        "menu_name": "PAR Report (PDF)",
        "res_model": "alba.report.par",
        "sequence": 30,
        "group_xmlid": "group_loan_officer",
    },
    {
        "action_xmlid": "action_alba_report_npl_wizard",
        "menu_xmlid": "menu_alba_report_npl_pdf",
        "action_name": "NPL Report",
        "menu_name": "NPL Report (PDF)",
        "res_model": "alba.report.npl",
        "sequence": 40,
        "group_xmlid": "group_loan_officer",
    },
    {
        "action_xmlid": "action_alba_report_pl_wizard",
        "menu_xmlid": "menu_alba_report_pl",
        "action_name": "Profit & Loss Report",
        "menu_name": "Profit & Loss",
        "res_model": "alba.report.pl",
        "sequence": 50,
        "group_xmlid": "group_finance_officer",
    },
    {
        "action_xmlid": "action_alba_report_cashflow_wizard",
        "menu_xmlid": "menu_alba_report_cashflow",
        "action_name": "Cash Flow Statement",
        "menu_name": "Cash Flow Statement",
        "res_model": "alba.report.cashflow",
        "sequence": 60,
        "group_xmlid": "group_finance_officer",
    },
    {
        "action_xmlid": "action_alba_report_balance_sheet_wizard",
        "menu_xmlid": "menu_alba_report_balance_sheet",
        "action_name": "Balance Sheet",
        "menu_name": "Balance Sheet",
        "res_model": "alba.report.balance.sheet",
        "sequence": 70,
        "group_xmlid": "group_finance_officer",
    },
]


def create_report_wizard_actions_and_menus(env):
    """
    Idempotent helper — skips any record that already exists in ir.model.data.
    Safe to call from both post_init_hook (install) and post-migrate (upgrade).
    """
    IrModelData = env["ir.model.data"]
    parent_menu = env.ref(f"{_MODULE}.menu_alba_reports_root")

    for spec in _WIZARD_SPECS:
        # ── action ──────────────────────────────────────────────────────
        existing_action = env.ref(
            f"{_MODULE}.{spec['action_xmlid']}", raise_if_not_found=False
        )
        if existing_action:
            action = existing_action
        else:
            group = env.ref(f"{_MODULE}.{spec['group_xmlid']}")
            action = env["ir.actions.act_window"].create(
                {
                    "name": spec["action_name"],
                    "res_model": spec["res_model"],
                    "view_mode": "form",
                    "target": "new",
                    "groups_id": [(6, 0, group.ids)] if group else False,
                }
            )
            IrModelData.create(
                {
                    "name": spec["action_xmlid"],
                    "module": _MODULE,
                    "model": "ir.actions.act_window",
                    "res_id": action.id,
                    "noupdate": False,
                }
            )

        # ── menu ────────────────────────────────────────────────────────
        existing_menu = env.ref(
            f"{_MODULE}.{spec['menu_xmlid']}", raise_if_not_found=False
        )
        if not existing_menu:
            menu = env["ir.ui.menu"].create(
                {
                    "name": spec["menu_name"],
                    "parent_id": parent_menu.id,
                    "action": f"ir.actions.act_window,{action.id}",
                    "sequence": spec["sequence"],
                }
            )
            IrModelData.create(
                {
                    "name": spec["menu_xmlid"],
                    "module": _MODULE,
                    "model": "ir.ui.menu",
                    "res_id": menu.id,
                    "noupdate": False,
                }
            )


def post_init_hook(env):
    """Called by Odoo after a fresh install of alba_loans."""
    create_report_wizard_actions_and_menus(env)
