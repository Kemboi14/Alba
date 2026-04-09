# -*- coding: utf-8 -*-
"""
post-migrate for alba_loans 19.0.1.2.0

Force-recreates the 5 financial-report wizard ir.actions.act_window records
and their ir.ui.menu entries.

Why Python and not XML:
  Odoo 19 convert.py wraps every <record> tag in try/except during upgrade
  mode.  ir.actions.act_window records whose res_model is a TransientModel
  are silently dropped because the string-based _check_model constraint fires
  before the model is considered "registered" by the XML data loader.  Running
  this code in post-migrate bypasses that constraint entirely.

Why force-recreate (not idempotent):
  A previous broken upgrade attempt may have corrupted or deleted the
  ir.model.data entries for these actions, leaving dangling or missing records.
  We delete any existing records and create fresh ones to guarantee a clean state.
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
        "group_xmlid":  "group_loan_officer",
    },
    {
        "action_xmlid": "action_alba_report_npl_wizard",
        "menu_xmlid":   "menu_alba_report_npl_pdf",
        "action_name":  "NPL Report",
        "menu_name":    "NPL Report (PDF)",
        "res_model":    "alba.report.npl",
        "sequence":     40,
        "group_xmlid":  "group_loan_officer",
    },
    {
        "action_xmlid": "action_alba_report_pl_wizard",
        "menu_xmlid":   "menu_alba_report_pl",
        "action_name":  "Profit & Loss Report",
        "menu_name":    "Profit & Loss",
        "res_model":    "alba.report.pl",
        "sequence":     50,
        "group_xmlid":  "group_finance_officer",
    },
    {
        "action_xmlid": "action_alba_report_cashflow_wizard",
        "menu_xmlid":   "menu_alba_report_cashflow",
        "action_name":  "Cash Flow Statement",
        "menu_name":    "Cash Flow Statement",
        "res_model":    "alba.report.cashflow",
        "sequence":     60,
        "group_xmlid":  "group_finance_officer",
    },
    {
        "action_xmlid": "action_alba_report_balance_sheet_wizard",
        "menu_xmlid":   "menu_alba_report_balance_sheet",
        "action_name":  "Balance Sheet",
        "menu_name":    "Balance Sheet",
        "res_model":    "alba.report.balance.sheet",
        "sequence":     70,
        "group_xmlid":  "group_finance_officer",
    },
]


def _purge_imd(env, module, name):
    """Remove ir.model.data entry (does NOT unlink the pointed-to record)."""
    env["ir.model.data"].search([
        ("module", "=", module),
        ("name", "=", name),
    ]).unlink()


def _set_imd(env, module, name, model, res_id):
    """Create or update an ir.model.data entry."""
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


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    parent_menu = env.ref(f"{_MODULE}.menu_alba_reports_root")

    for spec in _WIZARD_SPECS:
        # ── Clean up any stale ir.model.data entries first ──────────────────
        _purge_imd(env, _MODULE, spec["action_xmlid"])
        _purge_imd(env, _MODULE, spec["menu_xmlid"])

        # ── Recreate the act_window action ───────────────────────────────────
        action = env["ir.actions.act_window"].create({
            "name": spec["action_name"],
            "res_model": spec["res_model"],
            "view_mode": "form",
            "target": "new",
        })
        _set_imd(env, _MODULE, spec["action_xmlid"], "ir.actions.act_window", action.id)

        # ── Recreate the menu item ───────────────────────────────────────────
        group = env.ref(f"{_MODULE}.{spec['group_xmlid']}")
        menu = env["ir.ui.menu"].create({
            "name": spec["menu_name"],
            "parent_id": parent_menu.id,
            "action": f"ir.actions.act_window,{action.id}",
            "sequence": spec["sequence"],
            "groups_id": [(4, group.id)],
        })
        _set_imd(env, _MODULE, spec["menu_xmlid"], "ir.ui.menu", menu.id)
