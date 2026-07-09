# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.reference_utils import safe_investment_reference


class AlbaInterestPayoutWizard(models.TransientModel):
    _name = "alba.interest.payout.wizard"
    _description = "Interest Payout Wizard"

    # ── Investment ────────────────────────────────────────────────────────────
    investment_id = fields.Many2one(
        "alba.investment",
        string="Investment",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(related="investment_id.currency_id", readonly=True)
    investor_id = fields.Many2one(related="investment_id.investor_id", readonly=True)
    wht_rate = fields.Float(related="investment_id.wht_rate", readonly=True)

    # ── Payout Mode ───────────────────────────────────────────────────────────
    payout_mode = fields.Selection(
        selection=[
            ("all", "Pay All Outstanding Accruals"),
            ("select", "Select Specific Months"),
            ("partial", "Custom Partial Amount"),
        ],
        string="Payout Mode",
        default="all",
        required=True,
    )

    # ── Accrual Selection (for 'select' mode) ─────────────────────────────────
    selected_accrual_ids = fields.Many2many(
        "alba.interest.accrual",
        "alba_interest_payout_wizard_accrual_rel",
        "wizard_id",
        "accrual_id",
        string="Accruals to Pay",
        domain="[('investment_id', '=', investment_id), ('state', '=', 'posted')]",
        help="Select one or more monthly accruals to pay in full.",
    )

    # ── Custom Amount (for 'partial' mode) ────────────────────────────────────
    custom_gross_amount = fields.Monetary(
        string="Amount to Pay (Gross)",
        currency_field="currency_id",
        help="Enter any amount up to the total outstanding interest. "
             "Accrual records will NOT be marked paid; only a partial payout is recorded.",
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    total_outstanding = fields.Monetary(
        string="Total Outstanding Interest",
        currency_field="currency_id",
        compute="_compute_payout_amounts",
        help="Total gross interest currently in Interest Payable (not yet paid out).",
    )
    gross_interest = fields.Monetary(
        string="Gross Interest to Pay",
        currency_field="currency_id",
        compute="_compute_payout_amounts",
    )
    wht_amount = fields.Monetary(
        string="Withholding Tax (WHT)",
        currency_field="currency_id",
        compute="_compute_payout_amounts",
    )
    net_interest_payable = fields.Monetary(
        string="Net to Pay to Investor",
        currency_field="currency_id",
        compute="_compute_payout_amounts",
    )

    # ── Payment ───────────────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    payout_date = fields.Date(
        string="Payout Date",
        required=True,
        default=fields.Date.context_today,
    )
    notes = fields.Text(string="Notes")
    memo = fields.Char(
        string="Payment Memo",
        compute="_compute_memo",
        store=True,
        readonly=True,
    )

    # =========================================================================
    # Compute
    # =========================================================================

    @api.depends("investment_id")
    def _compute_memo(self):
        for wiz in self:
            if wiz.investment_id:
                wiz.memo = "Interest Payout — %s" % safe_investment_reference(wiz.investment_id)
            else:
                wiz.memo = False

    @api.depends(
        "payout_mode",
        "selected_accrual_ids",
        "custom_gross_amount",
        "investment_id",
        "investment_id.total_interest_outstanding",
        "investment_id.wht_rate",
    )
    def _compute_payout_amounts(self):
        for wiz in self:
            outstanding = wiz.investment_id.total_interest_outstanding or 0.0

            if wiz.payout_mode == "all":
                gross = outstanding
            elif wiz.payout_mode == "select":
                gross = sum(
                    wiz.selected_accrual_ids.filtered(
                        lambda a: a.state == "posted"
                    ).mapped("interest_amount")
                )
            else:  # partial
                gross = min(wiz.custom_gross_amount or 0.0, outstanding)

            wht = round(gross * ((wiz.wht_rate or 0.0) / 100.0), 2)
            wiz.total_outstanding = outstanding
            wiz.gross_interest = gross
            wiz.wht_amount = wht
            wiz.net_interest_payable = gross - wht

    @api.onchange("payout_mode", "investment_id")
    def _onchange_payout_mode(self):
        if self.payout_mode == "select":
            posted = self.investment_id.accrual_ids.filtered(
                lambda a: a.state == "posted"
            )
            self.selected_accrual_ids = [(6, 0, posted.ids)]
        else:
            self.selected_accrual_ids = False

    # =========================================================================
    # Confirm
    # =========================================================================

    def action_confirm_payout(self):
        self.ensure_one()
        investment = self.investment_id

        # ── Validate gross amount ──────────────────────────────────────────────
        if self.gross_interest <= 0:
            raise UserError(_(
                "Payout amount is zero. Please select accruals or enter a custom amount."
            ))
        outstanding = investment.total_interest_outstanding
        if self.gross_interest > outstanding + 0.01:  # 0.01 rounding tolerance
            raise UserError(_(
                "Payout amount (%(pay).2f) exceeds total outstanding interest (%(out).2f). "
                "You cannot pay more than what has been accrued.",
                pay=self.gross_interest,
                out=outstanding,
            ))

        # ── Validate accounts ──────────────────────────────────────────────────
        if not investment.account_interest_payable_id:
            raise UserError(_(
                "Please configure the Interest Payable Account on investment '%s'."
            ) % investment.investment_number)

        gross = self.gross_interest
        wht = self.wht_amount
        net = self.net_interest_payable

        if net <= 0:
            raise UserError(_(
                "Net payout is zero or negative. Please check the WHT rate."
            ))

        company = investment.company_id or self.env.company
        comp_currency = company.currency_id
        inv_currency = investment.currency_id

        # ── 1. Outbound payment — net interest to investor ─────────────────────
        # DR Interest Payable [net]   CR Bank [net]
        payment_vals = {
            "date": self.payout_date,
            "amount": net,
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": investment.investor_id.partner_id.id,
            "journal_id": self.journal_id.id,
            "currency_id": inv_currency.id,
            "memo": self.memo or ("Interest Payout — %s" % safe_investment_reference(investment)),
            "destination_account_id": investment.account_interest_payable_id.id,
        }
        payment = self.env["account.payment"].create(payment_vals)
        payment.action_post()

        # ── 2. WHT clearing entry (if WHT > 0) ────────────────────────────────
        # DR Interest Payable [wht]   CR WHT Payable [wht]
        wht_move = False
        if wht > 0:
            if not investment.account_wht_payable_id:
                raise UserError(_(
                    "WHT is configured but no WHT Payable Account is set on '%s'."
                ) % investment.investment_number)
            if not investment.journal_id:
                raise UserError(_(
                    "Please configure the Accrual Journal on investment '%s'."
                ) % investment.investment_number)

            wht_co = inv_currency._convert(wht, comp_currency, company, self.payout_date)
            wht_move = self.env["account.move"].create({
                "date": self.payout_date,
                "journal_id": investment.journal_id.id,
                "ref": "IPAY-WHT/%s/%s" % (
                    safe_investment_reference(investment),
                    self.payout_date.strftime("%Y%m"),
                ),
                "move_type": "entry",
                "currency_id": inv_currency.id,
                "line_ids": [
                    (0, 0, {
                        "name": "WHT on interest — %s" % safe_investment_reference(investment),
                        "account_id": investment.account_interest_payable_id.id,
                        "debit": wht_co,
                        "credit": 0.0,
                        "amount_currency": wht,
                        "currency_id": inv_currency.id,
                        "partner_id": investment.investor_id.partner_id.id,
                    }),
                    (0, 0, {
                        "name": "WHT Payable — %s" % safe_investment_reference(investment),
                        "account_id": investment.account_wht_payable_id.id,
                        "debit": 0.0,
                        "credit": wht_co,
                        "amount_currency": -wht,
                        "currency_id": inv_currency.id,
                        "partner_id": investment.investor_id.partner_id.id,
                    }),
                ],
            })
            wht_move.action_post()

        # ── 3. Determine accruals to mark as 'paid' ────────────────────────────
        # Only full-month payouts mark accruals as paid.
        # Partial payouts leave accruals as 'posted'.
        accruals_to_mark_paid = self.env["alba.interest.accrual"]
        if self.payout_mode == "all":
            accruals_to_mark_paid = investment.accrual_ids.filtered(
                lambda a: a.state == "posted"
            )
        elif self.payout_mode == "select":
            accruals_to_mark_paid = self.selected_accrual_ids.filtered(
                lambda a: a.state == "posted"
            )
        # partial mode: no accruals marked paid

        # ── 4. Create payout record ────────────────────────────────────────────
        payout = self.env["alba.interest.payout"].create({
            "investment_id": investment.id,
            "payout_date": self.payout_date,
            "gross_interest": gross,
            "wht_amount": wht,
            "net_amount": net,
            "payment_id": payment.id,
            "wht_move_id": wht_move.id if wht_move else False,
            "accrual_ids": [(6, 0, accruals_to_mark_paid.ids)],
            "state": "posted",
            "notes": self.notes or "",
        })

        # ── 5. Mark accruals as paid (full-payment modes only) ─────────────────
        if accruals_to_mark_paid:
            accruals_to_mark_paid.write({
                "state": "paid",
                "interest_payout_id": payout.id,
            })

        # ── 6. Invalidate subsequent posted accruals ───────────────────────────
        # After a payout, the opening balance for all future accruals changes
        # (paid interest is no longer compounding). Delete any posted accruals
        # that come AFTER the last paid accrual so the backfill recreates them
        # with the correct opening balance derived from current_value.
        if accruals_to_mark_paid:
            last_paid_period_end = max(accruals_to_mark_paid.mapped("period_end"))
            subsequent_posted = investment.accrual_ids.filtered(
                lambda a: a.state == "posted" and a.period_start > last_paid_period_end
            )
            if subsequent_posted:
                # Reverse and delete the journal entries first
                for accrual in subsequent_posted:
                    if accrual.move_id and accrual.move_id.state == "posted":
                        accrual.move_id.button_cancel()
                        accrual.move_id.unlink()
                subsequent_posted.unlink()

        # ── 7. Chatter ─────────────────────────────────────────────────────────
        mode_label = dict(self._fields["payout_mode"].selection).get(self.payout_mode, "")
        investment.message_post(
            body=_(
                "Interest payout <b>%(ref)s</b> (%(mode)s) posted: "
                "Gross <b>%(sym)s %(gross).2f</b>, "
                "WHT <b>%(sym)s %(wht).2f</b>, "
                "Net paid <b>%(sym)s %(net).2f</b>. "
                "Payment: <b>%(payment)s</b>.",
                ref=payout.name,
                mode=mode_label,
                sym=inv_currency.symbol,
                gross=gross,
                wht=wht,
                net=net,
                payment=payment.name,
            )
        )

        return {"type": "ir.actions.act_window_close"}
