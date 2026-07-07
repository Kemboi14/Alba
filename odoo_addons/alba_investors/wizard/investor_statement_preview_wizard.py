# -*- coding: utf-8 -*-
"""
Investor Statement Preview Wizard
===================================
Light-weight wizard launched from the Investor form that lets staff
select a date range and immediately preview / download the PDF statement
for that specific investor.  No need to navigate to the Statements menu.
"""
import calendar
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class InvestorStatementPreviewWizard(models.TransientModel):
    _name = "alba.investor.statement.preview.wizard"
    _description = "Investor Statement Preview"

    # ── Investor ──────────────────────────────────────────────────────────────
    investor_id = fields.Many2one(
        "alba.investor",
        string="Investor",
        required=True,
        readonly=True,
    )
    investor_name = fields.Char(
        string="Investor Name",
        related="investor_id.investor_name",
        readonly=True,
    )
    portfolio_value = fields.Monetary(
        string="Portfolio Value",
        related="investor_id.current_portfolio_value",
        currency_field="currency_id",
        readonly=True,
    )
    active_investments = fields.Integer(
        related="investor_id.active_investment_count",
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="investor_id.currency_id",
        readonly=True,
    )

    # ── Period ────────────────────────────────────────────────────────────────
    period_start = fields.Date(
        string="From",
        required=True,
    )
    period_end = fields.Date(
        string="To",
        required=True,
    )

    # ── Scope ─────────────────────────────────────────────────────────────────
    include_all_investments = fields.Boolean(
        string="All Investments",
        default=True,
        help="Include all investments for this investor. Untick to select specific ones.",
    )
    investment_ids = fields.Many2many(
        "alba.investment",
        "preview_wizard_investment_rel",
        "wizard_id",
        "investment_id",
        string="Investments",
        domain="[('investor_id','=',investor_id),('state','=','active')]",
    )

    # ── Output ────────────────────────────────────────────────────────────────
    output_format = fields.Selection(
        [
            ("pdf", "PDF (Download)"),
            ("save", "Save as Statement Record"),
        ],
        string="Output",
        default="pdf",
        required=True,
    )

    # ── Info summary ──────────────────────────────────────────────────────────
    statement_count = fields.Integer(
        string="Existing Statements",
        compute="_compute_statement_count",
    )

    # =========================================================================
    # Defaults
    # =========================================================================

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        # Pre-fill investor from context
        investor_id = self.env.context.get("default_investor_id") or \
                      self.env.context.get("active_id")
        if investor_id:
            res["investor_id"] = investor_id

        # Pre-fill period to the *previous* calendar month
        today = date.today()
        month = today.month - 1 or 12
        year = today.year if today.month > 1 else today.year - 1
        last_day = calendar.monthrange(year, month)[1]
        res["period_start"] = date(year, month, 1)
        res["period_end"] = date(year, month, last_day)

        return res

    # =========================================================================
    # Computed
    # =========================================================================

    @api.depends("investor_id", "period_start", "period_end")
    def _compute_statement_count(self):
        Statement = self.env["alba.investment.statement"]
        for rec in self:
            if not rec.investor_id or not rec.period_start or not rec.period_end:
                rec.statement_count = 0
                continue
            rec.statement_count = Statement.search_count([
                ("investor_id", "=", rec.investor_id.id),
                ("period_start", "=", rec.period_start),
                ("period_end", "=", rec.period_end),
            ])

    # =========================================================================
    # Main actions
    # =========================================================================

    def action_preview(self):
        """Generate (or retrieve) the statement and render the PDF inline."""
        self.ensure_one()
        self._validate()

        stmt = self._get_or_create_statement()
        report = self.env.ref(
            "alba_investors.action_report_investment_statement",
            raise_if_not_found=False,
        )
        if not report:
            raise UserError(_(
                "Could not find the Investment Statement report. "
                "Please contact your administrator."
            ))

        return report.report_action(stmt)

    def action_view_existing(self):
        """Open all existing statements for this investor/period."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Statements — %s") % self.investor_id.investor_name,
            "res_model": "alba.investment.statement",
            "view_mode": "list,form",
            "domain": [
                ("investor_id", "=", self.investor_id.id),
                ("period_start", "=", self.period_start),
                ("period_end", "=", self.period_end),
            ],
            "target": "current",
        }

    # =========================================================================
    # Helpers
    # =========================================================================

    def _validate(self):
        if self.period_end < self.period_start:
            raise UserError(_("'To' date must be on or after 'From' date."))
        if not self.include_all_investments and not self.investment_ids:
            raise UserError(_(
                "You unchecked 'All Investments' but selected no specific investments. "
                "Please select at least one investment."
            ))

    def _get_target_investments(self):
        """Return the investments to cover."""
        if self.include_all_investments:
            return self.env["alba.investment"].search([
                ("investor_id", "=", self.investor_id.id),
                ("state", "=", "active"),
            ])
        return self.investment_ids.filtered(lambda i: i.state == "active")

    def _get_or_create_statement(self):
        """
        Return an existing confirmed/sent statement for this period if one exists,
        otherwise create a fresh draft one (or save if output_format == 'save').
        """
        Statement = self.env["alba.investment.statement"]
        Accrual = self.env["alba.interest.accrual"]
        investments = self._get_target_investments()

        if not investments:
            raise UserError(_(
                "No active investments found for %s in the selected period."
            ) % self.investor_id.investor_name)

        # For simplicity, generate/return the first matching statement;
        # if the investor has multiple investments, generate one per investment
        # and return all of them for the PDF batch.
        created = Statement.browse()

        for inv in investments:
            existing = Statement.search([
                ("investment_id", "=", inv.id),
                ("period_start", "=", self.period_start),
                ("period_end", "=", self.period_end),
            ], limit=1)

            if existing:
                created |= existing
                continue

            # ── Accruals in the period ────────────────────────────────────────
            accruals = Accrual.search([
                ("investment_id", "=", inv.id),
                ("state", "=", "posted"),
                ("accrual_date", ">=", self.period_start),
                ("accrual_date", "<=", self.period_end),
            ])
            total_interest = sum(accruals.mapped("interest_amount"))

            # ── Top-ups in the period ─────────────────────────────────────────
            topups = self.env["alba.investment.topup"].search([
                ("investment_id", "=", inv.id),
                ("state", "=", "posted"),
                ("date", ">=", self.period_start),
                ("date", "<=", self.period_end),
            ])
            total_deposits = sum(topups.mapped("amount"))

            # ── Opening balance: principal + all prior activity ───────────────
            # Use the shared helper from the mixin so the logic stays in sync.
            report_model = self.env["alba.account.statement.report.mixin"]
            opening_balance = report_model._compute_investment_opening_balance(
                inv, self.period_start
            )

            stmt = Statement.create({
                "investment_id": inv.id,
                "statement_date": fields.Date.today(),
                "period_start": self.period_start,
                "period_end": self.period_end,
                "opening_balance": opening_balance,
                "deposits": total_deposits,
                "interest_accrued": total_interest,
                "accrual_ids": [(6, 0, accruals.ids)],
            })

            if self.output_format == "save":
                stmt.action_confirm()

            created |= stmt

        if not created:
            raise UserError(_("No statements could be generated."))

        return created
