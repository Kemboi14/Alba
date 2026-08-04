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
        "payout_date",
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
                # Bug 1 fix: use total_interest_outstanding (accrued minus already paid),
                # not total_accrued (all-time sum). This prevents showing an inflated
                # balance when some months have already been paid out.
                outstanding = wiz.investment_id.total_interest_outstanding or 0.0
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

    @api.onchange("selected_accrual_ids")
    def _onchange_selected_accrual_ids(self):
        """Recalculate payout amounts when specific accruals are selected/deselected."""
        # The compute method will automatically trigger due to @api.depends
        # This onchange ensures UI updates immediately when user changes selection
        pass

    @api.onchange("custom_gross_amount")
    def _onchange_custom_gross_amount(self):
        """Recalculate and validate custom partial amount."""
        if self.payout_mode == "partial" and self.custom_gross_amount:
            outstanding = self.total_outstanding or 0.0
            if self.custom_gross_amount > outstanding:
                # Odoo will show a warning but not block the user
                return {
                    'warning': {
                        'title': _('Amount Exceeds Outstanding'),
                        'message': _('Custom amount (%.2f) exceeds total outstanding interest (%.2f). It will be capped at the outstanding amount.') 
                                  % (self.custom_gross_amount, outstanding)
                    }
                }

    @api.onchange("payout_date")
    def _onchange_payout_date(self):
        """Recalculate payout amounts when payout date changes (affects cutoff calculations)."""
        # The compute method will automatically trigger due to @api.depends
        # This onchange ensures UI updates immediately when user changes date
        pass

    def _get_accrual_cutoff_breakdown(self, accrual):
        """
        Return (payable_now, deferred_amount) for this accrual.

        Fix A — Root cause of half-payments:
        The old code unconditionally read interest_amount_payable_now/deferred from the
        DB. Those fields are written at creation time by split_period_for_payout_cutoff
        (the 15th-cutoff first-period rule). Once the period is complete those stored
        values are stale — the full interest_amount is owed. Reading the stale stored
        split caused the wizard to pay only the 'payable_now' portion (e.g. 450/1,000).

        Rules (in priority order):
        1. Period complete (period_end <= payout_date):
           a. If the accrual is POSTED and has interest_payout_id set, it was partially
              consumed in a prior custom payout. The genuine remaining balance is stored
              in interest_amount_deferred. Return that as the payable amount.
           b. Otherwise (fresh or stale creation split): return full interest_amount.
        2. Period still in progress: split by the 15th-of-month cutoff.
        """
        payout_date = self.payout_date or fields.Date.today()

        if accrual.period_end and accrual.period_end <= payout_date:
            # Partially consumed in a prior custom payout — interest_payout_id is set
            # (even though state is still 'posted') and interest_amount_deferred holds
            # the true remaining amount after the earlier partial payment.
            if accrual.state == "posted" and accrual.interest_payout_id:
                return accrual.interest_amount_deferred or 0.0, 0.0
            # Fresh accrual or stale first-period creation split — full amount is due.
            return accrual.interest_amount or 0.0, 0.0

        # In-progress period — split by the 15th-of-month payout cutoff.
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

        # Fix D: cache breakdown results here so step 5 can reuse them without
        # a second DB read (which would read the values just written by this step
        # and potentially produce a different result if any rounding occurred).
        breakdown_cache = {}  # accrual.id -> (payable_now, deferred_amount)

        if self.payout_mode in ("all", "select"):
            for accrual in accrued_candidates:
                payable_now, deferred_amount = self._get_accrual_cutoff_breakdown(accrual)
                breakdown_cache[accrual.id] = (payable_now, deferred_amount)
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
            # Bug 2 fix: do NOT set state='paid' inside the loop — the payout record
            # does not exist yet, so interest_payout_id cannot be linked atomically.
            remaining = gross
            partial_fully_consumed = self.env["alba.interest.accrual"]
            # Track the ONE accrual that was split (partially consumed, not fully paid).
            # This is set to the payout after creation so _get_accrual_cutoff_breakdown
            # can identify it as a genuine partial residual on the next payout.
            partial_partially_consumed = self.env["alba.interest.accrual"]
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
                    accrual.write({
                        "interest_amount_payable_now": payable_now,
                        "interest_amount_deferred": deferred_amount,
                    })
                    if deferred_amount <= 0:
                        partial_fully_consumed |= accrual
                else:
                    # Partial split: record how much was paid now and how much remains.
                    # interest_amount_deferred = the true unpaid remainder.
                    # interest_payout_id will be set after payout creation (step 4.5)
                    # so _get_accrual_cutoff_breakdown returns this deferred amount
                    # (not the full interest_amount) on the next payout run.
                    payout_accruals |= accrual
                    accrual.write({
                        "interest_amount_payable_now": remaining,
                        "interest_amount_deferred": deferred_amount + (payable_now - remaining),
                    })
                    partial_partially_consumed = accrual
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

        # Step 4.5: now that the payout record exists, link accruals atomically.
        if self.payout_mode == "partial":
            # Fully consumed months: mark paid and link to payout.
            if partial_fully_consumed:
                partial_fully_consumed.write({
                    "state": "paid",
                    "interest_payout_id": payout.id,
                })
            # Partially consumed month: stays 'posted' but gets interest_payout_id set
            # so _get_accrual_cutoff_breakdown knows its interest_amount_deferred is a
            # genuine unpaid residual (not a stale first-period creation split).
            if partial_partially_consumed:
                partial_partially_consumed.write({"interest_payout_id": payout.id})

        for accrual in payout_accruals.filtered(lambda a: a.state == "paid"):
            accrual.write({"interest_payout_id": payout.id})

        # ── 5. Mark accruals as paid only when no deferred remainder remains ───
        # Fix D: reuse breakdown_cache from step 3 — avoids a second call to
        # _get_accrual_cutoff_breakdown which would re-read the values just
        # written by step 3 and could produce inconsistent results.
        if payout_accruals and self.payout_mode != "partial":
            for accrual in payout_accruals:
                payable_now, deferred_amount = breakdown_cache.get(
                    accrual.id, (accrual.interest_amount or 0.0, 0.0)
                )
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

        # ── 6. Delete all stale posted accruals from the first paid period onwards ──
        # Fix F: after paying any month(s), every subsequent posted accrual has a
        # stale opening balance because it was computed assuming those months would
        # compound. The old code only deleted accruals AFTER the last paid period,
        # leaving gap months (e.g. M2, M4 when M1, M3, M5 were paid) with wrong
        # opening balances. The fix: delete every posted accrual whose period_start
        # is >= the EARLIEST paid period's period_start, excluding the accruals that
        # were just processed in this payout. The cron will regenerate them all with
        # the correct running balance.
        if payout_accruals:
            # Find accruals that are now fully paid after step 5
            paid_in_this_payout = payout_accruals.filtered(lambda a: a.state == "paid")
            if paid_in_this_payout:
                first_paid_period_start = min(paid_in_this_payout.mapped("period_start"))
                payout_accrual_ids = set(payout_accruals.ids)

                # All posted accruals at or after the first paid period that were
                # NOT part of this payout are now stale — delete them.
                stale_posted = investment.accrual_ids.filtered(
                    lambda a: a.state == "posted"
                    and a.id not in payout_accrual_ids
                    and a.period_start >= first_paid_period_start
                )
                if stale_posted:
                    for accrual in stale_posted:
                        if accrual.move_id and accrual.move_id.state == "posted":
                            accrual.move_id.button_cancel()
                            accrual.move_id.unlink()
                    stale_posted.unlink()

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
