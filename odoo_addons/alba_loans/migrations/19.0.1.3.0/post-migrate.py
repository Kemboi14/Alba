# -*- coding: utf-8 -*-
"""
post-migrate for alba_loans 19.0.1.3.0

1. Ensures the Director group implies group_loan_officer (group chain fix).
2. Force-recreates the 5 financial-report wizard actions and menus, adding
   ALL relevant groups so Directors and Admins can see every report.

Why Python and not XML for the act_window records:
  Odoo 19 convert.py silently drops ir.actions.act_window records whose
  res_model is a TransientModel during upgrade mode. Post-migrate bypasses this.
"""
from odoo import api, SUPERUSER_ID

_MODULE = "alba_loans"

_WIZARD_SPECS = [
    {
        "action_xmlid": "action_alba_report_par_wizard",
        "menu_xmlid":   "menu_alba_report_par_pdf",
        "action_name":  "PAR Report",
        "menu_name":    "PAR Report (PDF)",
        "res_model":    "alba.report.par",
        "sequence":     30,
        "group_xmlids": ["group_loan_officer", "group_operations_manager", "group_director"],
    },
    {
        "action_xmlid": "action_alba_report_npl_wizard",
        "menu_xmlid":   "menu_alba_report_npl_pdf",
        "action_name":  "NPL Report",
        "menu_name":    "NPL Report (PDF)",
        "res_model":    "alba.report.npl",
        "sequence":     40,
        "group_xmlids": ["group_loan_officer", "group_operations_manager", "group_director"],
    },
    {
        "action_xmlid": "action_alba_report_pl_wizard",
        "menu_xmlid":   "menu_alba_report_pl",
        "action_name":  "Profit & Loss Report",
        "menu_name":    "Profit & Loss",
        "res_model":    "alba.report.pl",
        "sequence":     50,
        "group_xmlids": ["group_finance_officer", "group_finance_admin", "group_director"],
    },
    {
        "action_xmlid": "action_alba_report_cashflow_wizard",
        "menu_xmlid":   "menu_alba_report_cashflow",
        "action_name":  "Cash Flow Statement",
        "menu_name":    "Cash Flow Statement",
        "res_model":    "alba.report.cashflow",
        "sequence":     60,
        "group_xmlids": ["group_finance_officer", "group_finance_admin", "group_director"],
    },
    {
        "action_xmlid": "action_alba_report_balance_sheet_wizard",
        "menu_xmlid":   "menu_alba_report_balance_sheet",
        "action_name":  "Balance Sheet",
        "menu_name":    "Balance Sheet",
        "res_model":    "alba.report.balance.sheet",
        "sequence":     70,
        "group_xmlids": ["group_finance_officer", "group_finance_admin", "group_director"],
    },
]


def _purge_imd(env, module, name):
    """Remove the ir.model.data entry only (does NOT unlink the pointed record)."""
    env["ir.model.data"].search([
        ("module", "=", module),
        ("name", "=", name),
    ]).unlink()


def _set_imd(env, module, name, model, res_id):
    """Create or update an ir.model.data binding."""
    existing = env["ir.model.data"].search([
        ("module", "=", module),
        ("name", "=", name),
    ])
    if existing:
        existing.write({"res_id": res_id, "model": model})
    else:
        env["ir.model.data"].create({
            "name": name,
            "module": module,
            "model": model,
            "res_id": res_id,
            "noupdate": False,
        })


def _ensure_director_implies_loan_officer(env):
    """
    Ensure group_director implies group_loan_officer.
    security_groups.xml sets this via implied_ids eval, but may not have
    taken effect if the previous upgrade was partial. Apply it in Python too.
    """
    director = env.ref(f"{_MODULE}.group_director", raise_if_not_found=False)
    loan_officer = env.ref(f"{_MODULE}.group_loan_officer", raise_if_not_found=False)
    if director and loan_officer:
        if loan_officer not in director.implied_ids:
            director.write({"implied_ids": [(4, loan_officer.id)]})


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Step 1: Fix group chain
    _ensure_director_implies_loan_officer(env)

    # Step 2: Force-recreate all 5 report wizard actions and menus
    parent_menu = env.ref(f"{_MODULE}.menu_alba_reports_root")

    for spec in _WIZARD_SPECS:
        # Purge any existing stale ir.model.data entries
        _purge_imd(env, _MODULE, spec["action_xmlid"])
        _purge_imd(env, _MODULE, spec["menu_xmlid"])

        # Also unlink any orphaned menus with this name under the reports parent
        env["ir.ui.menu"].search([
            ("name", "=", spec["menu_name"]),
            ("parent_id", "=", parent_menu.id),
        ]).unlink()

        # Create fresh act_window action
        group_ids = []
        for gxml in spec.get("group_xmlids", []):
            g = env.ref(f"{_MODULE}.{gxml}", raise_if_not_found=False)
            if g:
                group_ids.append(g.id)
        action = env["ir.actions.act_window"].create({
            "name": spec["action_name"],
            "res_model": spec["res_model"],
            "view_mode": "form",
            "target": "new",
            "groups_id": [(6, 0, group_ids)] if group_ids else False,
        })
        _set_imd(env, _MODULE, spec["action_xmlid"], "ir.actions.act_window", action.id)

        # Create fresh menu
        menu = env["ir.ui.menu"].create({
            "name": spec["menu_name"],
            "parent_id": parent_menu.id,
            "action": f"ir.actions.act_window,{action.id}",
            "sequence": spec["sequence"],
        })
        _set_imd(env, _MODULE, spec["menu_xmlid"], "ir.ui.menu", menu.id)
