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
        "action_xmlid": "action_par_report",
        "menu_xmlid": "menu_par_report",
        "action_name": "PAR Report",
        "menu_name": "PAR Report",
        "res_model": "alba.report.par.wizard",
        "sequence": 30,
    },
    {
        "action_xmlid": "action_npl_report",
        "menu_xmlid": "menu_npl_report",
        "action_name": "NPL Report",
        "menu_name": "NPL Report",
        "res_model": "alba.report.npl.wizard",
        "sequence": 40,
    },
    {
        "action_xmlid": "action_pl_report",
        "menu_xmlid": "menu_pl_report",
        "action_name": "Profit & Loss Report",
        "menu_name": "Profit & Loss",
        "res_model": "alba.report.pl.wizard",
        "sequence": 50,
    },
    {
        "action_xmlid": "action_cashflow_report",
        "menu_xmlid": "menu_cashflow_report",
        "action_name": "Cash Flow Statement",
        "menu_name": "Cash Flow Statement",
        "res_model": "alba.report.cashflow.wizard",
        "sequence": 60,
    },
    {
        "action_xmlid": "action_balance_sheet_report",
        "menu_xmlid": "menu_balance_sheet_report",
        "action_name": "Balance Sheet",
        "menu_name": "Balance Sheet",
        "res_model": "alba.report.balance.sheet.wizard",
        "sequence": 70,
    },
]


def create_report_wizard_actions_and_menus(env):
    """
    Idempotent helper — skips any record that already exists in ir.model.data.
    Safe to call from both post_init_hook (install) and post-migrate (upgrade).
    """
    IrModelData = env["ir.model.data"]
    parent_menu = env.ref(f"{_MODULE}.menu_alba_loans_reports")

    for spec in _WIZARD_SPECS:
        # ── action ──────────────────────────────────────────────────────
        existing_action = env.ref(
            f"{_MODULE}.{spec['action_xmlid']}", raise_if_not_found=False
        )
        if existing_action:
            action = existing_action
        else:
            action = env["ir.actions.act_window"].create(
                {
                    "name": spec["action_name"],
                    "res_model": spec["res_model"],
                    "view_mode": "form",
                    "target": "new",
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
