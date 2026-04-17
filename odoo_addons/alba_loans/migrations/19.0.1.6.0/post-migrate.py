# -*- coding: utf-8 -*-
"""
post-migrate for alba_loans 19.0.1.6.0

Force-recreates the 5 PDF financial-report wizard act_window actions and their
menu items under the Reports menu.

Root cause: Odoo 19 convert.py silently drops ir.actions.act_window records
whose res_model is a TransientModel during the upgrade phase.  The
post_init_hook (fresh install) runs the creation code correctly, but on
subsequent upgrades the hook is NOT re-run — only the migration is.

This migration also purges any stale/partial records from the prior attempt
in 19.0.1.2.0 so we get a guaranteed-clean state.
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


def _purge_record(env, module, xml_name):
    """Delete both the ir.model.data entry AND the pointed-to record."""
    imd = env["ir.model.data"].search([
        ("module", "=", module),
        ("name", "=", xml_name),
    ])
    if imd:
        model_name = imd.model
        res_id = imd.res_id
        imd.unlink()
        try:
            record = env[model_name].browse(res_id)
            if record.exists():
                record.unlink()
        except Exception:
            pass


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
        # ── Wipe any stale records from previous (broken) migration ──────────
        _purge_record(env, _MODULE, spec["action_xmlid"])
        _purge_record(env, _MODULE, spec["menu_xmlid"])

        # ── Create fresh act_window action ───────────────────────────────────
        group = env.ref(f"{_MODULE}.{spec['group_xmlid']}")
        action = env["ir.actions.act_window"].create({
            "name": spec["action_name"],
            "res_model": spec["res_model"],
            "view_mode": "form",
            "target": "new",
            "group_ids": [(6, 0, group.ids)] if group else False,
        })
        _set_imd(env, _MODULE, spec["action_xmlid"], "ir.actions.act_window", action.id)

        # ── Create fresh menu item ───────────────────────────────────────────
        menu = env["ir.ui.menu"].create({
            "name": spec["menu_name"],
            "parent_id": parent_menu.id,
            "action": f"ir.actions.act_window,{action.id}",
            "sequence": spec["sequence"],
        })
        _set_imd(env, _MODULE, spec["menu_xmlid"], "ir.ui.menu", menu.id)
