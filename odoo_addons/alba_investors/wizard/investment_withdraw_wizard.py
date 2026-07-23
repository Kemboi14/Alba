# -*- coding: utf-8 -*-
from datetime import date

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..models.reference_utils import safe_investment_reference
from ..models.accrual_backfill import _period_start_from_accrual_date


class InvestmentWithdrawWizard(models.TransientModel):
    _name = "alba.investment.withdraw.wizard"
    _description = "Investment Withdrawal Wizard"

    investment_id = fields.Many2one("alba.investment", string="Investment", required=True)
    currency_id = fields.Many2one(related="investment_id.currency_id")

    # ── Payment parameters ────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    payment_date = fields.Date(
        string="Withdrawal Date",
        required=True,
        default=fields.Date.context_today,
    )
    earliest_withdrawal_date = fields.Date(related="investment_id.earliest_withdrawal_date")
    days_to_withdrawal = fields.Integer(related="investment_id.days_to_withdrawal")

    # ── Premature withdrawal detection ────────────────────────────────────────
    is_premature = fields.Boolean(
        string="Premature Withdrawal",
        compute="_compute_premature",
        help="True when the investment is being withdrawn before its maturity date.",
    )

    # ── Payout components (read-only display) ─────────────────────────────────
    principal_amount = fields.Monetary(
        string="Principal Amount",
        related="investment_id.principal_amount",
        readonly=True,
    )
    total_topup_amount = fields.Monetary(
        string="Total Top-Ups",
        related="investment_id.total_topup_amount",
        readonly=True,
    )
    wht_rate = fields.Float(
        string="WHT Rate (%)",
        related="investment_id.wht_rate",
        readonly=True,
    )

    # ── Computed payout breakdown ─────────────────────────────────────────────
    forfeited_interest = fields.Monetary(
        string="Forfeited Interest (Current Month)",
        currency_field="currency_id",
        compute="_compute_premature",
        help="Gross interest for the current billing cycle that the investor forfeits "
             "on premature withdrawal (Rule 4a).",
    )
    eligible_gross_interest = fields.Monetary(
        string="Eligible Gross Interest (Prior Months)",
        currency_field="currency_id",
        compute="_compute_premature",
        help="Total gross interest from completed prior months only.",
    )
    wht_amount = fields.Monetary(
        string="Withholding Tax (WHT)",
        currency_field="currency_id",
        compute="_compute_premature",
    )
    net_interest_payable = fields.Monetary(
        string="Net Interest Payable",
        currency_field="currency_id",
        compute="_compute_premature",
    )
    amount = fields.Monetary(
        string="Net Payout Amount",
        currency_field="currency_id",
        compute="_compute_premature",
        help="Principal + top-ups + net eligible interest (WHT deducted).",
    )

    # =========================================================================
    # Compute
    # =========================================================================

    @api.depends("investment_id", "investment_id.state", "investment_id.maturity_date")
    def _compute_premature(self):
        today = fields.Date.context_today(self)
        for wiz in self:
            inv = wiz.investment_id
            if not inv:
                wiz.is_premature = False
                wiz.forfeited_interest = 0.0
                wiz.eligible_gross_interest = 0.0
                wiz.wht_amount = 0.0
                wiz.net_interest_payable = 0.0
                wiz.amount = 0.0
                continue

            # ── Is this a premature (pre-maturity) withdrawal? ────────────────
            premature = (
                inv.state == "active"
                and inv.investment_type == "fixed_term"
                and inv.maturity_date
                and inv.maturity_date > today
            )
            wiz.is_premature = premature

            # ── Identify current-cycle accruals that must be forfeited ─────────
            # Current cycle = period whose period_end falls in the current month:
            # period_start = 29th of previous month, period_end = 28th of current month
            if premature:
                current_period_start = _period_start_from_accrual_date(
                    date(today.year, today.month, 28)
                )
                posted_accruals = inv.accrual_ids.filtered(lambda a: a.state == "posted")
                current_cycle = posted_accruals.filtered(
                    lambda a: a.period_end >= current_period_start
                )
                prior_cycles = posted_accruals - current_cycle

                forfeited = sum(current_cycle.mapped("interest_amount"))
                eligible_gross = sum(prior_cycles.mapped("interest_amount"))
            else:
                # Matured or open-ended — all outstanding interest is eligible
                forfeited = 0.0
                eligible_gross = inv.total_interest_outstanding

            wht = round(eligible_gross * ((inv.wht_rate or 0.0) / 100.0), 2)
            net_interest = eligible_gross - wht

            wiz.forfeited_interest = forfeited
            wiz.eligible_gross_interest = eligible_gross
            wiz.wht_amount = wht
            wiz.net_interest_payable = net_interest
            wiz.amount = inv.principal_amount + (inv.total_topup_amount or 0.0) + net_interest

    # =========================================================================
    # Confirm
    # =========================================================================

    def action_confirm_withdrawal(self):
        self.ensure_one()
        investment = self.investment_id
        if investment.state not in ("active", "matured"):
            raise UserError(_("Only active or matured investments can be withdrawn."))

        today = fields.Date.context_today(self)
        if (
            investment.state == "active"
            and investment.investment_type == "fixed_term"
            and investment.maturity_date
            and investment.maturity_date > today
        ):
            if not investment.withdrawal_notice_date:
                raise UserError(_(
                    "Please request early withdrawal notice before confirming withdrawal."
                ))
            if investment.earliest_withdrawal_date and investment.earliest_withdrawal_date > today:
                raise UserError(
                    _("This early withdrawal can only be paid out from %s.")
                    % investment.earliest_withdrawal_date
                )

        if not investment.account_investment_liability_id:
            raise UserError(_(
                "Please configure the Investment Liability Account on the investment."
            ))

        # ── Rule 4: Premature withdrawal — reverse current-month accruals ─────
        # The investor forfeits any interest accrued in the current billing
        # cycle.  Reverse those accrual records and their journal entries so
        # the accounting is clean before the payout is processed.
        if self.is_premature and self.forfeited_interest > 0:
            current_period_start = _period_start_from_accrual_date(
                date(today.year, today.month, 28)
            )
            current_accruals = investment.accrual_ids.filtered(
                lambda a: a.state == "posted" and a.period_end >= current_period_start
            )
            for accrual in current_accruals:
                # Set reversal reason then call action_reverse()
                accrual.write({
                    "reversal_reason": _(
                        "Forfeited on premature withdrawal %s — Rule 4."
                    ) % self.payment_date,
                })
                accrual.action_reverse()

        # ── Create the outbound payment (principal + top-ups + net interest) ──
        payment_vals = {
            "date": self.payment_date,
            "amount": self.amount,
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": investment.investor_id.partner_id.id,
            "journal_id": self.journal_id.id,
            "currency_id": self.currency_id.id,
            "memo": "Withdrawal - %s%s" % (
                safe_investment_reference(investment),
                _(" (Premature)") if self.is_premature else "",
            ),
            "destination_account_id": investment.account_investment_liability_id.id,
        }
        payment = self.env["account.payment"].create(payment_vals)
        payment.action_post()

        # ── Adjustment journal entry: clear Interest Payable & WHT ───────────
        # Only for the interest that was actually earned (eligible prior months).
        if self.eligible_gross_interest > 0:
            if not investment.account_interest_payable_id:
                raise UserError(_(
                    "Please configure the Interest Payable Account on the investment."
                ))
            if not investment.account_wht_payable_id:
                raise UserError(_(
                    "Please configure the WHT Payable Account on the investment."
                ))
            if not investment.journal_id:
                raise UserError(_(
                    "Please configure the Accrual Journal on the investment."
                ))

            # Determine how much WHT and Interest Payable has already been posted
            # in accrual moves for the ELIGIBLE (prior-cycle) accruals only.
            eligible_posted = investment.accrual_ids.filtered(
                lambda a: a.state == "posted"
            )
            accrued_wht_already_posted = 0.0
            accrued_interest_payable_posted = 0.0

            for accrual in eligible_posted:
                if accrual.move_id:
                    for line in accrual.move_id.line_ids:
                        if line.account_id == investment.account_wht_payable_id:
                            accrued_wht_already_posted += abs(line.amount_currency)
                        elif line.account_id == investment.account_interest_payable_id:
                            accrued_interest_payable_posted += abs(line.amount_currency)

            interest_payable_to_clear = accrued_interest_payable_posted
            wht_to_post = max(0.0, self.wht_amount - accrued_wht_already_posted)
            net_interest_to_offset = interest_payable_to_clear - wht_to_post

            company = investment.company_id or self.env.company
            comp_currency = company.currency_id
            inv_currency = investment.currency_id

            interest_payable_company = inv_currency._convert(
                interest_payable_to_clear, comp_currency, company, self.payment_date
            )
            wht_company = inv_currency._convert(
                wht_to_post, comp_currency, company, self.payment_date
            )
            net_interest_company = interest_payable_company - wht_company

            line_ids = []

            # 1. DR Interest Payable Account (clear it)
            if interest_payable_to_clear > 0:
                line_ids.append((0, 0, {
                    "name": "Clear Interest Payable - %s" % safe_investment_reference(investment),
                    "account_id": investment.account_interest_payable_id.id,
                    "debit": interest_payable_company,
                    "credit": 0.0,
                    "amount_currency": interest_payable_to_clear,
                    "currency_id": inv_currency.id,
                    "partner_id": investment.partner_id.id,
                }))

            # 2. CR Investment Liability Account (net interest portion)
            if net_interest_to_offset > 0:
                line_ids.append((0, 0, {
                    "name": "Investment Liability Interest Offset - %s" % safe_investment_reference(investment),
                    "account_id": investment.account_investment_liability_id.id,
                    "debit": 0.0,
                    "credit": net_interest_company,
                    "amount_currency": -net_interest_to_offset,
                    "currency_id": inv_currency.id,
                    "partner_id": investment.partner_id.id,
                }))

            # 3. CR WHT Payable Account
            if wht_to_post > 0:
                line_ids.append((0, 0, {
                    "name": "Withholding Tax Payable - %s" % safe_investment_reference(investment),
                    "account_id": investment.account_wht_payable_id.id,
                    "debit": 0.0,
                    "credit": wht_company,
                    "amount_currency": -wht_to_post,
                    "currency_id": inv_currency.id,
                    "partner_id": investment.partner_id.id,
                }))

            if line_ids:
                move_vals = {
                    "date": self.payment_date,
                    "journal_id": investment.journal_id.id,
                    "ref": "WHT/ADJ/%s" % safe_investment_reference(investment),
                    "move_type": "entry",
                    "currency_id": inv_currency.id,
                    "line_ids": line_ids,
                }
                move = self.env["account.move"].create(move_vals)
                move.action_post()

        # ── Update investment state ───────────────────────────────────────────
        investment.write({
            "state": "withdrawn",
            "withdrawal_payment_id": payment.id,
        })

        body = _(
            "Investment withdrawn via payment <b>%(payment)s</b> for %(sym)s %(amount).2f.",
            payment=payment.name,
            sym=self.currency_id.symbol,
            amount=self.amount,
        )
        if self.is_premature and self.forfeited_interest > 0:
            body += _(
                "<br/><b>Premature withdrawal:</b> %(sym)s %(forfeited).2f interest forfeited "
                "(current billing cycle, Rule 4).",
                sym=self.currency_id.symbol,
                forfeited=self.forfeited_interest,
            )
        investment.message_post(body=body)

        return {"type": "ir.actions.act_window_close"}
