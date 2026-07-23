# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaInvestmentMaturityWizard(models.TransientModel):
    """
    Maturity Processing Wizard — Rule 5.

    Presents the user with four options when an investment matures:
        (a) payout        — pay out principal + all accrued interest
        (b) rollover_full — reinvest everything into a new investment
        (c) rollover_partial — reinvest a portion, pay out the remainder
        (d) hold          — leave the investment in 'matured' state pending
                            investor instructions
    """
    _name = "alba.investment.maturity.wizard"
    _description = "Investment Maturity Processing Wizard"

    # ── Investment ─────────────────────────────────────────────────────────────
    investment_id = fields.Many2one(
        "alba.investment",
        string="Investment",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(related="investment_id.currency_id", readonly=True)
    investor_id = fields.Many2one(related="investment_id.investor_id", readonly=True)

    # ── Maturity Action ────────────────────────────────────────────────────────
    maturity_action = fields.Selection(
        selection=[
            ("payout",           "Pay Out — Principal + All Accrued Interest"),
            ("rollover_full",    "Roll Over — Reinvest Everything"),
            ("rollover_partial", "Partial Roll Over — Reinvest Some, Pay Out Balance"),
            ("hold",             "Hold — Pending Investor Instructions"),
        ],
        string="Maturity Action",
        required=True,
        default="hold",
        help="Choose how to process this matured investment.",
    )

    # ── Summary (read-only, always shown) ─────────────────────────────────────
    principal_amount = fields.Monetary(
        related="investment_id.principal_amount",
        string="Principal",
        readonly=True,
    )
    total_topup_amount = fields.Monetary(
        related="investment_id.total_topup_amount",
        string="Total Top-Ups",
        readonly=True,
    )
    total_interest_outstanding = fields.Monetary(
        related="investment_id.total_interest_outstanding",
        string="Outstanding Interest",
        readonly=True,
    )
    wht_rate = fields.Float(related="investment_id.wht_rate", readonly=True)
    wht_amount = fields.Monetary(
        related="investment_id.wht_amount",
        string="WHT Amount",
        readonly=True,
    )
    net_interest_payable = fields.Monetary(
        related="investment_id.net_interest_payable",
        string="Net Interest (after WHT)",
        readonly=True,
    )
    total_value = fields.Monetary(
        string="Total Maturity Value",
        currency_field="currency_id",
        compute="_compute_totals",
        store=False,
        help="Principal + top-ups + net interest after WHT.",
    )

    # ── Payout fields (shown for 'payout' and 'rollover_partial') ─────────────
    payout_journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    payout_date = fields.Date(
        string="Payout Date",
        default=fields.Date.context_today,
    )

    # ── Rollover fields (shown for 'rollover_full' and 'rollover_partial') ─────
    new_interest_rate = fields.Float(
        string="New Annual Rate (%)",
        digits=(5, 4),
        help="Interest rate for the rolled-over investment. "
             "Defaults to the existing rate — change if the terms differ at renewal.",
    )
    new_maturity_date = fields.Date(
        string="New Maturity Date",
        help="Maturity date for the new (rolled-over) investment.",
    )
    rollover_amount = fields.Monetary(
        string="Amount to Roll Over",
        currency_field="currency_id",
        help="Amount to reinvest (for Partial Roll Over). "
             "The remainder will be paid out to the investor.",
    )
    payout_amount = fields.Monetary(
        string="Amount to Pay Out",
        currency_field="currency_id",
        compute="_compute_totals",
        store=False,
        help="For Partial Roll Over: total value minus the rollover amount.",
    )

    # =========================================================================
    # Compute
    # =========================================================================

    @api.depends(
        "investment_id",
        "investment_id.principal_amount",
        "investment_id.total_topup_amount",
        "investment_id.net_interest_payable",
        "rollover_amount",
        "maturity_action",
    )
    def _compute_totals(self):
        for wiz in self:
            inv = wiz.investment_id
            if not inv:
                wiz.total_value = 0.0
                wiz.payout_amount = 0.0
                continue
            total = (
                (inv.principal_amount or 0.0)
                + (inv.total_topup_amount or 0.0)
                + (inv.net_interest_payable or 0.0)
            )
            wiz.total_value = total
            wiz.payout_amount = max(0.0, total - (wiz.rollover_amount or 0.0))

    @api.onchange("investment_id")
    def _onchange_investment_id(self):
        if self.investment_id:
            self.new_interest_rate = self.investment_id.interest_rate

    @api.onchange("maturity_action")
    def _onchange_maturity_action(self):
        if self.maturity_action == "rollover_full":
            self.rollover_amount = self.total_value
        elif self.maturity_action in ("payout", "hold"):
            self.rollover_amount = 0.0

    # =========================================================================
    # Validation
    # =========================================================================

    def _validate(self):
        self.ensure_one()
        inv = self.investment_id
        if inv.state != "matured":
            raise UserError(_(
                "Investment %s must be in 'Matured' state before processing."
            ) % inv.investment_number)

        if self.maturity_action == "payout":
            if not self.payout_journal_id:
                raise UserError(_("Please select a Payment Journal for the payout."))
            if not self.payout_date:
                raise UserError(_("Please specify a Payout Date."))

        elif self.maturity_action == "rollover_full":
            if not self.new_maturity_date:
                raise UserError(_("Please specify a New Maturity Date for the rolled-over investment."))
            if not self.new_interest_rate:
                raise UserError(_("Please specify the interest rate for the new investment."))

        elif self.maturity_action == "rollover_partial":
            if not self.rollover_amount or self.rollover_amount <= 0:
                raise UserError(_("Please enter an amount to roll over."))
            if self.rollover_amount >= self.total_value:
                raise UserError(_(
                    "Rollover amount must be less than the total maturity value (%(total).2f). "
                    "Use 'Roll Over — Reinvest Everything' for a full rollover."
                ) % {"total": self.total_value})
            if not self.new_maturity_date:
                raise UserError(_("Please specify a New Maturity Date for the rolled-over portion."))
            if not self.payout_journal_id:
                raise UserError(_("Please select a Payment Journal for the cash-out portion."))

    # =========================================================================
    # Action: Confirm
    # =========================================================================

    def action_confirm(self):
        self.ensure_one()
        self._validate()

        if self.maturity_action == "payout":
            return self._process_full_payout()

        elif self.maturity_action == "rollover_full":
            self._process_full_rollover()
            return {"type": "ir.actions.act_window_close"}

        elif self.maturity_action == "rollover_partial":
            return self._process_partial_rollover()

        else:  # hold
            self.investment_id.message_post(
                body=_("Maturity processing: <b>Hold</b>. Awaiting investor instructions.")
            )
            return {"type": "ir.actions.act_window_close"}

    # =========================================================================
    # Processing Helpers
    # =========================================================================

    def _process_full_payout(self):
        """Option (a): Pay out principal + all accrued interest via the withdraw wizard."""
        self.ensure_one()
        inv = self.investment_id

        # Delegate to the existing withdrawal wizard logic, pre-filled for maturity
        return {
            "name": _("Maturity Payout — %s") % inv.investment_number,
            "type": "ir.actions.act_window",
            "res_model": "alba.investment.withdraw.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_investment_id": inv.id,
                "default_journal_id": self.payout_journal_id.id if self.payout_journal_id else False,
                "default_payment_date": str(self.payout_date) if self.payout_date else False,
            },
        }

    def _process_full_rollover(self):
        """Option (b): Reinvest everything into a new investment with the same terms."""
        self.ensure_one()
        inv = self.investment_id

        if not self.new_maturity_date:
            raise UserError(_("New Maturity Date is required for a rollover."))

        new_inv = self.env["alba.investment"].create({
            "investor_id": inv.investor_id.id,
            "investment_product_id": inv.investment_product_id.id,
            "investment_type": inv.investment_type,
            "principal_amount": self.total_value,
            "interest_rate": self.new_interest_rate or inv.interest_rate,
            "compounding_frequency": inv.compounding_frequency,
            "start_date": self.payout_date or fields.Date.today(),
            "maturity_date": self.new_maturity_date,
            "currency_id": inv.currency_id.id,
            "account_interest_expense_id": inv.account_interest_expense_id.id,
            "account_interest_payable_id": inv.account_interest_payable_id.id,
            "account_investment_liability_id": inv.account_investment_liability_id.id,
            "account_long_term_liability_id": inv.account_long_term_liability_id.id if inv.account_long_term_liability_id else False,
            "journal_id": inv.journal_id.id,
            "payment_journal_id": inv.payment_journal_id.id,
            "wht_rate": inv.wht_rate,
            "account_wht_payable_id": inv.account_wht_payable_id.id,
            "notes": _("Rolled over from %s on maturity.") % inv.investment_number,
        })

        inv.message_post(body=_(
            "Investment <b>rolled over</b> in full at maturity. "
            "New investment: <b><a href='/odoo/alba-investments/%d'>%s</a></b>. "
            "New principal: <b>%s %.2f</b>."
        ) % (new_inv.id, new_inv.investment_number, inv.currency_id.symbol, self.total_value))

        new_inv.message_post(body=_(
            "Created by full rollover of matured investment <b>%s</b>."
        ) % inv.investment_number)

        return new_inv

    def _process_partial_rollover(self):
        """Option (c): Reinvest rollover_amount; pay out the remainder."""
        self.ensure_one()
        inv = self.investment_id
        payout_portion = self.payout_amount

        # Create the new (reinvested) investment
        new_inv = self._process_full_rollover_for_amount(self.rollover_amount)

        inv.message_post(body=_(
            "Partial rollover at maturity: <b>%(sym)s %(rollover).2f</b> reinvested in "
            "<b><a href='/odoo/alba-investments/%(new_id)d'>%(new_num)s</a></b>. "
            "Cash payout: <b>%(sym)s %(payout).2f</b> — use Withdraw Investment to process.",
            sym=inv.currency_id.symbol,
            rollover=self.rollover_amount,
            new_id=new_inv.id,
            new_num=new_inv.investment_number,
            payout=payout_portion,
        ))

        # Open the withdraw wizard for the cash-out portion
        # (The original investment stays matured until withdrawn)
        return {
            "name": _("Partial Maturity Payout — %s") % inv.investment_number,
            "type": "ir.actions.act_window",
            "res_model": "alba.investment.withdraw.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_investment_id": inv.id,
                "default_journal_id": self.payout_journal_id.id if self.payout_journal_id else False,
                "default_payment_date": str(self.payout_date) if self.payout_date else False,
            },
        }

    def _process_full_rollover_for_amount(self, amount):
        """Create a new rolled-over investment for the given amount."""
        self.ensure_one()
        inv = self.investment_id
        new_inv = self.env["alba.investment"].create({
            "investor_id": inv.investor_id.id,
            "investment_product_id": inv.investment_product_id.id,
            "investment_type": inv.investment_type,
            "principal_amount": amount,
            "interest_rate": self.new_interest_rate or inv.interest_rate,
            "compounding_frequency": inv.compounding_frequency,
            "start_date": self.payout_date or fields.Date.today(),
            "maturity_date": self.new_maturity_date,
            "currency_id": inv.currency_id.id,
            "account_interest_expense_id": inv.account_interest_expense_id.id,
            "account_interest_payable_id": inv.account_interest_payable_id.id,
            "account_investment_liability_id": inv.account_investment_liability_id.id,
            "account_long_term_liability_id": inv.account_long_term_liability_id.id if inv.account_long_term_liability_id else False,
            "journal_id": inv.journal_id.id,
            "payment_journal_id": inv.payment_journal_id.id,
            "wht_rate": inv.wht_rate,
            "account_wht_payable_id": inv.account_wht_payable_id.id,
            "notes": _("Partial rollover from %s on maturity.") % inv.investment_number,
        })
        return new_inv
