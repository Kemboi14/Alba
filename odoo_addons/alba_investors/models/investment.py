# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .accrual_backfill import iter_missing_accrual_periods


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
    accrual_count = fields.Integer(
        string="Accruals",
        compute="_compute_accrual_count",
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
        "accrual_ids",
        "accrual_ids.state",
        "accrual_ids.interest_amount",
    )
    def _compute_financials(self):
        for rec in self:
            posted_accruals = rec.accrual_ids.filtered(lambda a: a.state == "posted")
            total_accrued = sum(posted_accruals.mapped("interest_amount"))
            rec.total_interest_accrued = total_accrued
            rec.total_interest_paid = 0.0
            rec.current_value = rec.principal_amount + total_accrued

    # IMPORT-EXPORT FIX: no-op inverses — import can write these fields; compute resets them on trigger
    def _inverse_current_value(self): pass
    def _inverse_total_interest_accrued(self): pass
    def _inverse_total_interest_paid(self): pass

    @api.depends("total_interest_accrued", "principal_amount", "wht_rate")
    def _compute_wht_amount(self):
        for rec in self:
            rec.wht_amount = rec.total_interest_accrued * (rec.wht_rate / 100.0)
            rec.net_interest_payable = rec.total_interest_accrued - rec.wht_amount
            rec.net_payout_amount = rec.principal_amount + rec.net_interest_payable

    # IMPORT-EXPORT FIX: no-op inverses for WHT fields
    def _inverse_wht_amount(self): pass
    def _inverse_net_interest_payable(self): pass
    def _inverse_net_payout_amount(self): pass

    def _compute_accrual_count(self):
        for rec in self:
            rec.accrual_count = len(rec.accrual_ids)

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

    def action_accrue_monthly_interest(self, accrual_date=None, opening_balance=None):
        """
        Accrue one month's compound interest on this investment.
        Creates an alba.interest.accrual record and posts its journal entry.
        Returns the new accrual record.
        """
        self.ensure_one()
        if self.state != "active":
            raise UserError(
                _("Cannot accrue interest on investment %s — status is '%s'.")
                % (self.investment_number, self.state)
            )

        today = fields.Date.to_date(accrual_date) if accrual_date else fields.Date.today()
        period_interest = self.compute_compound_interest_for_period(opening_balance=opening_balance)

        if period_interest <= 0:
            raise UserError(
                _("Computed interest for investment %s is zero or negative.")
                % self.investment_number
            )

        # Determine period start/end (previous month start → today)
        import calendar

        month = today.month - 1 or 12
        year = today.year if today.month > 1 else today.year - 1
        last_day = calendar.monthrange(year, month)[1]
        from datetime import date

        period_start = date(year, month, 1)
        period_end = date(year, month, last_day)

        existing = self.env["alba.interest.accrual"].search(
            [
                ("investment_id", "=", self.id),
                ("period_start", "=", period_start),
                ("period_end", "=", period_end),
                ("state", "=", "posted"),
            ],
            limit=1,
        )
        if existing:
            return False

        accrual_opening_balance = opening_balance if opening_balance is not None else self.current_value
        accrual_vals = {
            "investment_id": self.id,
            "accrual_date": today,
            "period_start": period_start,
            "period_end": period_end,
            "opening_balance": accrual_opening_balance,
            "interest_amount": period_interest,
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
        """Mark the investment as matured."""
        self.ensure_one()
        self.write({"state": "matured"})
        self.message_post(body=_("Investment marked as <b>Matured</b>."))

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
        Called by the monthly cron on the 1st of each month.
        Accrues compound interest on every active investment.
        """
        active_investments = self.search([("state", "=", "active")])
        errors = []
        for inv in active_investments:
            try:
                inv.action_accrue_monthly_interest()
            except Exception as e:
                errors.append("Investment %s: %s" % (inv.investment_number, str(e)))

        if errors:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(
                "alba.investment: Monthly accrual completed with errors:\n%s",
                "\n".join(errors),
            )
        return True

    @api.model
    def action_backfill_missing_accruals(self, as_of_date=None):
        """Generate any missing monthly accruals for active investments."""
        as_of_date = fields.Date.to_date(as_of_date) if as_of_date else fields.Date.today()
        errors = []

        for inv in self.search([("state", "=", "active")]):
            product = inv.investment_product_id
            if not product:
                continue

            target_day = product.auto_accrual_day or 28
            if as_of_date.day < target_day:
                continue

            start_date = inv.start_date or as_of_date
            try:
                for run_date, period_start, period_end in iter_missing_accrual_periods(
                    start_date, as_of_date, target_day
                ):
                    existing = self.env["alba.interest.accrual"].search(
                        [
                            ("investment_id", "=", inv.id),
                            ("period_start", "=", period_start),
                            ("period_end", "=", period_end),
                            ("state", "=", "posted"),
                        ],
                        limit=1,
                    )
                    if existing:
                        continue

                    prior_accruals = self.env["alba.interest.accrual"].search(
                        [
                            ("investment_id", "=", inv.id),
                            ("state", "=", "posted"),
                            ("period_end", "<", period_start),
                        ],
                        order="period_end asc",
                    )
                    opening_balance = inv.principal_amount + sum(prior_accruals.mapped("interest_amount"))
                    inv.action_accrue_monthly_interest(accrual_date=run_date, opening_balance=opening_balance)
            except Exception as exc:
                errors.append("Investment %s: %s" % (inv.investment_number, str(exc)))

        if errors:
            _logger = __import__("logging").getLogger(__name__)
            _logger.warning(
                "alba.investment: Backfill missing accruals completed with errors:\n%s",
                "\n".join(errors),
            )
        return True

    @api.model
    def action_run_automated_interest_accrual(self):
        """
        Called by a daily cron job to accrue interest on all active investments.

        Delegates entirely to action_backfill_missing_accruals, which iterates
        every active investment month-by-month from its start_date through today,
        posting any missing accruals (including January catch-ups) and skipping
        periods that already have a posted record.
        """
        today = fields.Date.context_today(self)
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
