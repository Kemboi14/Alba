# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AlbaInterestAccrual(models.Model):
    _name = "alba.interest.accrual"
    _description = "Alba Capital Investment Interest Accrual"
    _inherit = ["mail.thread"]
    _rec_name = "display_name"
    _order = "accrual_date desc, id desc"

    # ── Display ───────────────────────────────────────────────────────────────
    display_name = fields.Char(
        string="Reference",
        compute="_compute_display_name",
        store=True,
        # IMPORT-EXPORT FIX: store=True ensures _rec_name is resolvable during import
    )

    # ── Investment Link ───────────────────────────────────────────────────────
    investment_id = fields.Many2one(
        "alba.investment",
        string="Investment",
        required=True,
        ondelete="cascade",
        tracking=True,
        index=True,
    )
    investor_id = fields.Many2one(
        "alba.investor",
        string="Investor",
        related="investment_id.investor_id",
        store=True,
        readonly=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="investment_id.investor_id.partner_id",
        store=True,
        readonly=True,
    )
    investment_product_id = fields.Many2one(
        "alba.investment.product",
        string="Investment Product",
        related="investment_id.investment_product_id",
        store=True,
        readonly=True,
    )
    interest_rate = fields.Float(
        string="Annual Interest Rate (%)",
        related="investment_id.interest_rate",
        readonly=True,
    )

    # ── Period ────────────────────────────────────────────────────────────────
    accrual_date = fields.Date(
        string="Accrual Date",
        required=True,
        default=fields.Date.today,
        index=True,
        tracking=True,
    )
    period_start = fields.Date(
        string="Period Start",
        required=True,
    )
    period_end = fields.Date(
        string="Closing Date",
        required=True,
    )

    # ── Amounts ───────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="investment_id.currency_id",
        store=True,
        readonly=True,
    )
    opening_balance = fields.Monetary(
        string="Opening Balance",
        currency_field="currency_id",
        required=True,
        tracking=True,
        help="Investment value at the start of the accrual period.",
    )
    interest_amount = fields.Monetary(
        string="Interest Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
        help="Compound interest accrued for this period.",
    )
    closing_balance = fields.Monetary(
        string="Closing Balance",
        currency_field="currency_id",
        compute="_compute_closing_balance",
        inverse="_inverse_closing_balance",
        store=True,
        help="Opening balance + accrued interest.",
        # IMPORT-EXPORT FIX: inverse allows Odoo import to write this field; compute still runs on triggers
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("paid", "Paid Out"),
            ("reversed", "Reversed"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )

    # ── Payout Link ───────────────────────────────────────────────────────────
    interest_payout_id = fields.Many2one(
        "alba.interest.payout",
        string="Interest Payout",
        readonly=True,
        copy=False,
        help="The interest payout that cleared this accrual.",
    )

    # ── Accounting ────────────────────────────────────────────────────────────
    move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
        readonly=True,
        copy=False,
    )
    reversal_move_id = fields.Many2one(
        "account.move",
        string="Reversal Journal Entry",
        readonly=True,
        copy=False,
    )

    # ── Company ───────────────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="investment_id.company_id",
        store=True,
        readonly=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Char(string="Notes")
    reversal_reason = fields.Text(string="Reversal Reason")

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _interest_amount_positive = models.Constraint(
        "CHECK(interest_amount > 0)",
        "Interest amount must be greater than zero.",
    )
    _opening_balance_non_negative = models.Constraint(
        "CHECK(opening_balance >= 0)",
        "Opening balance cannot be negative.",
    )
    _period_dates_check = models.Constraint(
        "CHECK(period_end >= period_start)",
        "Period end date must be on or after period start date.",
    )

    # =========================================================================
    # Computed methods
    # =========================================================================

    @api.model
    def _check_company(self, company_id):
        """Ensure company consistency for multi-company setup"""
        if company_id:
            self.company_id = company_id

    @api.depends("investment_id", "accrual_date", "period_start", "period_end")
    def _compute_display_name(self):
        for rec in self:
            inv_num = rec.investment_id.investment_number if rec.investment_id else "?"
            period = ""
            if rec.period_start and rec.period_end:
                period = " (%s – %s)" % (
                    rec.period_start.strftime("%b %Y"),
                    rec.period_end.strftime("%b %Y"),
                )
            rec.display_name = "Accrual — %s%s" % (inv_num, period)

    @api.depends("opening_balance", "interest_amount")
    def _compute_closing_balance(self):
        for rec in self:
            rec.closing_balance = rec.opening_balance + rec.interest_amount

    def _inverse_closing_balance(self):
        # IMPORT-EXPORT FIX: no-op inverse — allows import to write closing_balance;
        # the value is always recomputed from opening_balance + interest_amount on next trigger.
        pass

    @api.onchange('investment_id')
    def _onchange_investment_id(self):
        """Auto-fill period dates, opening balance and interest when investment is selected."""
        if not self.investment_id:
            return
        import calendar
        inv = self.investment_id
        today = fields.Date.context_today(self)

        self.accrual_date = today
        self.period_start = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        self.period_end = today.replace(day=last_day)

        # Opening balance = closing balance of last posted accrual, or principal if none
        last_accrual = self.env['alba.interest.accrual'].search([
            ('investment_id', '=', inv.id),
            ('state', '=', 'posted'),
        ], order='period_end desc', limit=1)

        if last_accrual:
            self.opening_balance = last_accrual.closing_balance
        else:
            self.opening_balance = inv.principal_amount

        if inv.interest_rate:
            monthly_rate = inv.interest_rate / 100.0 / 12.0
            self.interest_amount = round(self.opening_balance * monthly_rate, 2)
            self.closing_balance = self.opening_balance + self.interest_amount

    @api.onchange('opening_balance')
    def _onchange_opening_balance(self):
        """Recalculate interest amount when opening balance is changed manually."""
        if self.investment_id and self.investment_id.interest_rate:
            monthly_rate = self.investment_id.interest_rate / 100.0 / 12.0
            self.interest_amount = round(self.opening_balance * monthly_rate, 2)
            self.closing_balance = self.opening_balance + self.interest_amount

    # =========================================================================
    # Constraint methods
    # =========================================================================

    @api.constrains("period_start", "period_end")
    def _check_period_dates(self):
        for rec in self:
            if rec.period_start and rec.period_end:
                if rec.period_end < rec.period_start:
                    raise ValidationError(
                        _("Period end date must be on or after period start date.")
                    )

    @api.constrains("interest_amount")
    def _check_interest_amount(self):
        for rec in self:
            if rec.interest_amount <= 0:
                raise ValidationError(_("Interest amount must be greater than zero."))

    # =========================================================================
    # Business Logic
    # =========================================================================

    def action_post(self):
        """
        Post the interest accrual with WHT split:

        When WHT is configured on the investment:
            DR  Interest Expense Account        (gross interest_amount)
            CR  WHT Payable Account             (wht_rate% of interest)
            CR  Interest Payable Account        (net interest after WHT)

        When WHT is NOT configured (safe fallback):
            DR  Interest Expense Account        (interest_amount)
            CR  Interest Payable Account        (interest_amount)
        """
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    _("Only draft accruals can be posted. '%s' is already %s.")
                    % (rec.display_name, rec.state)
                )

            investment = rec.investment_id

            # Validate accounting configuration
            if not investment.account_interest_expense_id:
                raise UserError(
                    _(
                        "Please configure the Interest Expense account on investment '%s' "
                        "before posting the accrual."
                    )
                    % investment.investment_number
                )
            if not investment.account_interest_payable_id:
                raise UserError(
                    _(
                        "Please configure the Interest Payable account on investment '%s' "
                        "before posting the accrual."
                    )
                    % investment.investment_number
                )

            journal = investment.journal_id
            if not journal:
                # Fall back to first general journal in the company
                journal = rec.env["account.journal"].search(
                    [
                        ("type", "=", "general"),
                        ("company_id", "=", rec.company_id.id),
                    ],
                    limit=1,
                )
            if not journal:
                raise UserError(
                    _(
                        "No General journal found for company '%s'. "
                        "Please create one or configure the Accrual Journal on investment '%s'."
                    )
                    % (rec.company_id.name, investment.investment_number)
                )

            # Convert interest amount to company currency when accrual currency differs
            # FIX: ensure debit/credit in company currency are set using Odoo's conversion
            amount_in_company = rec.currency_id._convert(
                rec.interest_amount,
                rec.company_id.currency_id,
                rec.company_id,
                rec.accrual_date or fields.Date.today(),
            )

            # ── WHT split calculation ─────────────────────────────────────────
            # If the investment has WHT configured, split the CR into:
            #   CR WHT Payable  (tax portion)
            #   CR Interest Payable  (net = gross - wht)
            # Otherwise the full gross goes to Interest Payable.
            wht_rate = investment.wht_rate or 0.0
            wht_account = investment.account_wht_payable_id
            use_wht_split = bool(wht_rate > 0 and wht_account)

            wht_amount = round(rec.interest_amount * (wht_rate / 100.0), 2) if use_wht_split else 0.0
            net_interest = rec.interest_amount - wht_amount

            # Convert to company currency
            wht_amount_company = rec.currency_id._convert(
                wht_amount, rec.company_id.currency_id,
                rec.company_id, rec.accrual_date or fields.Date.today(),
            ) if use_wht_split else 0.0
            net_interest_company = amount_in_company - wht_amount_company

            # ── Build journal lines ───────────────────────────────────────────
            period_label = rec.period_start.strftime("%b %Y") if rec.period_start else ""

            credit_lines = []
            if use_wht_split:
                # CR WHT Payable
                credit_lines.append((0, 0, {
                    "account_id": wht_account.id,
                    "name": _(
                        "WHT on interest — %(inv)s — %(period)s",
                        inv=investment.investment_number, period=period_label,
                    ),
                    "debit": 0.0,
                    "credit": wht_amount_company,
                    "amount_currency": -wht_amount,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))
                # CR Net Interest Payable
                credit_lines.append((0, 0, {
                    "account_id": investment.account_interest_payable_id.id,
                    "name": _(
                        "Net interest payable — %(inv)s — %(period)s",
                        inv=investment.investment_number, period=period_label,
                    ),
                    "debit": 0.0,
                    "credit": net_interest_company,
                    "amount_currency": -net_interest,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))
            else:
                # CR Gross Interest Payable (no WHT)
                credit_lines.append((0, 0, {
                    "account_id": investment.account_interest_payable_id.id,
                    "name": _(
                        "Interest payable — %(inv)s — %(period)s",
                        inv=investment.investment_number, period=period_label,
                    ),
                    "debit": 0.0,
                    "credit": amount_in_company,
                    "amount_currency": -rec.interest_amount,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))

            move_vals = {
                "journal_id": journal.id,
                "date": rec.accrual_date,
                "ref": "ACCR/%s/%s" % (
                    investment.investment_number,
                    rec.accrual_date.strftime("%Y%m") if rec.accrual_date else "",
                ),
                "narration": _(
                    "Monthly compound interest accrual — %(investment)s — %(period)s",
                    investment=investment.investment_number,
                    period="%s to %s" % (rec.period_start, rec.period_end),
                ),
                "currency_id": rec.currency_id.id,
                "line_ids": [
                    # DR Interest Expense (gross)
                    (0, 0, {
                        "account_id": investment.account_interest_expense_id.id,
                        "name": _(
                            "Interest expense — %(inv)s — %(period)s",
                            inv=investment.investment_number, period=period_label,
                        ),
                        "debit": amount_in_company,
                        "credit": 0.0,
                        "amount_currency": rec.interest_amount,
                        "currency_id": rec.currency_id.id,
                        "partner_id": rec.partner_id.id,
                    }),
                ] + credit_lines,
            }
            move = rec.env["account.move"].create(move_vals)
            move.action_post()

            rec.write({"state": "posted", "move_id": move.id})
            wht_msg = (
                _(", WHT: <b>%(currency)s %(wht).2f</b>, Net: <b>%(currency)s %(net).2f</b>",
                  currency=rec.currency_id.name, wht=wht_amount, net=net_interest)
                if use_wht_split else ""
            )
            rec.message_post(
                body=_(
                    "Accrual posted: <b>%(currency)s %(amount).2f</b>%(wht_info)s. "
                    "Journal entry: <b>%(move)s</b>.",
                    currency=rec.currency_id.name,
                    amount=rec.interest_amount,
                    wht_info=wht_msg,
                    move=move.name,
                )
            )

        return True

    def action_reverse(self):
        """Reverse a posted accrual and its journal entry."""
        self.ensure_one()
        if self.state not in ("posted",):
            raise UserError(_("Only posted accruals can be reversed."))
        if not self.reversal_reason:
            return {
                "name": _("Reason for Reversal"),
                "type": "ir.actions.act_window",
                "res_model": "alba.interest.accrual.reverse.wizard",
                "view_mode": "form",
                "view_id": self.env.ref("alba_investors.view_alba_interest_accrual_reverse_wizard_form").id,
                "target": "new",
                "context": {
                    "default_accrual_id": self.id,
                }
            }

        if self.move_id:
            reversal = self.move_id._reverse_moves(
                [
                    {
                        "date": fields.Date.today(),
                        "journal_id": self.move_id.journal_id.id,
                        "reason": self.reversal_reason,
                    }
                ]
            )
            reversal.action_post()
            self.write({"reversal_move_id": reversal.id})

        self.write({"state": "reversed"})
        self.message_post(
            body=_("Accrual <b>reversed</b>. Reason: %s") % self.reversal_reason
        )
        return True

    def action_reset_to_draft(self):
        """Reset a reversed accrual back to draft for correction."""
        self.ensure_one()
        if self.state != "reversed":
            raise UserError(_("Only reversed accruals can be reset to draft."))
        self.write({"state": "draft", "move_id": False, "reversal_move_id": False})
        self.message_post(body=_("Accrual reset to <b>Draft</b>."))
        return True

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
        """Allow Odoo's importer to resolve investment_id by investment_number."""
        domain = list(domain or [])
        if name:
            domain = ['|',
                ('investment_id.investment_number', '=', name),
                ('display_name', operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)

    @api.model
    def _get_default_list_export_fields(self):
        # IMPORT-EXPORT FIX:
        # - investment_id/investment_number is the only import key needed;
        #   investor_id, partner_id, currency_id, company_id are all readonly related
        #   fields that Odoo silently ignores on import — exporting them misleads users.
        # - Do NOT include investor_id/investor_number here; the investor is fully
        #   resolved via the investment_id relationship.
        return [
            "accrual_date",
            "investment_id/investment_number",
            "period_start",
            "period_end",
            "opening_balance",
            "interest_amount",
            "closing_balance",
            "state",
        ]
