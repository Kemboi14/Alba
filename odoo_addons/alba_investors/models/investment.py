# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .accrual_backfill import (
    iter_missing_accrual_periods,
    _period_start_from_accrual_date,
    get_effective_period_start,
    split_period_for_payout_cutoff,
    compute_accrual_interest,
    split_period_by_topups,
)


class AlbaInvestment(models.Model):
    _name = "alba.investment"
    _description = "Alba Capital Investment Account"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "investment_number"
    _order = "start_date desc, id desc"

    # ── Identification ────────────────────────────────────────────────────────
    investment_number = fields.Char(
        string="Investment Number",
        readonly=False,  # IMPORT-FIX: make writable for import matching
        copy=False,
        index=True,
        store=True,
        default=lambda self: _("New"),
    )

    # ── Investor Link ─────────────────────────────────────────────────────────
    investor_id = fields.Many2one(
        "alba.investor",
        string="Investor",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="investor_id.partner_id",
        store=True,
        readonly=True,
    )
    investment_product_id = fields.Many2one(
        "alba.investment.product",
        string="Investment Product",
        # Do not restrict available products by `currency_id` here because
        # new investments may start without a currency. Let the product
        # selection determine the currency and other defaults.
        domain="[('active', '=', True), ('investment_type', '=', investment_type)]",
        tracking=True,
        help="Configuration that supplies default rates, ledgers, journals, and document requirements.",
    )
    relationship_officer_id = fields.Many2one(
        "hr.employee",
        string="Relationship Officer",
        tracking=True,
        help="Relationship Officer assigned to this investment account.",
    )

    
    # ── Investment Type ───────────────────────────────────────────────────────
    investment_type = fields.Selection(
        selection=[
            ("fixed_term", "Fixed Term"),
            ("open_ended", "Open Ended"),
        ],
        string="Investment Type",
        required=True,
        default="fixed_term",
        tracking=True,
    )

    # ── Terms ─────────────────────────────────────────────────────────────────
    principal_amount = fields.Monetary(
        string="Principal Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    interest_rate = fields.Float(
        string="Annual Interest Rate (%)",
        digits=(5, 4),
        required=True,
        tracking=True,
        help="Annual interest rate as a percentage e.g. 12.0000 for 12% per annum.",
    )
    compounding_frequency = fields.Selection(
        selection=[
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("annually", "Annually"),
        ],
        string="Compounding Frequency",
        required=True,
        default="monthly",
        tracking=True,
    )

    # ── Dates ─────────────────────────────────────────────────────────────────
    start_date = fields.Date(
        string="Start Date",
        required=True,
        tracking=True,
        default=fields.Date.today,
    )
    maturity_date = fields.Date(
        string="Maturity Date",
        tracking=True,
        help="Required for Fixed Term investments. Leave blank for Open Ended.",
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("active", "Active"),
            ("matured", "Matured"),
            ("withdrawn", "Withdrawn"),
            ("suspended", "Suspended"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )

    # ── Financial Totals (computed) ───────────────────────────────────────────
    current_value = fields.Monetary(
        string="Current Value",
        currency_field="currency_id",
        compute="_compute_financials",
        inverse="_inverse_current_value",
        store=True,
        help="Principal + total interest accrued to date.",
        # IMPORT-EXPORT FIX: inverse allows import to write value; compute resets on next trigger
    )
    total_interest_accrued = fields.Monetary(
        string="Total Interest Accrued",
        currency_field="currency_id",
        compute="_compute_financials",
        inverse="_inverse_total_interest_accrued",
        store=True,
        # IMPORT-EXPORT FIX
    )
    total_interest_paid = fields.Monetary(
        string="Total Interest Paid Out",
        currency_field="currency_id",
        compute="_compute_financials",
        inverse="_inverse_total_interest_paid",
        store=True,
        # IMPORT-EXPORT FIX
    )
    total_topup_amount = fields.Monetary(
        string="Total Top-Ups",
        currency_field="currency_id",
        compute="_compute_financials",
        inverse="_inverse_total_topup_amount",
        store=True,
        help="Sum of all posted top-up (incremental deposit) amounts.",
    )
    total_interest_outstanding = fields.Monetary(
        string="Outstanding Interest",
        currency_field="currency_id",
        compute="_compute_financials",
        inverse="_inverse_total_interest_outstanding",
        store=True,
        help="Gross interest accrued minus gross interest already paid out — "
             "balance still sitting in the Interest Payable account.",
    )
    accrual_count = fields.Integer(
        string="Accruals",
        compute="_compute_accrual_count",
    )
    payout_count = fields.Integer(
        string="Interest Payouts",
        compute="_compute_payout_count",
    )
    topup_count = fields.Integer(
        string="Top-Ups",
        compute="_compute_topup_count",
    )
    statement_count = fields.Integer(
        string="Number of Statements",
        compute="_compute_statement_count",
    )
    investment_progress = fields.Float(
        string="Investment Progress",
        compute="_compute_investment_progress",
        help="Percentage of the investment term that has elapsed.",
    )

    def _compute_investment_progress(self):
        today = fields.Date.today()
        for rec in self:
            if rec.investment_type == 'fixed_term' and rec.start_date and rec.maturity_date:
                total_days = (rec.maturity_date - rec.start_date).days
                if total_days > 0:
                    elapsed_days = (today - rec.start_date).days
                    progress = (elapsed_days / total_days) * 100
                    rec.investment_progress = max(0, min(100, progress))
                else:
                    rec.investment_progress = 0
            else:
                rec.investment_progress = 0


    # ── Relationships ─────────────────────────────────────────────────────────
    accrual_ids = fields.One2many(
        "alba.interest.accrual",
        "investment_id",
        string="Interest Accruals",
    )
    statement_ids = fields.One2many(
        "alba.investment.statement",
        "investment_id",
        string="Statements",
    )
    topup_ids = fields.One2many(
        "alba.investment.topup",
        "investment_id",
        string="Top-Ups",
    )
    payout_ids = fields.One2many(
        "alba.interest.payout",
        "investment_id",
        string="Interest Payouts",
    )

    # ── Accounting ────────────────────────────────────────────────────────────
    account_interest_expense_id = fields.Many2one(
        "account.account",
        string="Interest Expense Account",
        tracking=True,
        domain="[('account_type', '=', 'expense')]",
        help="Account debited when interest is accrued (DR Interest Expense).",
    )
    account_interest_payable_id = fields.Many2one(
        "account.account",
        string="Interest Payable Account",
        tracking=True,
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current'])]",
        help="Account credited when interest is accrued (CR Interest Payable).",
    )
    account_investment_liability_id = fields.Many2one(
        "account.account",
        string="Investment Liability Account",
        tracking=True,
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current'])]",
        help="Liability account representing funds received from investors.",
    )
    account_long_term_liability_id = fields.Many2one(
        "account.account",
        string="Long-term Investment Liability Account",
        tracking=True,
        domain="[('account_type', '=', 'liability_non_current')]",
        help="Account used for investments with tenure > 1 year.",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Accrual Journal",
        domain="[('type', '=', 'general')]",
        help="General journal used for interest accrual entries.",
    )
    payment_journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Bank/Cash journal to record the receipt of investment funds.",
        tracking=True,
    )
    wht_rate = fields.Float(
        string="Withholding Tax Rate (%)",
        default=15.0,
        tracking=True,
    )
    account_wht_payable_id = fields.Many2one(
        "account.account",
        string="WHT Payable Account",
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current', 'liability_payable'])]",
        tracking=True,
    )
    wht_amount = fields.Monetary(
        string="Withholding Tax Amount",
        currency_field="currency_id",
        compute="_compute_wht_amount",
        inverse="_inverse_wht_amount",
        store=True,
        # IMPORT-EXPORT FIX
    )
    net_interest_payable = fields.Monetary(
        string="Net Interest Payable",
        currency_field="currency_id",
        compute="_compute_wht_amount",
        inverse="_inverse_net_interest_payable",
        store=True,
        # IMPORT-EXPORT FIX
    )
    net_payout_amount = fields.Monetary(
        string="Net Payout Amount",
        currency_field="currency_id",
        compute="_compute_wht_amount",
        inverse="_inverse_net_payout_amount",
        store=True,
        # IMPORT-EXPORT FIX
    )
    payment_id = fields.Many2one(
        "account.payment",
        string="Initial Payment Receipt",
        readonly=True,
        copy=False,
    )
    initial_accounting_posted = fields.Boolean(
        string="Initial Accounting Posted",
        compute="_compute_initial_accounting_posted",
        store=True,
    )
    withdrawal_payment_id = fields.Many2one(
        "account.payment",
        string="Withdrawal Payment",
        readonly=True,
        copy=False,
    )
    withdrawal_notice_date = fields.Date(
        string="Early Withdrawal Notice Date",
        readonly=True,
        copy=False,
        tracking=True,
    )
    earliest_withdrawal_date = fields.Date(
        string="Earliest Withdrawal Date",
        compute="_compute_earliest_withdrawal_date",
        store=True,
        readonly=True,
        compute_sudo=True,
    )
    days_to_withdrawal = fields.Integer(
        string="Days to Withdrawal",
        compute="_compute_withdrawal_notice",
        compute_sudo=True,
    )
    can_withdraw_now = fields.Boolean(
        string="Can Withdraw Now",
        compute="_compute_withdrawal_notice",
        compute_sudo=True,
    )

    # ── Currency / Company ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="investor_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=False,
        tracking=True,
        help="Currency will be set when an investment product is chosen.",
    )

    # ── UX Helpers ────────────────────────────────────────────────────────────
    maturity_progress = fields.Integer(
        string="Maturity Progress %",
        compute="_compute_maturity",
    )
    is_high_yield = fields.Boolean(
        string="High Yield Investment",
        compute="_compute_is_high_yield",
        store=True,
    )
    days_to_maturity = fields.Integer(
        string="Days to Maturity",
        compute="_compute_maturity",
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string="Notes")

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _investment_number_unique = models.Constraint(
        "UNIQUE(investment_number)",
        "An investment with this number already exists.",
    )
    _principal_positive = models.Constraint(
        "CHECK(principal_amount > 0)",
        "Principal amount must be greater than zero.",
    )
    _interest_rate_non_negative = models.Constraint(
        "CHECK(interest_rate >= 0)",
        "Interest rate cannot be negative.",
    )

    # =========================================================================
    # Computed methods
    # =========================================================================

    @api.depends(
        "principal_amount",
        "accrual_ids.state",
        "accrual_ids.interest_amount",
        "payout_ids.state",
        "payout_ids.gross_interest",
        "topup_ids.state",
        "topup_ids.amount",
    )
    def _compute_financials(self):
        for rec in self:
            # All interest ever earned (posted + paid accruals)
            all_accruals = rec.accrual_ids.filtered(
                lambda a: a.state in ("posted", "paid")
            )
            total_accrued = sum(all_accruals.mapped("interest_amount"))

            # Total gross interest paid out (from posted payout records)
            # This covers both full-month and partial payouts correctly
            posted_payouts = rec.payout_ids.filtered(lambda p: p.state == "posted")
            total_paid = sum(posted_payouts.mapped("gross_interest"))

            # Top-ups received (only posted top-ups)
            posted_topups = rec.topup_ids.filtered(lambda t: t.state == "posted")
            total_topup = sum(posted_topups.mapped("amount"))

            # Outstanding interest = accrued but not yet paid out
            outstanding = max(total_accrued - total_paid, 0.0)

            rec.total_interest_accrued = total_accrued
            rec.total_interest_paid = total_paid
            rec.total_topup_amount = total_topup
            rec.total_interest_outstanding = outstanding
            # current_value = original principal + all top-ups + outstanding interest
            rec.current_value = rec.principal_amount + total_topup + outstanding

    # IMPORT-EXPORT FIX: no-op inverses
    def _inverse_current_value(self): pass
    def _inverse_total_interest_accrued(self): pass
    def _inverse_total_interest_paid(self): pass
    def _inverse_total_topup_amount(self): pass
    def _inverse_total_interest_outstanding(self): pass

    @api.depends(
        "total_interest_outstanding",
        "principal_amount",
        "total_topup_amount",
        "wht_rate",
    )
    def _compute_wht_amount(self):
        for rec in self:
            outstanding = rec.total_interest_outstanding
            rec.wht_amount = outstanding * (rec.wht_rate / 100.0)
            rec.net_interest_payable = outstanding - rec.wht_amount
            # Full withdrawal payout = principal + all top-ups + net outstanding interest
            rec.net_payout_amount = (
                rec.principal_amount + rec.total_topup_amount + rec.net_interest_payable
            )

    # IMPORT-EXPORT FIX: no-op inverses for WHT fields
    def _inverse_wht_amount(self): pass
    def _inverse_net_interest_payable(self): pass
    def _inverse_net_payout_amount(self): pass

    def _compute_accrual_count(self):
        for rec in self:
            rec.accrual_count = len(rec.accrual_ids)

    def _compute_payout_count(self):
        for rec in self:
            rec.payout_count = len(rec.payout_ids)

    def _compute_topup_count(self):
        for rec in self:
            rec.topup_count = len(rec.topup_ids)

    def _compute_statement_count(self):
        for rec in self:
            rec.statement_count = len(rec.statement_ids)

    @api.depends("payment_id", "payment_id.state")
    def _compute_initial_accounting_posted(self):
        for rec in self:
            rec.initial_accounting_posted = rec.payment_id.state == "posted"

    @api.depends("interest_rate")
    def _compute_is_high_yield(self):
        for rec in self:
            rec.is_high_yield = rec.interest_rate >= 15.0

    @api.depends("start_date", "maturity_date", "investment_type")
    def _compute_maturity(self):
        today = fields.Date.today()
        for rec in self:
            if rec.investment_type == "fixed_term" and rec.start_date and rec.maturity_date:
                total_days = (rec.maturity_date - rec.start_date).days
                elapsed_days = (today - rec.start_date).days
                
                if total_days > 0:
                    rec.maturity_progress = min(100, max(0, int((elapsed_days / total_days) * 100)))
                    rec.days_to_maturity = max(0, (rec.maturity_date - today).days)
                else:
                    rec.maturity_progress = 0
                    rec.days_to_maturity = 0
            else:
                rec.maturity_progress = 0
                rec.days_to_maturity = 0

    @api.depends("withdrawal_notice_date", "investment_product_id.early_withdrawal_notice_days")
    def _compute_earliest_withdrawal_date(self):
        for rec in self:
            notice_days = rec.investment_product_id.early_withdrawal_notice_days or 60
            rec.earliest_withdrawal_date = (
                rec.withdrawal_notice_date + timedelta(days=notice_days)
                if rec.withdrawal_notice_date
                else False
            )

    @api.depends(
        "earliest_withdrawal_date",
        "state",
        "investment_type",
        "maturity_date",
    )
    def _compute_withdrawal_notice(self):
        today = fields.Date.today()
        for rec in self:
            if rec.earliest_withdrawal_date:
                rec.days_to_withdrawal = max(0, (rec.earliest_withdrawal_date - today).days)
            else:
                rec.days_to_withdrawal = 0

            matured = rec.state == "matured" or (
                rec.investment_type == "fixed_term"
                and rec.maturity_date
                and rec.maturity_date <= today
            )
            notice_elapsed = bool(
                rec.earliest_withdrawal_date and rec.earliest_withdrawal_date <= today
            )
            rec.can_withdraw_now = rec.state in ("active", "matured") and (
                matured or rec.investment_type != "fixed_term" or notice_elapsed
            )

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.onchange("investment_product_id")
    def _onchange_investment_product_id(self):
        for rec in self:
            if rec.investment_product_id:
                rec._apply_product_defaults()
            else:
                rec.interest_rate = 0.0

    @api.onchange("investment_type", "currency_id", "investor_id")
    def _onchange_investment_product_lookup(self):
        for rec in self:
            if not rec.investment_product_id and rec.currency_id:
                product = rec.env["alba.investment.product"]._default_product_for(
                    rec.investment_type,
                    rec.currency_id.id,
                    rec.investor_id.company_id.id if rec.investor_id else rec.env.company.id,
                )
                if product:
                    rec.investment_product_id = product
                    rec._apply_product_defaults()

    def _apply_product_defaults(self):
        for rec in self:
            product = rec.investment_product_id
            if not product:
                continue
            rec.investment_type = product.investment_type
            rec.currency_id = product.currency_id
            rec.interest_rate = product.interest_rate
            rec.compounding_frequency = product.compounding_frequency
            rec.account_interest_expense_id = product.account_interest_expense_id
            rec.account_interest_payable_id = product.account_interest_payable_id
            rec.account_investment_liability_id = product.account_investment_liability_id
            rec.account_long_term_liability_id = product.account_long_term_liability_id
            rec.journal_id = product.journal_id
            rec.payment_journal_id = product.payment_journal_id
            rec.wht_rate = product.wht_rate
            rec.account_wht_payable_id = product.account_wht_payable_id
            # If the product defines a default principal and the investment
            # principal is empty or zero, apply the default principal.
            try:
                default_principal = product.default_principal
            except Exception:
                default_principal = None
            if default_principal and (not rec.principal_amount or rec.principal_amount == 0.0):
                rec.principal_amount = default_principal

    @api.constrains("investment_type", "maturity_date")
    def _check_maturity_date(self):
        for rec in self:
            if rec.investment_type == "fixed_term" and not rec.maturity_date:
                raise ValidationError(
                    _("A Maturity Date is required for Fixed Term investments.")
                )
            if (
                rec.maturity_date
                and rec.start_date
                and rec.maturity_date <= rec.start_date
            ):
                raise ValidationError(_("Maturity Date must be after the Start Date."))

    @api.constrains("interest_rate")
    def _check_interest_rate(self):
        for rec in self:
            if rec.interest_rate < 0:
                raise ValidationError(_("Interest rate cannot be negative."))
            if rec.interest_rate > 1200:
                raise ValidationError(_("Interest rate cannot exceed 1200%."))

    # =========================================================================
    # Compound Interest Engine
    # =========================================================================

    def _get_periods_per_year(self):
        """Return the number of compounding periods per year."""
        self.ensure_one()
        return {
            "monthly": 12,
            "quarterly": 4,
            "annually": 1,
        }.get(self.compounding_frequency, 12)

    def compute_compound_interest_for_period(self, opening_balance=None):
        """
        Calculate compound interest for one compounding period.

        Formula: I = P_current × ( (1 + r/n) - 1 )
        Where:
            P_current = current investment value (principal + previously accrued interest)
            r         = annual interest rate / 100
            n         = compounding periods per year
        Returns:
            float: interest amount for one period
        """
        self.ensure_one()
        n = self._get_periods_per_year()
        r = self.interest_rate / 100.0
        current = opening_balance if opening_balance is not None else self.current_value
        period_interest = current * ((1 + r / n) - 1)
        return round(period_interest, 2)

    def action_accrue_monthly_interest(self, accrual_date=None, opening_balance=None,
                                       period_start=None, period_end=None):
        """
        Accrue one month's compound interest on this investment.
        Creates an alba.interest.accrual record and posts its journal entry.
        Returns the new accrual record.

        Args:
            accrual_date:    Date to stamp on the accrual record (defaults to today).
            opening_balance: Balance at period start (defaults to current_value).
            period_start:    Explicit period start (optional; overrides auto-derivation).
                             Pass this from the backfill loop when a pro-rata first
                             period has been clamped to the investment start date.
            period_end:      Explicit period end (optional; overrides auto-derivation).
        """
        self.ensure_one()
        if self.state != "active":
            raise UserError(
                _("Cannot accrue interest on investment %s — status is '%s'.")
                % (self.investment_number, self.state)
            )

        today = fields.Date.to_date(accrual_date) if accrual_date else fields.Date.today()

        # Determine period start/end: prefer explicit args (backfill passes these so
        # that pro-rata first-month clamping is preserved), otherwise derive from today.
        if period_start is None or period_end is None:
            from datetime import date as _date
            month = today.month
            year = today.year
            # 29th-to-28th rule: period_end = 28th of current month,
            # period_start = 29th of previous month (timedelta handles leap years)
            period_end = _date(year, month, 28)
            period_start = _period_start_from_accrual_date(period_end)

        existing = self.env["alba.interest.accrual"].search(
            [
                ("investment_id", "=", self.id),
                ("period_start", "=", period_start),
                ("period_end", "=", period_end),
                ("state", "in", ["posted", "draft", "paid", "reversed"]),
            ],
            limit=1,
        )
        if existing:
            return False

        has_existing_accruals = bool(self.env["alba.interest.accrual"].search(
            [
                ("investment_id", "=", self.id),
                ("state", "in", ["posted", "draft", "paid", "reversed"]),
            ],
            limit=1,
        ))
        period_start = get_effective_period_start(
            self.start_date,
            period_start,
            is_first_period=(self.start_date is not None and not has_existing_accruals),
        )
        if period_start > period_end:
            # Day-0 exclusion pushed the start past the period boundary — nothing
            # to accrue for this stub period (e.g. investment started on the same
            # day the period boundary falls). Not an error.
            return False

        accrual_opening_balance = opening_balance if opening_balance is not None else self.current_value
        topups_in_period = self.env["alba.investment.topup"].search([
            ("investment_id", "=", self.id),
            ("state", "=", "posted"),
            ("date", ">=", period_start),
            ("date", "<=", period_end),
        ])
        period_interest = split_period_by_topups(
            opening_balance=accrual_opening_balance,
            annual_rate=self.interest_rate,
            period_start=period_start,
            period_end=period_end,
            topups=topups_in_period,
        )

        if period_interest <= 0:
            raise UserError(
                _("Computed interest for investment %s is zero or negative.")
                % self.investment_number
            )

        payable_now, deferred_amount = split_period_for_payout_cutoff(
            period_start,
            period_end,
            interest_amount=period_interest,
        )
        accrual_vals = {
            "investment_id": self.id,
            "accrual_date": today,
            "period_start": period_start,
            "period_end": period_end,
            "opening_balance": accrual_opening_balance,
            "interest_amount": period_interest,
            "interest_amount_payable_now": payable_now,
            "interest_amount_deferred": deferred_amount,
        }
        accrual = self.env["alba.interest.accrual"].create(accrual_vals)
        accrual.action_post()

        self.message_post(
            body=_(
                "Monthly interest accrual posted: <b>%(currency)s %(amount).2f</b> "
                "for period %(start)s – %(end)s. New portfolio value: %(currency)s %(value).2f.",
                currency=self.currency_id.name,
                amount=period_interest,
                start=period_start,
                end=period_end,
                value=self.current_value,
            )
        )
        return accrual


    def action_mature(self):
        """Mark the investment as matured and open the maturity processing wizard (Rule 5)."""
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("Only active investments can be matured."))
        today = fields.Date.today()
        if (
            self.investment_type == "fixed_term"
            and self.maturity_date
            and self.maturity_date > today
        ):
            raise UserError(_(
                "This fixed-term investment matures on %s. "
                "It cannot be marked as matured before its maturity date."
            ) % self.maturity_date)

        # Mark the investment as matured first so the wizard operates on a
        # matured record (required by maturity action validation).
        self.write({"state": "matured"})
        self.message_post(body=_("Investment reached <b>Maturity</b>. Select processing option."))

        # Open the 4-option maturity processing wizard
        return {
            "name": _("Maturity Processing — %s") % self.investment_number,
            "type": "ir.actions.act_window",
            "res_model": "alba.investment.maturity.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_investment_id": self.id,
            },
        }

    def action_view_accruals(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Accruals - %s") % self.investment_number,
            "res_model": "alba.interest.accrual",
            "view_mode": "list,form",
            "domain": [("investment_id", "=", self.id)],
            "context": {"default_investment_id": self.id},
        }

    def action_view_payouts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Interest Payouts - %s") % self.investment_number,
            "res_model": "alba.interest.payout",
            "view_mode": "list,form",
            "domain": [("investment_id", "=", self.id)],
            "context": {"default_investment_id": self.id},
        }

    def action_topup(self):
        """Open the investment top-up wizard."""
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("Top-ups can only be made on active investments."))
        return {
            "name": _("Top-Up Investment"),
            "type": "ir.actions.act_window",
            "res_model": "alba.investment.topup.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_investment_id": self.id,
            },
        }

    def action_view_topups(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Top-Ups - %s") % self.investment_number,
            "res_model": "alba.investment.topup",
            "view_mode": "list,form",
            "domain": [("investment_id", "=", self.id)],
            "context": {"default_investment_id": self.id},
        }

    def action_view_payment(self):
        """Open the linked initial payment receipt."""
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_("No payment receipt has been linked yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Initial Payment Receipt"),
            "res_model": "account.payment",
            "view_mode": "form",
            "res_id": self.payment_id.id,
        }

    def action_view_withdrawal_payment(self):
        """Open the linked withdrawal payment."""
        self.ensure_one()
        if not self.withdrawal_payment_id:
            raise UserError(_("No withdrawal payment has been linked yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Withdrawal Payment"),
            "res_model": "account.payment",
            "view_mode": "form",
            "res_id": self.withdrawal_payment_id.id,
        }

    def action_pay_interest(self):
        """Open the interest-only payout wizard."""
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("Only active investments can pay out interest."))
        posted_accruals = self.accrual_ids.filtered(lambda a: a.state == "posted")
        if not posted_accruals:
            raise UserError(_(
                "There is no posted (unpaid) accrued interest on this investment. "
                "Please run the monthly accrual first."
            ))
        return {
            "name": _("Pay Accrued Interest"),
            "type": "ir.actions.act_window",
            "res_model": "alba.interest.payout.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_investment_id": self.id,
            },
        }

    def action_withdraw(self):
        """Open the investment withdrawal wizard."""
        self.ensure_one()
        today = fields.Date.today()
        if self.state not in ("active", "matured"):
            raise UserError(_("Only active or matured investments can be withdrawn."))
        if (
            self.state == "active"
            and self.investment_type == "fixed_term"
            and self.maturity_date
            and self.maturity_date > today
        ):
            if not self.withdrawal_notice_date:
                raise UserError(_("Please request early withdrawal notice before withdrawing this investment."))
            if self.earliest_withdrawal_date and self.earliest_withdrawal_date > today:
                raise UserError(
                    _(
                        "This fixed-term investment is under early-withdrawal notice. "
                        "The earliest payout date is %s."
                    )
                    % self.earliest_withdrawal_date
                )
        return {
            'name': _('Withdraw Investment'),
            'type': 'ir.actions.act_window',
            'res_model': 'alba.investment.withdraw.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_investment_id': self.id,
            }
        }

    def action_request_withdrawal_notice(self):
        """Start the company notice period for early fixed-term withdrawal."""
        self.ensure_one()
        today = fields.Date.today()
        if self.state != "active":
            raise UserError(_("Only active investments can request early withdrawal."))
        if self.investment_type != "fixed_term":
            raise UserError(_("Early withdrawal notice only applies to fixed-term investments."))
        if self.maturity_date and self.maturity_date <= today:
            raise UserError(_("This investment has already matured. Use Withdraw Investment instead."))
        if self.withdrawal_notice_date:
            raise UserError(_("Early withdrawal notice has already been requested."))

        self.write({"withdrawal_notice_date": today})
        self.message_post(
            body=_(
                "Early withdrawal notice recorded. Earliest payout date: <b>%s</b>."
            )
            % self.earliest_withdrawal_date
        )
        return True

    def action_sync_currency_rates(self):
        """Sync currency rates to accounting"""
        sync_service = self.env["alba.currency.rate.sync"]
        return sync_service.sync_rates_to_accounting()
    
    def action_create_accounting_move(self):
        """Create accounting move for investment with currency integration"""
        sync_service = self.env["alba.currency.rate.sync"]
        return sync_service.create_accounting_move_for_investment(self)

    def action_suspend(self):
        """Suspend the investment."""
        self.ensure_one()
        self.write({"state": "suspended"})
        self.message_post(body=_("Investment <b>suspended</b>."))

    def action_reactivate(self):
        """Reactivate a suspended investment."""
        self.ensure_one()
        self.write({"state": "active"})
        self.message_post(body=_("Investment <b>reactivated</b>."))

    def action_activate(self):
        """Activate a draft investment."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only draft investments can be activated."))
        self._prepare_and_validate_for_activation()
        if not self.payment_id:
            self.action_create_accounting_move()
        if not self.payment_id or self.payment_id.state not in ("posted", "in_process", "paid"):
            raise UserError(
                _("The investment accounting entry was not posted. Please review the payment journal and try again.")
            )
        self.write({"state": "active"})
        self.message_post(
            body=_(
                "Investment <b>activated</b>. Initial accounting payment posted: <b>%s</b>."
            )
            % self.payment_id.name
        )

    def _prepare_and_validate_for_activation(self):
        self.ensure_one()
        if not self.investment_product_id:
            product = self.env["alba.investment.product"]._default_product_for(
                self.investment_type,
                self.currency_id.id,
                self.company_id.id or self.env.company.id,
            )
            if product:
                self.investment_product_id = product
        if not self.investment_product_id:
            raise UserError(
                _(
                    "Please configure an investment product for %s in %s before activation."
                )
                % (
                    dict(self._fields["investment_type"].selection).get(self.investment_type),
                    self.currency_id.name,
                )
            )

        self.investment_product_id._ensure_accounting_defaults()
        self._copy_product_defaults()
        self._check_required_documents()
        self._check_required_accounting()

    def _copy_product_defaults(self):
        self.ensure_one()
        product = self.investment_product_id
        vals = {}
        for field_name in [
            "investment_type",
            "currency_id",
            "interest_rate",
            "compounding_frequency",
            "account_interest_expense_id",
            "account_interest_payable_id",
            "account_investment_liability_id",
            "account_long_term_liability_id",
            "journal_id",
            "payment_journal_id",
            "wht_rate",
            "account_wht_payable_id",
        ]:
            value = product[field_name]
            if value is not False and value is not None:
                vals[field_name] = value.id if hasattr(value, "id") else value
        if vals:
            self.write(vals)

    def action_move_to_long_term(self):
        """
        Manual action to reclassify investment from current liability to 
        long-term liability if tenure is > 1 year.
        """
        self.ensure_one()
        if not self.account_long_term_liability_id:
            raise UserError(_("Please configure a Long-term Investment Liability Account on the product first."))
        
        # Check if tenure is > 1 year (approx 365 days)
        if self.start_date and self.maturity_date:
            tenure_days = (self.maturity_date - self.start_date).days
            if tenure_days <= 365:
                raise UserError(_("This investment tenure is not greater than one year."))
        
        # Create a journal entry to move the principal
        move_vals = {
            'journal_id': self.journal_id.id,
            'date': fields.Date.today(),
            'ref': _("Long-term reclassification: %s") % self.investment_number,
            'line_ids': [
                (0, 0, {
                    'name': _("Reclassification to Long-term"),
                    'account_id': self.account_investment_liability_id.id,
                    'debit': self.principal_amount,
                    'credit': 0.0,
                    'partner_id': self.partner_id.id,
                }),
                (0, 0, {
                    'name': _("Reclassification to Long-term"),
                    'account_id': self.account_long_term_liability_id.id,
                    'debit': 0.0,
                    'credit': self.principal_amount,
                    'partner_id': self.partner_id.id,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        
        self.message_post(
            body=_("Investment principal reclassified to Long-term Liability account: %s") % move.name
        )
        return True

    def _check_required_accounting(self):
        self.ensure_one()
        missing = [
            label
            for field_name, label in [
                ("account_interest_expense_id", _("Interest Expense Account")),
                ("account_interest_payable_id", _("Interest Payable Account")),
                ("account_investment_liability_id", _("Investment Liability Account")),
                ("journal_id", _("Accrual Journal")),
                ("payment_journal_id", _("Payment Journal")),
                ("account_wht_payable_id", _("WHT Payable Account")),
            ]
            if not self[field_name]
        ]
        if missing:
            raise UserError(_("Please configure: %s") % ", ".join(missing))

    def _check_required_documents(self):
        self.ensure_one()
        required_lines = self.investment_product_id.required_document_ids
        missing = []
        for line in required_lines:
            docs = self.investor_id.document_ids.filtered(
                lambda doc, line=line: doc.document_type == line.document_type and doc.has_file
            )
            if line.require_verified:
                docs = docs.filtered(lambda doc: doc.status == "verified")
            if not docs:
                label = line.name or dict(line._fields["document_type"].selection).get(line.document_type)
                if line.require_verified:
                    label = _("%s (verified)") % label
                missing.append(label)
        if missing:
            raise UserError(
                _("Upload the mandatory investor document(s) before activation: %s")
                % ", ".join(missing)
            )

    def action_revert_to_draft(self):
        """Revert an active investment to draft for editing."""
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("Only active investments can be reverted to draft."))
        self.write({"state": "draft"})
        self.message_post(body=_("Investment reverted to <b>draft</b> for editing."))

    # =========================================================================
    # Scheduled action (cron) — accrue interest on ALL active investments
    # =========================================================================

    @api.model
    def action_accrue_all_active_investments(self):
        """
        Backward-compatible wrapper for the daily backfill accrual flow.
        """
        return self.action_backfill_missing_accruals()

    def action_recalculate_stale_accruals(self):
        """Delete and regenerate posted accruals that were computed with a
        stale opening balance (i.e. a top-up was posted after those accruals
        were already created and the top-up amount was never folded into their
        compounding base).

        SAFE GUARDS:
          - Only 'posted' accruals are ever touched.
          - If any 'paid' accrual exists in the stale range, the method raises
            UserError so a human can decide how to handle it.
          - 'reversed' accruals are left untouched.

        After running this method, call action_backfill_missing_accruals() on
        the same investments to regenerate the deleted periods with the correct
        running balance.

        Usage from Odoo shell (e.g. for IM-0072):
            inv = env['alba.investment'].search(
                [('investment_number', '=', 'IM-0072')], limit=1)
            result = inv.action_recalculate_stale_accruals()
            # inspect result['log'] for what was removed
            inv.action_backfill_missing_accruals()
        """
        import logging
        _logger = logging.getLogger(__name__)

        result_log = []

        for inv in self:
            _logger.info("action_recalculate_stale_accruals: checking %s", inv.investment_number)

            # ── Gather posted top-ups in chronological order ──────────────────
            posted_topups = self.env["alba.investment.topup"].search([
                ("investment_id", "=", inv.id),
                ("state", "=", "posted"),
            ], order="date asc")

            if not posted_topups:
                result_log.append("%s: no posted top-ups found — skipped." % inv.investment_number)
                continue

            # ── Walk each top-up and find the first stale accrual after it ───
            first_stale_period_start = None

            for topup in posted_topups:
                candidate_accruals = inv.accrual_ids.filtered(
                    lambda a, d=topup.date: a.state in ("posted", "paid") and a.period_end >= d
                ).sorted(key=lambda a: a.period_start)

                if not candidate_accruals:
                    continue

                first_after_topup = candidate_accruals[0]

                # Compute what the opening balance SHOULD have been:
                # principal + all posted top-ups up to and including this one
                # + sum of interest from paid accruals BEFORE first_after_topup
                # - sum of gross_interest from payouts BEFORE first_after_topup
                topups_up_to_now = self.env["alba.investment.topup"].search([
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("date", "<=", topup.date),
                ])
                prior_paid_accruals = inv.accrual_ids.filtered(
                    lambda a, ps=first_after_topup.period_start: (
                        a.state == "paid" and a.period_end < ps
                    )
                )
                prior_payouts = self.env["alba.interest.payout"].search([
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("payout_date", "<", first_after_topup.period_start),
                ])

                expected_opening = (
                    inv.principal_amount
                    + sum(topups_up_to_now.mapped("amount"))
                    + sum(prior_paid_accruals.mapped("interest_amount"))
                    - sum(prior_payouts.mapped("gross_interest"))
                )

                # Round to 2dp for float comparison
                actual_opening = round(first_after_topup.opening_balance, 2)
                expected_rounded = round(expected_opening, 2)

                if abs(actual_opening - expected_rounded) < 0.02:
                    # Opening balance is already correct — this top-up was
                    # accounted for (e.g. accruals were created after the fix)
                    result_log.append(
                        "%s: top-up %s (%.2f on %s) — first subsequent accrual "
                        "opening balance %.2f matches expected %.2f — OK, skipped."
                        % (inv.investment_number, topup.name, topup.amount,
                           topup.date, actual_opening, expected_rounded)
                    )
                    continue

                # Discrepancy found — determine the range of stale accruals
                # (all posted accruals from first_stale_period_start onward)
                stale_cutoff = first_after_topup.period_start
                if first_stale_period_start is None or stale_cutoff < first_stale_period_start:
                    first_stale_period_start = stale_cutoff

                result_log.append(
                    "%s: top-up %s (%.2f on %s) introduced discrepancy — "
                    "first stale accrual period_start=%s "
                    "(actual opening=%.2f, expected=%.2f, diff=%.2f)"
                    % (inv.investment_number, topup.name, topup.amount, topup.date,
                       stale_cutoff, actual_opening, expected_rounded,
                       expected_rounded - actual_opening)
                )

            if first_stale_period_start is None:
                result_log.append("%s: all accrual opening balances are correct — nothing to do." % inv.investment_number)
                continue

            # ── Identify ALL stale accruals from the cutoff onward ────────────
            stale_accruals = inv.accrual_ids.filtered(
                lambda a, cs=first_stale_period_start: a.period_start >= cs
            ).sorted(key=lambda a: a.period_start)

            # Safety: abort if ANY paid accrual is in the stale range —
            # deleting paid accruals could leave the accounting in an
            # inconsistent state; a human must resolve this manually.
            stale_paid = stale_accruals.filtered(lambda a: a.state == "paid")
            if stale_paid:
                paid_refs = ", ".join(
                    "%s (%s)" % (a.display_name, a.period_start)
                    for a in stale_paid
                )
                raise UserError(_(
                    "Cannot recalculate stale accruals for %(inv)s:\n"
                    "The following accruals in the stale range are in 'paid' state "
                    "and cannot be safely deleted:\n%(refs)s\n\n"
                    "Please reverse these payouts and their accruals manually before "
                    "running this method.",
                    inv=inv.investment_number,
                    refs=paid_refs,
                ))

            # Only delete 'posted' accruals (reversed are left alone)
            stale_posted = stale_accruals.filtered(lambda a: a.state == "posted")

            result_log.append(
                "%s: deleting %d stale posted accrual(s) from %s onward."
                % (inv.investment_number, len(stale_posted), first_stale_period_start)
            )

            for accrual in stale_posted:
                result_log.append(
                    "  → removing %s (period %s–%s, opening=%.2f, interest=%.2f)"
                    % (accrual.display_name, accrual.period_start, accrual.period_end,
                       accrual.opening_balance, accrual.interest_amount)
                )
                if accrual.move_id:
                    if accrual.move_id.state == "posted":
                        accrual.move_id.button_cancel()
                    accrual.move_id.unlink()

            stale_posted.unlink()

            result_log.append(
                "%s: done. Run action_backfill_missing_accruals() to regenerate "
                "the deleted periods with correct opening balances." % inv.investment_number
            )

        log_str = "\n".join(result_log)
        _logger.info("action_recalculate_stale_accruals result:\n%s", log_str)
        return {"log": log_str, "result_lines": result_log}


    @api.model
    def action_backfill_missing_accruals(self, as_of_date=None):
        """Generate any missing monthly accruals for active investments.

        Each investment is processed inside its own database savepoint so that
        a failure on one investment does not roll back accruals already posted
        for others.  All errors are collected and surfaced to the user at the
        end via UserError so nothing is swallowed silently.
        """

        import logging
        _logger = logging.getLogger(__name__)

        as_of_date = fields.Date.to_date(as_of_date) if as_of_date else fields.Date.today()
        errors = []

        for inv in self.search([("state", "=", "active")]):
            product = inv.investment_product_id
            if not product:
                continue

            target_day = product.auto_accrual_day or 28
            cutoff_day = product.after_cutoff_day if product.after_cutoff_day else 15
            start_date = inv.start_date or as_of_date

            _logger.info(
                "Backfill: processing %s (start=%s, cutoff_day=%d)",
                inv.investment_number, inv.start_date, cutoff_day,
            )

            try:
                # Re-derive the true opening balance for each period from first principles.
                # This uses: principal + all posted top-ups up to period_start +
                # sum(interest_amount of prior accruals that are still 'posted').
                # Paid accruals are excluded so their interest does not compound.

                for accrual_date, period_start, period_end in iter_missing_accrual_periods(
                    start_date, as_of_date, target_day,
                    investment_start=inv.start_date,
                    cutoff_day=cutoff_day,
                    env=self.env,
                ):
                    existing = self.env["alba.interest.accrual"].search(
                        [
                            ("investment_id", "=", inv.id),
                            ("period_start", "=", period_start),
                            ("period_end", "=", period_end),
                            ("state", "in", ["posted", "draft", "paid", "reversed"]),
                        ],
                        limit=1,
                    )

                    # Compute principal + posted top-ups strictly BEFORE period_start
                    topups_prior = self.env["alba.investment.topup"].search([
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("date", "<", period_start),
                    ])
                    base_before_period = inv.principal_amount + sum(topups_prior.mapped("amount"))

                    # Add interest from prior accruals that are still unpaid ('posted')
                    prior_unpaid_accruals = self.env["alba.interest.accrual"].search([
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("period_end", "<", period_start),
                    ])
                    running_balance = base_before_period + sum(prior_unpaid_accruals.mapped("interest_amount"))

                    if existing:
                        # Period already exists — nothing to recreate. Skip.
                        continue

                    opening_balance = running_balance

                    _logger.info(
                        "Backfill %s period %s-%s: current_value=%.2f (principal=%.2f topup=%.2f outstanding=%.2f)",
                        inv.investment_number, period_start, period_end,
                        inv.current_value, inv.principal_amount, inv.total_topup_amount,
                        inv.total_interest_outstanding,
                    )

                    # Each period gets its own savepoint so a mid-investment
                    # failure doesn't roll back periods already posted.
                    with self.env.cr.savepoint():
                        accrual = inv.action_accrue_monthly_interest(
                            accrual_date=accrual_date,
                            opening_balance=opening_balance,
                            period_start=period_start,
                            period_end=period_end,
                        )
                        # We do not rely on chained closing_balance values from
                        # existing accruals; running_balance is re-derived each
                        # iteration above when needed.

            except Exception as exc:
                _logger.error(
                    "Backfill: failed for investment %s — %s",
                    inv.investment_number, exc,
                    exc_info=True,
                )
                errors.append("%s: %s" % (inv.investment_number, exc))

        if errors:
            raise UserError(
                _("Interest accrual backfill failed for %d investment(s):\n\n%s")
                % (len(errors), "\n".join("• %s" % e for e in errors))
            )
        return True

    @api.model
    def action_remediate_rule3_violations(self):
        """
        Server Action / Remediation Utility for Business Rule 3 (After-15th Cutoff).

        Finds active/matured investments where start_date.day > cutoff_day (default 15).
        Inspects posted accruals to detect any invalid accrual created for the initial
        receipt month cycle (period_start < first_eligible_accrual_start).

        Remediation steps for affected investments:
        1. Reverse the invalid initial accruals and unpost/reverse their journal entries.
        2. Recalculate opening balances and interest for subsequent posted accruals
           so compounding balances are 100% mathematically accurate.
        """
        import logging
        _logger = logging.getLogger(__name__)

        target_investments = self if self else self.search([("state", "in", ["active", "matured"])])
        remediated_count = 0
        result_logs = []

        for inv in target_investments:
            if not inv.start_date:
                continue

            cutoff_day = (
                inv.investment_product_id.after_cutoff_day
                if inv.investment_product_id and inv.investment_product_id.after_cutoff_day
                else 15
            )
            if inv.start_date.day <= cutoff_day:
                continue

            first_eligible_start = get_first_eligible_accrual_start(inv.start_date, cutoff_day=cutoff_day)
            if not first_eligible_start:
                continue

            # Identify invalid posted accruals prior to first_eligible_start
            invalid_accruals = inv.accrual_ids.filtered(
                lambda a, fes=first_eligible_start: a.state == "posted" and a.period_start < fes
            ).sorted(key=lambda a: a.period_start)

            if not invalid_accruals:
                continue

            remediated_count += 1
            inv_log = ["Remediating Rule 3 violations for %s (start_date=%s):" % (inv.investment_number, inv.start_date)]

            # 1. Reverse invalid accruals
            for accrual in invalid_accruals:
                reason = "Remediation: Rule 3 (After-15th Cutoff) violation — start_date %s" % inv.start_date
                accrual.write({"reversal_reason": reason})
                try:
                    accrual.action_reverse()
                    inv_log.append("  → Reversed invalid accrual %s (period %s to %s, interest %.2f)" % (
                        accrual.display_name, accrual.period_start, accrual.period_end, accrual.interest_amount
                    ))
                except Exception as e:
                    if accrual.move_id and accrual.move_id.state == "posted":
                        accrual.move_id.button_cancel()
                    accrual.write({"state": "reversed"})
                    inv_log.append("  → Unposted move & reversed %s (%s)" % (accrual.display_name, e))

            # 2. Recalculate subsequent posted accruals sequentially
            subsequent_accruals = inv.accrual_ids.filtered(
                lambda a, fes=first_eligible_start: a.state == "posted" and a.period_start >= fes
            ).sorted(key=lambda a: a.period_start)

            for acc in subsequent_accruals:
                topups = self.env["alba.investment.topup"].search([
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("date", "<=", acc.period_start),
                ])
                base = inv.principal_amount + sum(topups.mapped("amount"))

                prior_posted = inv.accrual_ids.filtered(
                    lambda a, ps=acc.period_start, fes=first_eligible_start: (
                        a.state == "posted" and fes <= a.period_start < ps
                    )
                )
                expected_opening = base + sum(prior_posted.mapped("interest_amount"))
                monthly_rate = inv.interest_rate / 100.0 / 12.0

                total_days = 30
                actual_days = (acc.period_end - acc.period_start).days + 1
                if actual_days < total_days:
                    expected_interest = round(expected_opening * monthly_rate * actual_days / total_days, 2)
                else:
                    expected_interest = round(expected_opening * monthly_rate, 2)

                if round(acc.opening_balance, 2) != round(expected_opening, 2) or round(acc.interest_amount, 2) != round(expected_interest, 2):
                    inv_log.append("  → Recalculated %s: opening %.2f -> %.2f, interest %.2f -> %.2f" % (
                        acc.display_name, acc.opening_balance, expected_opening, acc.interest_amount, expected_interest
                    ))
                    if acc.move_id:
                        if acc.move_id.state == "posted":
                            acc.move_id.button_cancel()
                        acc.move_id.unlink()
                        acc.write({"move_id": False})

                    acc.write({
                        "opening_balance": expected_opening,
                        "interest_amount": expected_interest,
                        "closing_balance": expected_opening + expected_interest,
                        "state": "draft",
                    })
                    acc.action_post()

            inv._compute_financials()
            result_logs.append("\n".join(inv_log))

        full_log = "\n\n".join(result_logs) if result_logs else "No Rule 3 violations found."
        _logger.info("action_remediate_rule3_violations:\n%s", full_log)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Rule 3 Remediation Complete"),
                "message": _("Successfully remediated %d investment(s).") % remediated_count,
                "sticky": False,
            },
        }

    @api.model
    def action_run_automated_interest_accrual(self):
        """
        Called by a daily cron job to accrue interest on all active investments.
        Step 1: run a lightweight self-repair across all active investments to
        detect and correct stale posted accrual chains (top-ups not folded in).
        Any investment that requires manual review (e.g. a 'paid' accrual sits
        inside the stale range) is logged and skipped without aborting the
        cron so other investments continue to be processed.

        Step 2: delegates to action_backfill_missing_accruals, which iterates
        every active investment month-by-month from its start_date through today,
        posting any missing accruals (including catch-ups) and skipping
        periods that already have a posted record.
        """
        import logging
        _logger = logging.getLogger(__name__)

        today = fields.Date.context_today(self)

        repair_errors = []
        repaired = []

        active_investments = self.search([("state", "=", "active")])
        for inv in active_investments:
            try:
                with self.env.cr.savepoint():
                    result = inv.action_recalculate_stale_accruals()

                log = (result or {}).get("log", "")
                if log and "nothing to do" not in log and "no posted top-ups" not in log:
                    repaired.append(log)
                    _logger.info(
                        "Automated accrual repair: %s\n%s",
                        inv.investment_number, log,
                    )
            except UserError as e:
                # Expected manual-review case: a paid accrual sits inside the stale range.
                repair_errors.append("%s: %s" % (inv.investment_number, str(e)))
                _logger.warning(
                    "Automated accrual repair skipped for %s — manual review needed: %s",
                    inv.investment_number, str(e),
                )
            except Exception as exc:
                repair_errors.append("%s: unexpected error — %s" % (inv.investment_number, exc))
                _logger.error(
                    "Automated accrual repair failed unexpectedly for %s — %s",
                    inv.investment_number, exc, exc_info=True,
                )

        if repair_errors:
            _logger.warning(
                "Automated accrual repair: %d investment(s) need manual review:\n%s",
                len(repair_errors), "\n".join(repair_errors),
            )

        # Step 2: existing backfill behavior, unchanged.
        return self.action_backfill_missing_accruals(as_of_date=today)

    @api.model
    def action_check_maturing_investments(self):
        """Daily cron to find investments maturing in 7 days and notify investors."""
        from dateutil.relativedelta import relativedelta
        reminder_date = fields.Date.today() + relativedelta(days=7)
        maturing = self.search([
            ("state", "=", "active"),
            ("investment_type", "=", "fixed_term"),
            ("maturity_date", "=", reminder_date)
        ])
        for inv in maturing:
            inv._send_maturity_notification()
        return True

    def _send_maturity_notification(self):
        """Helper to send maturity reminder email/SMS."""
        self.ensure_one()
        template = self.env.ref("alba_investors.email_template_investment_maturing", raise_if_not_found=False)
        if template and self.investor_id.partner_id.email:
            template.send_mail(self.id, force_send=False)
            self.message_post(body=_("Maturity reminder email sent to investor."))

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("investment_number", _("New")) == _("New"):
                vals["investment_number"] = seq.next_by_code(
                    "alba.investment.seq"
                ) or _("New")
            product = self.env["alba.investment.product"].browse(vals.get("investment_product_id"))
            if not product:
                investor = self.env["alba.investor"].browse(vals.get("investor_id"))
                currency_id = vals.get("currency_id") or investor.currency_id.id or self.env.company.currency_id.id
                company_id = investor.company_id.id or self.env.company.id
                product = self.env["alba.investment.product"]._default_product_for(
                    vals.get("investment_type", "fixed_term"),
                    currency_id,
                    company_id,
                )
                if product:
                    vals["investment_product_id"] = product.id
            if product:
                vals.setdefault("investment_type", product.investment_type)
                vals.setdefault("currency_id", product.currency_id.id)
                vals.setdefault("interest_rate", product.interest_rate)
                vals.setdefault("compounding_frequency", product.compounding_frequency)
                vals.setdefault("account_interest_expense_id", product.account_interest_expense_id.id)
                vals.setdefault("account_interest_payable_id", product.account_interest_payable_id.id)
                vals.setdefault("account_investment_liability_id", product.account_investment_liability_id.id)
                vals.setdefault("journal_id", product.journal_id.id)
                vals.setdefault("payment_journal_id", product.payment_journal_id.id)
                vals.setdefault("wht_rate", product.wht_rate)
                vals.setdefault("account_wht_payable_id", product.account_wht_payable_id.id)
        records = super(AlbaInvestment, self).create(vals_list)
        return records

    def write(self, vals):
        # Prevent editing key fields when investment is active
        editable_active_fields = {
            "notes",
            "state",
            "payment_id",
            "withdrawal_payment_id",
            "withdrawal_notice_date",
        }
        protected_fields = set(vals) - editable_active_fields
        if protected_fields:
            active_records = self.filtered(lambda rec: rec.state == "active")
            if active_records:
                raise UserError(
                    _(
                        "Cannot edit investment while it is active. "
                        "Please revert to draft state first to make changes."
                    )
                )
        if 'state' in vals:
            for rec in self:
                if rec.state != vals['state']:
                    rec._log_professional_status_change(rec.state, vals['state'])
        return super(AlbaInvestment, self).write(vals)

    def _log_professional_status_change(self, old_state, new_state):
        """Post a professional, formatted message to the chatter on status change."""
        state_labels = dict(self._fields['state'].selection)
        old_label = state_labels.get(old_state, old_state)
        new_label = state_labels.get(new_state, new_state)
        
        icon = "📈" if new_state == "active" else "ℹ️"
        if new_state == "draft": icon = "📝"
        if new_state == "matured": icon = "🔔"
        if new_state == "withdrawn": icon = "💸"
        if new_state == "suspended": icon = "⚠️"
        
        body = _(
            "<div class='o_alba_status_change'>"
            "<strong>%s Investment Status Changed</strong><br/>"
            "From: <span class='badge badge-secondary'>%s</span> "
            "To: <span class='badge badge-primary' style='background-color: #004a99;'>%s</span><br/>"
            "Changed by: %s"
            "</div>"
        ) % (icon, old_label.upper(), new_label.upper(), self.env.user.name)
        
        self.message_post(body=body, subtype_xmlid="mail.mt_comment")

    def name_get(self):
        return [
            (
                rec.id,
                "[%s] %s" % (rec.investment_number, rec.investor_id.investor_name),
            )
            for rec in self
        ]

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
        """
        Allow Odoo's CSV importer to resolve investment_id by a bare investment_number
        (e.g. 'INV-0001'), which is what the export column investment_id/investment_number
        contains. Falls back to the full display name search for UI autocomplete.
        """
        domain = list(domain or [])
        if name:
            domain = ['|',
                ('investment_number', '=', name),
                ('investment_number', operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)

    @api.model
    def _get_default_list_export_fields(self):
        # IMPORT-EXPORT FIX: export investment_number as the import key for investment_id.
        # investor_id, partner_id, currency_id, company_id are all derived from
        # investment_id — they are readonly on import and must not be included as
        # separate columns.
        return [
            "investment_number",
            "investor_id/investor_number",
            "start_date",
            "maturity_date",
            "investment_type",
            "principal_amount",
            "interest_rate",
            "compounding_frequency",
            "state",
        ]

    @api.model
    def _check_company(self, company_id):
        """Ensure company consistency for multi-company setup"""
        if company_id:
            self.company_id = company_id
