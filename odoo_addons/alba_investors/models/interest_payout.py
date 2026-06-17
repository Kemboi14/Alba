# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaInterestPayout(models.Model):
    _name = "alba.interest.payout"
    _description = "Alba Capital Interest Payout"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "payout_date desc, id desc"

    # ── Reference ─────────────────────────────────────────────────────────────
    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=False,  # IMPORT-FIX: make writable for import matching
        default=lambda self: _("New"),
        index=True,
        tracking=True,
    )

    # ── Investment Link ───────────────────────────────────────────────────────
    investment_id = fields.Many2one(
        "alba.investment",
        string="Investment",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )
    investor_id = fields.Many2one(
        "alba.investor",
        string="Investor",
        related="investment_id.investor_id",
        store=True,
        readonly=False,  # IMPORT-FIX: make writable for import mapping
        inverse="_inverse_readonly_import",
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        related="investment_id.investor_id.partner_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="investment_id.company_id",
        store=True,
        readonly=True,
    )

    # ── Currency ──────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="investment_id.currency_id",
        store=True,
        readonly=True,
    )

    # ── Dates ─────────────────────────────────────────────────────────────────
    payout_date = fields.Date(
        string="Payout Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )

    # ── Amounts ───────────────────────────────────────────────────────────────
    gross_interest = fields.Monetary(
        string="Gross Interest",
        currency_field="currency_id",
        tracking=True,
        help="Total gross interest paid out (sum of all cleared accruals).",
    )
    wht_amount = fields.Monetary(
        string="Withholding Tax (WHT)",
        currency_field="currency_id",
        tracking=True,
    )
    net_amount = fields.Monetary(
        string="Net Paid to Investor",
        currency_field="currency_id",
        tracking=True,
        help="Gross interest minus withholding tax — actual cash paid.",
    )

    # ── Accounting Links ──────────────────────────────────────────────────────
    payment_id = fields.Many2one(
        "account.payment",
        string="Payment (Net Interest)",
        readonly=True,
        copy=False,
        help="Outbound payment: DR Interest Payable / CR Bank.",
    )
    wht_move_id = fields.Many2one(
        "account.move",
        string="WHT Clearing Entry",
        readonly=True,
        copy=False,
        help="Journal entry: DR Interest Payable / CR WHT Payable.",
    )

    # ── Accruals Cleared ──────────────────────────────────────────────────────
    accrual_ids = fields.Many2many(
        "alba.interest.accrual",
        "alba_interest_payout_accrual_rel",
        "payout_id",
        "accrual_id",
        string="Accruals Cleared",
        readonly=True,
        help="The monthly accrual records that were settled by this payout.",
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string="Notes")

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "alba.interest.payout.seq"
                ) or _("New")
        return super().create(vals_list)

    def _inverse_readonly_import(self):
        """No-op inverse for read-only fields to allow import mapping without modifying related records."""
        pass

    # =========================================================================
    # Export / Import helpers
    # =========================================================================

    @api.model
    def _get_default_list_export_fields(self):
        """Fields recommended for CSV export/import of interest payouts."""
        return [
            "name",
            "investment_id/investment_number",
            "investor_id/investor_number",
            "payout_date",
            "gross_interest",
            "wht_amount",
            "net_amount",
            "state",
            "notes",
        ]

    @api.model
    def _name_search(self, name="", domain=None, operator="ilike", limit=100, order=None):
        """Allow resolving by reference (name) or investment number."""
        domain = list(domain or [])
        if name:
            domain = [
                "|",
                ("name", operator, name),
                ("investment_id.investment_number", "=", name),
            ] + domain
        return self._search(domain, limit=limit, order=order)

    # =========================================================================
    # Business Logic
    # =========================================================================

    def action_view_payment(self):
        """Open the linked outbound payment."""
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_("No payment has been linked to this payout yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Payment"),
            "res_model": "account.payment",
            "view_mode": "form",
            "res_id": self.payment_id.id,
        }

    def action_view_wht_entry(self):
        """Open the linked WHT clearing journal entry."""
        self.ensure_one()
        if not self.wht_move_id:
            raise UserError(_("No WHT journal entry has been linked to this payout."))
        return {
            "type": "ir.actions.act_window",
            "name": _("WHT Clearing Entry"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.wht_move_id.id,
        }
