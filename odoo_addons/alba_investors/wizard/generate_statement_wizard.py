# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AlbaGenerateStatementWizard(models.TransientModel):
    _name = "alba.generate.statement.wizard"
    _description = "Alba Capital — Generate Investment Statements Wizard"

    # ── Period ────────────────────────────────────────────────────────────────
    period_start = fields.Date(
        string="Period Start",
        required=True,
        help="First day of the statement period.",
    )
    period_end = fields.Date(
        string="Period End",
        required=True,
        help="Last day of the statement period.",
    )
    statement_date = fields.Date(
        string="Statement Date",
        required=True,
        default=fields.Date.today,
        help="Date printed on the generated statements.",
    )

    # ── Scope ─────────────────────────────────────────────────────────────────
    generate_for = fields.Selection(
        selection=[
            ("all_active", "All Active Investments"),
            ("selected_investors", "Selected Investors Only"),
            ("selected_investments", "Selected Investments Only"),
        ],
        string="Generate For",
        required=True,
        default="all_active",
    )
    investor_ids = fields.Many2many(
        "alba.investor",
        "generate_statement_wizard_investor_rel",
        "wizard_id",
        "investor_id",
        string="Investors",
        domain="[('state', '=', 'active')]",
        help="Leave empty to generate for all active investors.",
    )
    investment_ids = fields.Many2many(
        "alba.investment",
        "generate_statement_wizard_investment_rel",
        "wizard_id",
        "investment_id",
        string="Investments",
        domain="[('state', '=', 'active')]",
        help="Select specific investment accounts to generate statements for.",
    )

    # ── Options ───────────────────────────────────────────────────────────────
    skip_existing = fields.Boolean(
        string="Skip Existing Statements",
        default=True,
        help="If ticked, skip investments that already have a statement "
        "for the selected period.",
    )
    auto_confirm = fields.Boolean(
        string="Auto-Confirm Statements",
        default=True,
        help="Automatically confirm (lock) each statement after generation.",
    )
    auto_send = fields.Boolean(
        string="Auto-Send to Investors",
        default=False,
        help="Automatically email each statement to the investor after generation. "
        "Requires an email template to be configured.",
    )

    # ── Summary (informational) ───────────────────────────────────────────────
    preview_count = fields.Integer(
        string="Investments to Process",
        compute="_compute_preview_count",
        help="Number of investment accounts that will be processed with the current settings.",
    )

    # =========================================================================
    # Defaults
    # =========================================================================

    @api.model
    def default_get(self, fields_list):
        """Pre-fill period_start / period_end to the previous 29th-to-28th accrual cycle."""
        res = super().default_get(fields_list)
        today = fields.Date.today()
        month = today.month
        year = today.year
        # 29th-to-28th rule: period_end = 28th of current month,
        # period_start = 29th of previous month (timedelta handles leap years)
        prev_month = month - 1 or 12
        prev_year = year if month > 1 else year - 1
        res["period_end"] = date(year, month, 28)
        res["period_start"] = date(prev_year, prev_month, 28) + timedelta(days=1)
        return res

    # =========================================================================
    # Computed methods
    # =========================================================================

    @api.depends(
        "generate_for",
        "investor_ids",
        "investment_ids",
        "skip_existing",
        "period_start",
        "period_end",
    )
    def _compute_preview_count(self):
        for rec in self:
            investments = rec._get_target_investments()
            if rec.skip_existing and rec.period_start and rec.period_end:
                existing_inv_ids = (
                    self.env["alba.investment.statement"]
                    .search(
                        [
                            ("period_start", "=", rec.period_start),
                            ("period_end", "=", rec.period_end),
                        ]
                    )
                    .mapped("investment_id.id")
                )
                investments = investments.filtered(
                    lambda i: i.id not in existing_inv_ids
                )
            rec.preview_count = len(investments)

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains("period_start", "period_end")
    def _check_period_dates(self):
        for rec in self:
            if rec.period_start and rec.period_end:
                if rec.period_end < rec.period_start:
                    raise ValidationError(
                        _("Period end date must be on or after the period start date.")
                    )

    @api.constrains("generate_for", "investor_ids", "investment_ids")
    def _check_scope_selection(self):
        for rec in self:
            if rec.generate_for == "selected_investors" and not rec.investor_ids:
                raise ValidationError(
                    _(
                        "You selected 'Selected Investors Only' but have not "
                        "chosen any investors. Please select at least one investor "
                        "or change the scope to 'All Active Investments'."
                    )
                )
            if rec.generate_for == "selected_investments" and not rec.investment_ids:
                raise ValidationError(
                    _(
                        "You selected 'Selected Investments Only' but have not "
                        "chosen any investments. Please select at least one investment "
                        "or change the scope to 'All Active Investments'."
                    )
                )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _get_target_investments(self):
        """Return the recordset of alba.investment to generate statements for."""
        self.ensure_one()
        Investment = self.env["alba.investment"]

        if self.generate_for == "selected_investments":
            return self.investment_ids.filtered(lambda i: i.state == "active")

        if self.generate_for == "selected_investors":
            if not self.investor_ids:
                return Investment
            return Investment.search(
                [
                    ("investor_id", "in", self.investor_ids.ids),
                    ("state", "=", "active"),
                ]
            )

        # Default: all active investments
        return Investment.search([("state", "=", "active")])

    # =========================================================================
    # Main action
    # =========================================================================

    def action_generate(self):
        """
        Generate investment statements for the selected scope and period.

        Steps for each investment:
        1.  Optionally skip if a statement already exists for the period.
        2.  Collect posted interest accruals within the period.
        3.  Compute opening balance from principal + all prior posted accruals.
        4.  Create alba.investment.statement record.
        5.  Optionally confirm and/or send the statement.

        Returns an ir.actions.act_window pointing at the created statements.
        """
        self.ensure_one()

        if not self.period_start or not self.period_end:
            raise UserError(_("Please set both a Period Start and Period End date."))

        investments = self._get_target_investments()
        if not investments:
            raise UserError(
                _(
                    "No active investments found matching the selected scope. "
                    "Nothing to generate."
                )
            )

        Statement = self.env["alba.investment.statement"]
        Accrual = self.env["alba.interest.accrual"]

        created_statements = Statement.browse()
        skipped = 0
        errors = []

        for inv in investments:
            try:
                # ── Skip if existing ─────────────────────────────────────────
                if self.skip_existing:
                    existing = Statement.search(
                        [
                            ("investment_id", "=", inv.id),
                            ("period_start", "=", self.period_start),
                            ("period_end", "=", self.period_end),
                        ],
                        limit=1,
                    )
                    if existing:
                        skipped += 1
                        continue

                # ── Accruals within period ────────────────────────────────────
                accruals = Accrual.search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("accrual_date", ">=", self.period_start),
                        ("accrual_date", "<=", self.period_end),
                    ]
                )
                total_interest = sum(accruals.mapped("interest_amount"))

                # Top-ups in this period
                topups = self.env["alba.investment.topup"].search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("date", ">=", self.period_start),
                        ("date", "<=", self.period_end),
                    ]
                )
                total_deposits = sum(topups.mapped("amount"))

                # Principal withdrawals (investment payoff) in this period
                total_withdrawals = 0.0
                if inv.state == "withdrawn" and inv.withdrawal_payment_id:
                    pay_date = inv.withdrawal_payment_id.date
                    if pay_date and self.period_start <= pay_date <= self.period_end:
                        total_withdrawals = inv.principal_amount + inv.total_topup_amount

                # Prior elements for opening balance
                prior_topups = self.env["alba.investment.topup"].search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("date", "<", self.period_start),
                    ]
                )
                prior_accruals = Accrual.search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "in", ["posted", "paid"]),
                        ("accrual_date", "<", self.period_start),
                    ]
                )
                prior_payouts = self.env["alba.interest.payout"].search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("payout_date", "<", self.period_start),
                    ]
                )
                prior_withdrawals = 0.0
                if inv.state == "withdrawn" and inv.withdrawal_payment_id:
                    pay_date = inv.withdrawal_payment_id.date
                    if pay_date and pay_date < self.period_start:
                        prior_withdrawals = inv.principal_amount + inv.total_topup_amount

                opening_balance = (
                    inv.principal_amount
                    + sum(prior_topups.mapped("amount"))
                    + sum(prior_accruals.mapped("interest_amount"))
                    - sum(prior_payouts.mapped("gross_interest"))
                    - prior_withdrawals
                )

                # ── Create statement ──────────────────────────────────────────
                stmt_vals = {
                    "investment_id": inv.id,
                    "statement_date": self.statement_date,
                    "period_start": self.period_start,
                    "period_end": self.period_end,
                    "opening_balance": opening_balance,
                    "deposits": total_deposits,
                    "withdrawals": total_withdrawals,
                    "interest_accrued": total_interest,
                    "accrual_ids": [(6, 0, accruals.ids)],
                }
                stmt = Statement.create(stmt_vals)
                created_statements |= stmt


                # ── Auto-confirm ──────────────────────────────────────────────
                if self.auto_confirm:
                    stmt.action_confirm()

                # ── Auto-send ─────────────────────────────────────────────────
                if self.auto_send:
                    stmt.action_send()

            except Exception as exc:
                errors.append(
                    _(
                        "Investment %(number)s: %(error)s",
                        number=inv.investment_number,
                        error=str(exc),
                    )
                )

        # ── Error summary ─────────────────────────────────────────────────────
        if errors:
            import logging

            _logger = logging.getLogger(__name__)
            _logger.warning(
                "alba.generate.statement.wizard: Generation completed with errors:\n%s",
                "\n".join(errors),
            )

        if not created_statements:
            raise UserError(
                _(
                    "No statements were created. "
                    "%(skipped)d investment(s) were skipped (statements already exist). "
                    "%(errors)d error(s) occurred.",
                    skipped=skipped,
                    errors=len(errors),
                )
            )

        # ── Return act_window pointing at generated statements ────────────────
        action = {
            "type": "ir.actions.act_window",
            "name": _("Generated Statements (%d)") % len(created_statements),
            "res_model": "alba.investment.statement",
            "view_mode": "list,form",
            "domain": [("id", "in", created_statements.ids)],
            "target": "current",
        }
        return action
