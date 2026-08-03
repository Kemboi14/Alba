# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.accrual_backfill import split_period_for_payout_cutoff
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
        help="Editable memo that will be stored on the payout and used for the payment narration.",
    )

    # =========================================================================
    # Compute
    # =========================================================================

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
            posted_accruals = wiz.investment_id.accrual_ids.filtered(lambda a: a.state == "posted")
            total_accrued = sum(posted_accruals.mapped("interest_amount")) or 0.0
            outstanding = wiz.investment_id.total_interest_outstanding or 0.0

            if wiz.payout_mode == "all":
                gross = sum(
                    (self._get_accrual_cutoff_breakdown(accrual)[0] for accrual in posted_accruals)
                )
            elif wiz.payout_mode == "select":
                gross = sum(
                    self._get_accrual_cutoff_breakdown(accrual)[0]
                    for accrual in wiz.selected_accrual_ids.filtered(lambda a: a.state == "posted")
                )
            else:  # partial
                outstanding = total_accrued
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

    def _get_accrual_cutoff_breakdown(self, accrual):
        payout_date = self.payout_date or fields.Date.today()
        # Prefer the accrual's already-split payable/deferred fields so a partial
        # payout can accurately preserve any outstanding deferred amount.
        if accrual.interest_amount_payable_now or accrual.interest_amount_deferred:
            return accrual.interest_amount_payable_now or 0.0, accrual.interest_amount_deferred or 0.0
        # For completed/posted periods (or periods ending on or before payout date),
        # 100% of the interest amount is payable.
        if accrual.state in ("posted", "paid") or (accrual.period_end and accrual.period_end <= payout_date):
            return accrual.interest_amount or 0.0, 0.0
        return split_period_for_payout_cutoff(
            accrual.period_start,
            accrual.period_end,
            accrual.interest_amount,
        )

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

        # ── 3. Determine accruals to include in this payout ───────────────────
        payout_accruals = self.env["alba.interest.accrual"]
        accrued_candidates = self.env["alba.interest.accrual"]
        if self.payout_mode == "all":
            accrued_candidates = investment.accrual_ids.filtered(lambda a: a.state == "posted")
        elif self.payout_mode == "select":
            accrued_candidates = self.selected_accrual_ids.filtered(lambda a: a.state == "posted")
        else:  # partial/custom payout
            accrued_candidates = investment.accrual_ids.filtered(lambda a: a.state == "posted")

        if self.payout_mode in ("all", "select"):
            for accrual in accrued_candidates:
                payable_now, deferred_amount = self._get_accrual_cutoff_breakdown(accrual)
                if payable_now <= 0:
                    accrual.write({
                        "interest_amount_payable_now": 0.0,
                        "interest_amount_deferred": deferred_amount,
                    })
                    continue

                payout_accruals |= accrual
                accrual.write({
                    "interest_amount_payable_now": payable_now,
                    "interest_amount_deferred": deferred_amount,
                })

        else:  # partial/custom — distribute oldest first
            remaining = gross
            for accrual in accrued_candidates.sorted("accrual_date"):
                if remaining <= 0:
                    break

                payable_now, deferred_amount = self._get_accrual_cutoff_breakdown(accrual)
                if payable_now <= 0:
                    accrual.write({
                        "interest_amount_payable_now": 0.0,
                        "interest_amount_deferred": deferred_amount,
                    })
                    continue

                if remaining >= payable_now:
                    remaining -= payable_now
                    payout_accruals |= accrual
                    next_state = "paid" if deferred_amount <= 0 else "posted"
                    accrual.write({
                        "state": next_state,
                        "interest_payout_id": False,
                        "interest_amount_payable_now": payable_now,
                        "interest_amount_deferred": deferred_amount,
                    })
                else:
                    payout_accruals |= accrual
                    accrual.write({
                        "state": "posted",
                        "interest_payout_id": False,
                        "interest_amount_payable_now": remaining,
                        "interest_amount_deferred": deferred_amount + (payable_now - remaining),
                    })
                    remaining = 0.0

        # ── 4. Create payout record ────────────────────────────────────────────
        payout = self.env["alba.interest.payout"].create({
            "investment_id": investment.id,
            "payout_date": self.payout_date,
            "gross_interest": gross,
            "wht_amount": wht,
            "net_amount": net,
            "payment_id": payment.id,
            "wht_move_id": wht_move.id if wht_move else False,
            "accrual_ids": [(6, 0, payout_accruals.ids)],
            "state": "posted",
            "notes": self.notes or "",
            "memo": self.memo or ("Interest Payout — %s" % safe_investment_reference(investment)),
        })

        for accrual in payout_accruals.filtered(lambda a: a.state == "paid"):
            accrual.write({"interest_payout_id": payout.id})

        # ── 5. Mark accruals as paid only when no deferred remainder remains ───
        if payout_accruals and self.payout_mode != "partial":
            for accrual in payout_accruals:
                payable_now, deferred_amount = self._get_accrual_cutoff_breakdown(accrual)
                if deferred_amount > 0:
                    accrual.write({
                        "state": "posted",
                        "interest_payout_id": False,
                        "interest_amount_payable_now": payable_now,
                        "interest_amount_deferred": deferred_amount,
                    })
                else:
                    accrual.write({
                        "state": "paid",
                        "interest_payout_id": payout.id,
                        "interest_amount_payable_now": 0.0,
                        "interest_amount_deferred": 0.0,
                    })

        # ── 6. Invalidate subsequent posted accruals ───────────────────────────
        # After a payout, the opening balance for all future accruals changes
        # (paid interest is no longer compounding). Delete any posted accruals
        # that come AFTER the payout date so the backfill recreates them using
        # the correct running balance.
        if payout_accruals:
            if self.payout_mode == "partial":
                last_processed_date = max(payout_accruals.mapped("accrual_date")) if payout_accruals else False
                subsequent_posted = investment.accrual_ids.filtered(
                    lambda a: a.state == "posted"
                    and a.id not in payout_accruals.ids
                    and (last_processed_date and a.accrual_date > last_processed_date)
                )
            else:
                paid_period_ends = [
                    accrual.period_end for accrual in payout_accruals
                    if accrual.state == "paid"
                ]
                subsequent_posted = self.env["alba.interest.accrual"]
                if paid_period_ends:
                    last_paid_period_end = max(paid_period_ends)
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
