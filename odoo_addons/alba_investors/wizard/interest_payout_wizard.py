# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    currency_id = fields.Many2one(
        related="investment_id.currency_id",
        readonly=True,
    )
    investor_id = fields.Many2one(
        related="investment_id.investor_id",
        readonly=True,
    )

    # ── Accrual Selection ─────────────────────────────────────────────────────
    pay_all = fields.Boolean(
        string="Pay All Outstanding Accruals",
        default=True,
        help="When checked, all posted (unpaid) accruals are paid in one shot. "
             "Uncheck to select individual months.",
    )
    selected_accrual_ids = fields.Many2many(
        "alba.interest.accrual",
        "alba_interest_payout_wizard_accrual_rel",
        "wizard_id",
        "accrual_id",
        string="Accruals to Pay",
        domain="[('investment_id', '=', investment_id), ('state', '=', 'posted')]",
        help="Select one or more monthly accruals to pay out. "
             "Only posted (unpaid) accruals are available.",
    )

    # ── Summary (computed from selection) ─────────────────────────────────────
    gross_interest = fields.Monetary(
        string="Gross Interest",
        currency_field="currency_id",
        compute="_compute_payout_amounts",
        help="Total gross interest for the selected accruals.",
    )
    wht_rate = fields.Float(
        related="investment_id.wht_rate",
        readonly=True,
    )
    wht_amount = fields.Monetary(
        string="Withholding Tax (WHT)",
        currency_field="currency_id",
        compute="_compute_payout_amounts",
    )
    net_interest_payable = fields.Monetary(
        string="Net Interest to Pay",
        currency_field="currency_id",
        compute="_compute_payout_amounts",
        help="Gross interest minus WHT — this is the cash paid to the investor.",
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

    # =========================================================================
    # Compute
    # =========================================================================

    @api.depends(
        "pay_all",
        "selected_accrual_ids",
        "investment_id",
        "investment_id.accrual_ids",
        "investment_id.accrual_ids.state",
        "investment_id.accrual_ids.interest_amount",
        "investment_id.wht_rate",
    )
    def _compute_payout_amounts(self):
        for wiz in self:
            if wiz.pay_all:
                accruals = wiz.investment_id.accrual_ids.filtered(
                    lambda a: a.state == "posted"
                )
            else:
                accruals = wiz.selected_accrual_ids.filtered(
                    lambda a: a.state == "posted"
                )
            gross = sum(accruals.mapped("interest_amount"))
            wht = round(gross * (wiz.wht_rate / 100.0), 2)
            wiz.gross_interest = gross
            wiz.wht_amount = wht
            wiz.net_interest_payable = gross - wht

    @api.onchange("pay_all", "investment_id")
    def _onchange_pay_all(self):
        """Auto-populate the accrual selection when switching modes."""
        if self.pay_all:
            self.selected_accrual_ids = False
        else:
            posted = self.investment_id.accrual_ids.filtered(
                lambda a: a.state == "posted"
            )
            self.selected_accrual_ids = [(6, 0, posted.ids)]

    # =========================================================================
    # Confirm
    # =========================================================================

    def action_confirm_payout(self):
        self.ensure_one()
        investment = self.investment_id

        # ── 1. Determine accruals to pay ──────────────────────────────────────
        if self.pay_all:
            accruals_to_pay = investment.accrual_ids.filtered(
                lambda a: a.state == "posted"
            )
        else:
            accruals_to_pay = self.selected_accrual_ids.filtered(
                lambda a: a.state == "posted"
            )

        if not accruals_to_pay:
            raise UserError(_(
                "No posted accruals selected. Please select at least one "
                "accrual period to pay out."
            ))

        # ── 2. Validate accounts ───────────────────────────────────────────────
        if not investment.account_interest_payable_id:
            raise UserError(_(
                "Please configure the Interest Payable Account on investment '%s'."
            ) % investment.investment_number)

        gross = sum(accruals_to_pay.mapped("interest_amount"))
        wht = round(gross * (investment.wht_rate / 100.0), 2)
        net = gross - wht

        if net <= 0:
            raise UserError(_(
                "Net payout amount is zero or negative. "
                "Please check the WHT rate on this investment."
            ))

        company = investment.company_id or self.env.company
        comp_currency = company.currency_id
        inv_currency = investment.currency_id

        # ── 3. Create outbound payment (net interest → bank) ──────────────────
        #  DR  Interest Payable    (net amount)
        #  CR  Bank / Cash         (net amount)
        net_in_company = inv_currency._convert(
            net, comp_currency, company, self.payout_date
        )

        payment_vals = {
            "date": self.payout_date,
            "amount": net_in_company if inv_currency != comp_currency else net,
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": investment.investor_id.partner_id.id,
            "journal_id": self.journal_id.id,
            "currency_id": inv_currency.id,
            "memo": "Interest Payout — %s" % investment.investment_number,
            "destination_account_id": investment.account_interest_payable_id.id,
        }
        payment = self.env["account.payment"].create(payment_vals)
        payment.action_post()

        # ── 4. WHT clearing journal entry (if WHT > 0) ────────────────────────
        #  DR  Interest Payable    (wht amount)
        #  CR  WHT Payable         (wht amount)
        wht_move = False
        if wht > 0:
            if not investment.account_wht_payable_id:
                raise UserError(_(
                    "WHT is configured but no WHT Payable Account is set on "
                    "investment '%s'. Please configure it before paying out interest."
                ) % investment.investment_number)
            if not investment.journal_id:
                raise UserError(_(
                    "Please configure the Accrual Journal on investment '%s'."
                ) % investment.investment_number)

            wht_company = inv_currency._convert(
                wht, comp_currency, company, self.payout_date
            )

            wht_move_vals = {
                "date": self.payout_date,
                "journal_id": investment.journal_id.id,
                "ref": "IPAY-WHT/%s/%s" % (
                    investment.investment_number,
                    self.payout_date.strftime("%Y%m"),
                ),
                "move_type": "entry",
                "currency_id": inv_currency.id,
                "narration": _(
                    "WHT clearing on interest payout — %(inv)s — %(date)s",
                    inv=investment.investment_number,
                    date=self.payout_date,
                ),
                "line_ids": [
                    # DR Interest Payable (WHT portion)
                    (0, 0, {
                        "name": "WHT on interest — %s" % investment.investment_number,
                        "account_id": investment.account_interest_payable_id.id,
                        "debit": wht_company,
                        "credit": 0.0,
                        "amount_currency": wht,
                        "currency_id": inv_currency.id,
                        "partner_id": investment.investor_id.partner_id.id,
                    }),
                    # CR WHT Payable
                    (0, 0, {
                        "name": "WHT payable — %s" % investment.investment_number,
                        "account_id": investment.account_wht_payable_id.id,
                        "debit": 0.0,
                        "credit": wht_company,
                        "amount_currency": -wht,
                        "currency_id": inv_currency.id,
                        "partner_id": investment.investor_id.partner_id.id,
                    }),
                ],
            }
            wht_move = self.env["account.move"].create(wht_move_vals)
            wht_move.action_post()

        # ── 5. Create the interest payout record ──────────────────────────────
        payout_vals = {
            "investment_id": investment.id,
            "payout_date": self.payout_date,
            "gross_interest": gross,
            "wht_amount": wht,
            "net_amount": net,
            "payment_id": payment.id,
            "wht_move_id": wht_move.id if wht_move else False,
            "accrual_ids": [(6, 0, accruals_to_pay.ids)],
            "state": "posted",
            "notes": self.notes or "",
        }
        payout = self.env["alba.interest.payout"].create(payout_vals)

        # ── 6. Mark accruals as paid ──────────────────────────────────────────
        accruals_to_pay.write({
            "state": "paid",
            "interest_payout_id": payout.id,
        })

        # ── 7. Chatter on investment ───────────────────────────────────────────
        investment.message_post(
            body=_(
                "Interest payout <b>%(ref)s</b> posted: "
                "Gross <b>%(currency)s %(gross).2f</b>, "
                "WHT <b>%(currency)s %(wht).2f</b>, "
                "Net paid <b>%(currency)s %(net).2f</b>. "
                "%(count)d accrual(s) cleared. "
                "Payment: <b>%(payment)s</b>.",
                ref=payout.name,
                currency=inv_currency.symbol,
                gross=gross,
                wht=wht,
                net=net,
                count=len(accruals_to_pay),
                payment=payment.name,
            )
        )

        return {"type": "ir.actions.act_window_close"}
