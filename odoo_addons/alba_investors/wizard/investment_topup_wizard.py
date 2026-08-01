# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaInvestmentTopupWizard(models.TransientModel):
    _name = "alba.investment.topup.wizard"
    _description = "Investment Top-Up Wizard"

    investment_id = fields.Many2one(
        "alba.investment",
        string="Investment",
        required=True,
        readonly=True,
    )
    investor_id = fields.Many2one(related="investment_id.investor_id", readonly=True)
    currency_id = fields.Many2one(related="investment_id.currency_id", readonly=True)
    current_principal = fields.Monetary(
        related="investment_id.principal_amount",
        string="Original Principal",
        readonly=True,
    )
    total_topup_amount = fields.Monetary(
        related="investment_id.total_topup_amount",
        string="Previous Top-Ups",
        readonly=True,
    )
    effective_principal = fields.Monetary(
        string="Current Effective Principal",
        currency_field="currency_id",
        compute="_compute_effective_principal",
    )

    amount = fields.Monetary(
        string="Top-Up Amount",
        currency_field="currency_id",
        required=True,
        help="Additional amount the investor is depositing today.",
    )
    date = fields.Date(
        string="Receipt Date",
        required=True,
        default=fields.Date.context_today,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Receipt Journal",
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    notes = fields.Text(string="Notes")

    # ── Preview ───────────────────────────────────────────────────────────────
    new_effective_principal = fields.Monetary(
        string="New Effective Principal (after top-up)",
        currency_field="currency_id",
        compute="_compute_effective_principal",
    )

    @api.depends("investment_id", "amount")
    def _compute_effective_principal(self):
        for wiz in self:
            base = (wiz.investment_id.principal_amount or 0.0) + (
                wiz.investment_id.total_topup_amount or 0.0
            )
            wiz.effective_principal = base
            wiz.new_effective_principal = base + (wiz.amount or 0.0)

    def action_confirm(self):
        self.ensure_one()
        investment = self.investment_id

        if investment.state != "active":
            raise UserError(
                _("Top-ups can only be made on active investments.")
            )
        if not self.amount or self.amount <= 0:
            raise UserError(_("Top-Up Amount must be greater than zero."))
        if not investment.account_investment_liability_id:
            raise UserError(
                _("Please configure the Investment Liability Account on investment '%s'.")
                % investment.investment_number
            )

        # Create the top-up record and immediately post it
        topup = self.env["alba.investment.topup"].create({
            "investment_id": investment.id,
            "amount": self.amount,
            "date": self.date,
            "journal_id": self.journal_id.id,
            "notes": self.notes or "",
        })
        topup.action_post()

        # ── Invalidate subsequent posted accruals ──────────────────────────────
        # A top-up increases the investment's compounding base from self.date
        # onward. Any posted accruals whose period starts AFTER the top-up date
        # were computed on a base that is too low; delete them so the next
        # backfill (action_backfill_missing_accruals) regenerates them using
        # the correct running balance that includes this top-up.
        # We only touch 'posted' accruals — 'paid' and 'reversed' are immutable.
        subsequent_posted = investment.accrual_ids.filtered(
            lambda a: a.state == "posted" and a.period_end >= self.date
        )
        if subsequent_posted:
            for accrual in subsequent_posted:
                if accrual.move_id and accrual.move_id.state == "posted":
                    accrual.move_id.button_cancel()
                    accrual.move_id.unlink()
            subsequent_posted.unlink()

        return {"type": "ir.actions.act_window_close"}
