# -*- coding: utf-8 -*-
"""
Alba Capital Loan Refinance
Switch to different loan product - old loan settled, new loan created
Fee: 1% of new principal (lower than restructure 3%)
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from markupsafe import Markup


class AlbaLoanRefinance(models.Model):
    """Loan Refinance - Switch to new product"""
    
    _name = "alba.loan.refinance"
    _description = "Loan Refinance"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin", "alba.loan.modification.mixin"]
    
    # Identification
    name = fields.Char(string="Reference", required=True, copy=False, default="New")
    
    # Original Loan
    original_loan_id = fields.Many2one(
        "alba.loan",
        string="Original Loan",
        required=True,
        ondelete="restrict",
        domain="[('state', 'not in', ['draft', 'closed', 'written_off'])]",
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="original_loan_id.customer_id",
        readonly=False,
        inverse="_inverse_noop",
        store=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="original_loan_id.customer_id.partner_id",
        store=True,
    )
    
    # Original Loan Details (for reference)
    original_product_id = fields.Many2one(
        "alba.loan.product",
        string="Original Product",
        related="original_loan_id.loan_product_id",
        store=True,
    )
    original_outstanding = fields.Monetary(
        string="Original Outstanding",
        currency_field="currency_id",
        related="original_loan_id.outstanding_balance",
        store=True,
    )
    original_principal = fields.Monetary(
        string="Original Principal",
        currency_field="currency_id",
        related="original_loan_id.principal_amount",
        store=True,
    )
    original_rate = fields.Float(
        string="Original Interest Rate (%)",
        related="original_loan_id.interest_rate",
        store=True,
    )
    original_tenure = fields.Integer(
        string="Original Tenure",
        related="original_loan_id.tenure_months",
        store=True,
    )
    
    # New Product Details
    new_product_id = fields.Many2one(
        "alba.loan.product",
        string="New Loan Product",
        required=True,
        ondelete="restrict",
    )
    new_principal = fields.Monetary(
        string="New Principal Amount",
        currency_field="currency_id",
        required=True,
        default=0.0,
        help="Can be same, higher (top-up), or lower than original",
    )

    @api.constrains("new_principal")
    def _check_new_principal(self):
        for rec in self:
            if rec.new_principal <= 0.0:
                raise ValidationError(_("New Principal Amount must be greater than 0.00 and is mandatory."))

    @api.constrains("original_loan_id")
    def _check_original_loan_state(self):
        # The domain=... on original_loan_id above is only a client-side UI
        # filter — it does not stop the field being set via the wizard's
        # programmatic create(), direct RPC, or an import. Enforce the same
        # restriction server-side so a refinance can never be attached to a
        # loan that isn't actually refinanceable, regardless of how the
        # field got set.
        for rec in self:
            if rec.original_loan_id.state in ("draft", "closed", "written_off"):
                raise ValidationError(_(
                    "Cannot refinance a loan that is Draft, Closed, or Written Off."
                ))

    @api.constrains("is_topup", "original_loan_id")
    def _check_topup_eligibility(self):
        for rec in self:
            if rec.is_topup and rec.original_loan_id:
                loan = rec.original_loan_id
                repaid_pct = (loan.total_paid / loan.total_repayable * 100.0) if loan.total_repayable > 0 else 0.0
                if repaid_pct < 50.0:
                    raise ValidationError(_(
                        "Top-Up Refinance is not allowed. Customer has only repaid %.1f%% of original loan '%s' "
                        "(minimum 50%% repayment required)."
                    ) % (repaid_pct, loan.loan_number))

    new_interest_rate = fields.Float(
        string="New Interest Rate (% p.m.)",
        digits=(5, 2),
        required=True,
    )
    new_tenure_months = fields.Integer(
        string="New Tenure (Months)",
        required=True,
    )
    new_repayment_frequency = fields.Selection([
        ("weekly", "Weekly"),
        ("fortnightly", "Fortnightly"),
        ("monthly", "Monthly"),
    ], string="New Repayment Frequency", required=True, default="monthly")
    new_emi = fields.Monetary(
        string="New EMI",
        currency_field="currency_id",
        compute="_compute_new_terms",
        store=True,
    )
    new_total_repayable = fields.Monetary(
        string="New Total Repayable",
        currency_field="currency_id",
        compute="_compute_new_terms",
        store=True,
    )
    
    # Settlement & Fees
    settlement_amount = fields.Monetary(
        string="Settlement Amount",
        currency_field="currency_id",
        help="Amount to pay off original loan. Auto-suggested from remaining principal + accrued interest + charges, but can be manually overridden.",
    )
    accrued_interest_to_date = fields.Monetary(
        string="Accrued Interest to Settlement",
        currency_field="currency_id",
        compute="_compute_settlement",
        store=True,
    )
    refinance_fee_rate = fields.Float(
        string="Refinance Fee Rate (%)",
        default=1.0,
        help="Standard refinance fee is 1%",
    )
    refinance_fee_amount = fields.Monetary(
        string="Refinance Fee",
        currency_field="currency_id",
        compute="_compute_settlement",
        store=True,
    )
    cashback_to_customer = fields.Monetary(
        string="Cashback to Customer",
        currency_field="currency_id",
        compute="_compute_settlement",
        store=True,
        help="If new loan > settlement + fees",
    )
    customer_to_pay = fields.Monetary(
        string="Customer to Pay",
        currency_field="currency_id",
        compute="_compute_settlement",
        store=True,
        help="If settlement > new loan (shortfall)",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Settlement Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Journal used for settling the original loan",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        domain="[('payment_type', '=', 'inbound'), ('journal_id', '=', journal_id)]",
        help="Specific payment method for the selected journal.",
    )
    monthly_savings = fields.Monetary(
        string="Monthly Savings",
        currency_field="currency_id",
        compute="_compute_settlement",
        inverse="_inverse_noop",
        store=True,
        help="Old EMI - New EMI (if positive)",
    )
    
    # Currency
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="original_loan_id.currency_id",
        store=True,
    )
    
    # Status
    state = fields.Selection([
        ("draft", "Draft"),
        ("quoted", "Quoted"),
        ("customer_accepted", "Customer Accepted"),
        ("approved", "Approved"),
        ("settled", "Original Loan Settled"),
        ("disbursed", "New Loan Disbursed"),
        ("completed", "Completed"),
        ("rejected", "Rejected"),
    ], string="Status", default="draft")
    
    # Approval
    quote_date = fields.Date(string="Quote Date")
    quote_valid_until = fields.Date(string="Quote Valid Until")
    customer_acceptance_date = fields.Date(string="Customer Accepted On")
    approved_by = fields.Many2one("res.users", string="Approved By", readonly=True)
    approved_date = fields.Date(string="Approved Date")
    
    # Links to new loan
    new_loan_application_id = fields.Many2one(
        "alba.loan.application",
        string="New Loan Application",
        readonly=True,
    )
    new_loan_id = fields.Many2one(
        "alba.loan",
        string="New Loan",
        readonly=True,
    )

    # Top-up marker
    is_topup = fields.Boolean(string="Is Top-Up", default=False)
    topup_amount = fields.Monetary(
        string="Top-Up Amount",
        currency_field="currency_id",
        help="If this refinance represents a top-up, amount added to original principal.",
    )

    document_ids = fields.One2many(
        "alba.loan.document",
        "refinance_id",
        string="Supporting Documents",
    )
    document_count = fields.Integer(
        string="Documents",
        compute="_compute_document_count",
    )

    @api.depends(
        "original_outstanding",
        "original_principal",
        "new_principal",
        "new_emi",
        "settlement_amount",
        "refinance_fee_amount",
        "cashback_to_customer",
        "customer_to_pay",
        "monthly_savings",
        "original_loan_id",
        "state",
    )
    def _compute_modification_charts(self):
        return super()._compute_modification_charts()

    @api.depends("document_ids")
    def _compute_document_count(self):
        for rec in self:
            rec.document_count = len(rec.document_ids)
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.depends("new_principal", "new_interest_rate", "new_tenure_months", "new_product_id")
    def _compute_new_terms(self):
        for rec in self:
            if not rec.new_principal or not rec.new_tenure_months:
                if rec.id:
                    continue
                rec.new_emi = 0
                rec.new_total_repayable = 0
                continue

            principal = rec.new_principal
            rate = rec.new_interest_rate / 100  # monthly rate
            months = rec.new_tenure_months

            # Determine method from new product (fall back to flat_rate)
            method = (
                rec.new_product_id.interest_method
                if rec.new_product_id
                else "flat_rate"
            )

            if method == "reducing_balance" and rate > 0:
                # Annuity (reducing-balance) formula — same as disburse wizard
                emi = round(
                    principal * rate * (1 + rate) ** months
                    / ((1 + rate) ** months - 1),
                    2,
                )
                total_interest = round(emi * months - principal, 2)
                total_repayable = principal + total_interest
            elif method == "reducing_balance" and rate == 0:
                # Zero-interest reducing balance
                emi = round(principal / months, 2)
                total_interest = 0.0
                total_repayable = principal
            else:
                # Flat-rate formula: I = P × r × n
                total_interest = round(principal * rate * months, 2)
                total_repayable = principal + total_interest
                emi = round(total_repayable / months, 2) if months > 0 else 0

            rec.new_total_repayable = total_repayable
            rec.new_emi = emi
    
    @api.depends("original_loan_id", "settlement_amount", "new_principal", "refinance_fee_rate", "original_loan_id.outstanding_balance")
    def _compute_settlement(self):
        for rec in self:
            if not rec.original_loan_id:
                if rec.id:
                    continue
                rec.accrued_interest_to_date = 0
                rec.refinance_fee_amount = 0
                rec.cashback_to_customer = 0
                rec.customer_to_pay = 0
                rec.monthly_savings = 0
                continue
            
            loan = rec.original_loan_id
            rec.accrued_interest_to_date = loan.accrued_interest or 0
            
            # Refinance fee defaults
            if rec.is_topup and rec.topup_amount and rec.original_product_id:
                # For top-ups, apply original product fee templates to the top-up amount
                try:
                    rec.refinance_fee_amount = rec.original_product_id.calculate_total_fees(rec.topup_amount)
                except Exception:
                    # Fallback to standard refinance percentage if fee templates fail
                    rec.refinance_fee_amount = rec.new_principal * (rec.refinance_fee_rate / 100)
            else:
                # Refinance fee = percentage of new principal
                rec.refinance_fee_amount = rec.new_principal * (rec.refinance_fee_rate / 100)
            
            total_required = (rec.settlement_amount or 0.0) + rec.refinance_fee_amount
            
            # Calculate cashback or shortfall
            if rec.new_principal > total_required:
                rec.cashback_to_customer = rec.new_principal - total_required
                rec.customer_to_pay = 0
            else:
                rec.cashback_to_customer = 0
                rec.customer_to_pay = total_required - rec.new_principal
            
            # Monthly savings
            old_emi = loan.installment_amount
            rec.monthly_savings = max(0, old_emi - rec.new_emi)

    @api.onchange("settlement_amount")
    def _onchange_settlement_amount(self):
        for rec in self:
            if rec.is_topup:
                rec.new_principal = (rec.settlement_amount or 0.0) + (rec.topup_amount or 0.0)
            total_required = (rec.settlement_amount or 0.0) + (rec.refinance_fee_amount or 0.0)
            if rec.new_principal > total_required:
                rec.cashback_to_customer = rec.new_principal - total_required
                rec.customer_to_pay = 0.0
            else:
                rec.cashback_to_customer = 0.0
                rec.customer_to_pay = total_required - rec.new_principal

    @api.onchange("is_topup", "topup_amount", "original_loan_id")
    def _onchange_topup_terms(self):
        for rec in self:
            if rec.is_topup and rec.original_loan_id:
                loan = rec.original_loan_id
                settlement = loan.outstanding_principal + (loan.accrued_interest or 0.0) + (loan.outstanding_charges or 0.0)
                rec.settlement_amount = settlement
                rec.new_principal = settlement + (rec.topup_amount or 0.0)
                
                repaid_pct = (loan.total_paid / loan.total_repayable * 100.0) if loan.total_repayable > 0 else 0.0
                if repaid_pct < 50.0:
                    return {
                        "warning": {
                            "title": _("Ineligible for Top-Up"),
                            "message": _(
                                "Original loan '%s' has only %.1f%% repaid. At least 50%% repayment is required before a top-up can be granted."
                            ) % (loan.loan_number, repaid_pct)
                        }
                    }

    @api.onchange("original_loan_id")
    def _onchange_original_loan_id(self):
        for rec in self:
            if rec.original_loan_id:
                loan = rec.original_loan_id
                if not rec.new_product_id and loan.loan_product_id:
                    rec.new_product_id = loan.loan_product_id.id
                if not rec.new_interest_rate:
                    rec.new_interest_rate = loan.interest_rate
                if not rec.new_tenure_months:
                    rec.new_tenure_months = loan.tenure_months
                if not rec.settlement_amount:
                    rec.settlement_amount = loan.outstanding_principal + (loan.accrued_interest or 0.0) + (loan.outstanding_charges or 0.0)
                if rec.is_topup:
                    rec._onchange_topup_terms()


    @api.onchange("new_product_id")
    def _onchange_new_product_id(self):
        for rec in self:
            if rec.new_product_id:
                product = rec.new_product_id
                rec.new_interest_rate = product.interest_rate
                rec.new_tenure_months = product.min_tenure_months or product.max_tenure_months or 12

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        for rec in self:
            if rec.payment_method_line_id and rec.payment_method_line_id.journal_id != rec.journal_id:
                rec.payment_method_line_id = False

    def _ensure_payment_method_line(self):
        for rec in self:
            if not rec.journal_id:
                continue
            if rec.payment_method_line_id:
                if rec.payment_method_line_id.journal_id != rec.journal_id:
                    raise UserError(_(
                        "Payment Method '%(method)s' does not belong to Settlement Journal '%(journal)s'.",
                        method=rec.payment_method_line_id.display_name,
                        journal=rec.journal_id.display_name,
                    ))
                if rec.payment_method_line_id.payment_type != "inbound":
                    raise UserError(_("Please select an inbound payment method for settlement journal '%s'.") % rec.journal_id.display_name)
                continue

            method_line = self.env["account.payment.method.line"].search([
                ("payment_type", "=", "inbound"),
                ("journal_id", "=", rec.journal_id.id),
            ], limit=1)
            if not method_line:
                raise UserError(_("Please configure an inbound Payment Method on settlement journal '%s'.") % rec.journal_id.display_name)
            rec.payment_method_line_id = method_line

    def _get_modification_comparison_chart(self):
        self.ensure_one()
        loan = self.original_loan_id
        old_emi = loan.installment_amount if loan else 0
        return self._build_grouped_bar_chart(
            ["Outstanding", "Principal", "EMI"],
            [
                self._chart_amount(self.original_outstanding),
                self._chart_amount(self.original_principal),
                self._chart_amount(old_emi),
            ],
            [
                self._chart_amount(self.new_principal),
                self._chart_amount(self.new_principal),
                self._chart_amount(self.new_emi),
            ],
        )

    def _get_modification_impact_chart(self):
        self.ensure_one()
        labels = ["Settlement", "Refinance Fee"]
        values = [
            self._chart_amount(self.settlement_amount),
            self._chart_amount(self.refinance_fee_amount),
        ]
        if self.cashback_to_customer:
            labels.append("Cashback")
            values.append(self._chart_amount(self.cashback_to_customer))
        elif self.customer_to_pay:
            labels.append("Customer Top-Up")
            values.append(self._chart_amount(self.customer_to_pay))
        if self.monthly_savings:
            labels.append("Monthly Savings")
            values.append(self._chart_amount(self.monthly_savings))
        return self._build_doughnut_chart(labels, values)
    
    # =========================================================================
    # ORM Overrides
    # =========================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("alba.loan.refinance") or "New"
        return super().create(vals_list)
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_generate_quote(self):
        """Generate refinance quote"""
        for rec in self:
            if rec.is_topup and rec.original_loan_id:
                loan = rec.original_loan_id
                repaid_pct = (loan.total_paid / loan.total_repayable * 100.0) if loan.total_repayable > 0 else 0.0
                if repaid_pct < 50.0:
                    raise UserError(_(
                        "Cannot generate quote: Top-Up Refinance is not allowed. Customer has only repaid %.1f%% of original loan '%s' (minimum 50%% repayment required)."
                    ) % (repaid_pct, loan.loan_number))

            from datetime import date, timedelta
            
            rec.write({
                "state": "quoted",
                "quote_date": fields.Date.today(),
                "quote_valid_until": fields.Date.today() + timedelta(days=7),
            })
            
            rec.message_post(body=_(
                "<b>REFINANCE QUOTE</b>: %s %s new principal (%s → %s). Fee: %s %s."
            ) % (
                rec.currency_id.symbol, rec.new_principal,
                rec.original_product_id.name, rec.new_product_id.name,
                rec.currency_id.symbol, rec.refinance_fee_amount,
            ))
    
    def action_customer_accept(self):
        """Customer accepts quote"""
        for rec in self:
            rec.write({
                "state": "customer_accepted",
                "customer_acceptance_date": fields.Date.today(),
            })
            rec.message_post(body=_("Quote accepted."))
    
    def action_approve(self):
        """Approve refinance"""
        for rec in self:
            if not self.env.user.has_group("alba_loans.group_operations_manager"):
                raise UserError(_("Only Operations Manager can approve refinances."))
            
            if rec.is_topup and rec.original_loan_id:
                loan = rec.original_loan_id
                repaid_pct = (loan.total_paid / loan.total_repayable * 100.0) if loan.total_repayable > 0 else 0.0
                if repaid_pct < 50.0:
                    raise UserError(_(
                        "Cannot approve: Top-Up Refinance is not allowed. Customer has only repaid %.1f%% of original loan '%s' (minimum 50%% repayment required)."
                    ) % (repaid_pct, loan.loan_number))

            rec.write({
                "state": "approved",
                "approved_by": self.env.user.id,
                "approved_date": fields.Date.today(),
            })
            rec.message_post(body=_("Refinance approved."))
    
    def action_settle_original_loan(self):
        """
        Settle the original loan and post the refinance fee.

        Neither leg here is real customer cash — both are funded by the new
        loan's proceeds (booked in action_create_new_loan()). Both post
        against the Loan Clearing account instead of a bank/cash account;
        only the true net difference (cashback_to_customer or
        customer_to_pay) touches real cash, posted once the new loan actually
        exists. Booking the full settlement_amount and refinance_fee_amount
        as if real cash moved (the old behaviour) created two large journal
        entries with no matching bank transaction — a reconciliation break.
        """
        for rec in self:
            if rec.state != "approved":
                raise UserError(_("Refinance must be approved first."))

            # Lock the original loan row for the rest of this transaction so
            # a concurrent action against the same loan (another repayment,
            # a payment holiday, a second settlement attempt) can't read the
            # same pre-settlement balance and race with this write-off/close.
            self.env.cr.execute(
                "SELECT id FROM alba_loan WHERE id = %s FOR UPDATE",
                (rec.original_loan_id.id,),
            )

            product = rec.original_loan_id.loan_product_id
            if not product.account_clearing_id:
                raise UserError(_(
                    "Please configure the Loan Clearing account on product '%s'."
                ) % product.name)

            # ── 1. Create final repayment for the original loan — internal
            #      transfer, funded by the new loan, not fresh cash ─────────
            repayment = self.env["alba.loan.repayment"].create({
                "loan_id": rec.original_loan_id.id,
                "payment_date": fields.Date.today(),
                "amount_paid": rec.settlement_amount,
                "payment_method": "bank_transfer",
                "payment_reference": _("Refinance settlement - %s") % rec.name,
                "is_internal_transfer": True,
                "notes": _("Loan refinanced - settlement via %s") % rec.name,
            })
            repayment.action_post()

            # ── 2. Post refinance fee journal entry (also internal — netted
            #      against the new loan's proceeds, not collected in cash) ──
            if rec.refinance_fee_amount and rec.refinance_fee_amount > 0:
                fee_account = product.account_fees_income_id if product else False

                if not fee_account:
                    raise UserError(_(
                        "Please configure the Fee Income account on loan product '%s' "
                        "before settling this refinance."
                    ) % (product.name if product else "Unknown"))

                fee_journal = self.env["account.journal"].search(
                    [("type", "=", "general"), ("company_id", "=", rec.original_loan_id.company_id.id)],
                    limit=1,
                )
                if not fee_journal:
                    raise UserError(_(
                        "No General journal found for company '%s'. "
                        "Please create one under Accounting > Configuration > Journals."
                    ) % rec.original_loan_id.company_id.name)

                # DR Loan Clearing (funded by the new loan's proceeds)
                # CR Fee Income  (income recognised for the refinance)
                fee_move_vals = {
                    "journal_id": fee_journal.id,
                    "date": fields.Date.today(),
                    "ref": _("Refinance Fee — %s") % rec.name,
                    "alba_loan_id": rec.original_loan_id.id,
                    "narration": _(
                        "Refinance fee @ %.2f%% on new principal %s %s"
                    ) % (
                        rec.refinance_fee_rate,
                        rec.currency_id.symbol,
                        rec.new_principal,
                    ),
                    "currency_id": rec.currency_id.id,
                    "line_ids": [
                        # DR Loan Clearing — funded by the new loan's proceeds
                        (0, 0, {
                            "account_id": product.account_clearing_id.id,
                            "name": _("Refinance Fee — %s") % rec.name,
                            "debit": rec.refinance_fee_amount if rec.currency_id == rec.original_loan_id.company_id.currency_id else 0.0,
                            "credit": 0.0,
                            "amount_currency": rec.refinance_fee_amount,
                            "currency_id": rec.currency_id.id,
                            "partner_id": rec.partner_id.id,
                        }),
                        # CR Fee Income — recognised as income
                        (0, 0, {
                            "account_id": fee_account.id,
                            "name": _("Refinance Fee income — %s") % rec.name,
                            "debit": 0.0,
                            "credit": rec.refinance_fee_amount if rec.currency_id == rec.original_loan_id.company_id.currency_id else 0.0,
                            "amount_currency": -rec.refinance_fee_amount,
                            "currency_id": rec.currency_id.id,
                            "partner_id": rec.partner_id.id,
                        }),
                    ],
                }
                fee_move = self.env["account.move"].create(fee_move_vals)
                fee_move.action_post()
                rec.message_post(body=_(
                    "<b>REFINANCE FEE POSTED</b>: %s %s → Journal Entry: %s"
                ) % (rec.currency_id.symbol, rec.refinance_fee_amount, fee_move.name))

            # ── 3. Write off any shortfall, close original loan, forgive
            #      the (now written-off) remaining schedule ─────────────────
            # settlement_amount can be a manual override lower than the
            # loan's true payoff. If it under-collects, book a real
            # write-off entry for the gap BEFORE forgiving the schedule —
            # otherwise the Loan/Interest/Penalty Receivable accounts would
            # carry the uncollected balance forever while the schedule
            # silently shows 0, with no accounting trail for the loss.
            original_loan = rec.original_loan_id
            shortfall = original_loan.outstanding_balance
            if shortfall > 0.01:
                original_loan.action_post_write_off_entry()
                original_loan.message_post(body=_(
                    "<b>REFINANCE SHORTFALL WRITTEN OFF</b>: settlement of %s %s did not cover "
                    "the full payoff — %s %s written off against the Provision account."
                ) % (
                    rec.currency_id.symbol, rec.settlement_amount,
                    rec.currency_id.symbol, f"{shortfall:,.2f}",
                ))

            original_loan.write({"state": "closed"})

            # Set unpaid future schedule lines due amounts to 0 (forgive future interest, principal, and
            # penalty since they are settled) — penalty_due must be forgiven too, otherwise a line with
            # any unpaid penalty keeps balance_due > 0 forever on a loan that's supposedly "closed".
            schedule_to_adjust = original_loan.repayment_schedule_ids.filtered(lambda s: s.balance_due > 0)
            for line in schedule_to_adjust:
                line.write({
                    "principal_due": line.principal_paid,
                    "interest_due": line.interest_paid,
                    "penalty_due": line.penalty_paid,
                })
            # Force compute of financial totals on the loan to update outstanding_balance to 0
            original_loan._compute_financial_totals()

            original_loan.message_post(body=_(
                "<b>SETTLED VIA REFINANCE</b>: %s %s settled. Future schedule adjusted."
            ) % (rec.currency_id.symbol, rec.settlement_amount))

            rec.write({"state": "settled"})
            rec.message_post(body=_("Original loan settled."))
    
    def action_create_new_loan(self):
        """
        Create the new loan application and disburse.

        Only ENTRY 1 (DR New Loan Receivable / CR Loan Clearing) is posted
        here — not a full cash disbursement of the gross new_principal.
        The Clearing account was already debited for settlement_amount and
        refinance_fee_amount in action_settle_original_loan(); crediting it
        here for the full new_principal leaves exactly the true net
        difference (cashback_to_customer or customer_to_pay) outstanding in
        Clearing, which is then settled against real Bank/Cash in one final
        entry below — the only leg of this whole refinance that is real
        cash. Posting the gross new_principal as a bank disbursement (the
        old behaviour) created a bank-statement mismatch: most of that
        amount never actually left the bank, it was consumed internally by
        the settlement and fee.
        """
        for rec in self:
            if rec.state != "settled":
                raise UserError(_("Original loan must be settled first."))
            if not rec.journal_id:
                raise UserError(_(
                    "Please select a Settlement Journal — it is used for the "
                    "net cashback/top-up payment to the customer, if any."
                ))

            # Lock the original loan row for the rest of this transaction so
            # a concurrent action against it can't race with the accounting
            # entries below (the new loan doesn't exist yet at this point,
            # so there is nothing to lock for it until after it is created).
            self.env.cr.execute(
                "SELECT id FROM alba_loan WHERE id = %s FOR UPDATE",
                (rec.original_loan_id.id,),
            )

            # Create new loan application
            application = self.env["alba.loan.application"].create({
                "customer_id": rec.customer_id.id,
                "loan_product_id": rec.new_product_id.id,
                "requested_amount": rec.new_principal,
                "approved_amount": rec.new_principal,
                "tenure_months": rec.new_tenure_months,
                "repayment_frequency": rec.new_repayment_frequency,
                "purpose": _("Refinance from %s") % rec.original_loan_id.loan_number,
                "state": "approved",
                "approved_date": fields.Datetime.now(),
                "approved_by": self.env.uid,
            })

            rec.write({
                "new_loan_application_id": application.id,
            })

            # Create new loan
            loan = self.env["alba.loan"].create({
                "application_id": application.id,
                "loan_number": self.env["ir.sequence"].next_by_code("alba.loan.seq"),
                "principal_amount": rec.new_principal,
                "interest_rate": rec.new_interest_rate,
                "interest_method": rec.new_product_id.interest_method,
                "tenure_months": rec.new_tenure_months,
                "repayment_frequency": rec.new_repayment_frequency,
                "loan_date": fields.Date.today(),
                "disbursement_date": fields.Date.today(),
                "installment_amount": rec.new_emi,
                "outstanding_balance": rec.new_principal,
                "state": "normal",
                "journal_id": rec.journal_id.id,
            })

            # Generate schedule
            loan.action_generate_schedule()

            # ENTRY 1 only — DR New Loan Receivable / CR Loan Clearing.
            # No ENTRY 2 (no gross cash disbursement) — see docstring.
            general_journal = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", loan.company_id.id)],
                limit=1,
            )
            if not general_journal:
                raise UserError(_(
                    "No General journal found for company '%s'. "
                    "Please create one under Accounting > Configuration > Journals."
                ) % loan.company_id.name)
            application.action_post_approval_entry(journal=general_journal)
            loan.disbursement_move_id = application.approval_move_id

            # ── Final entry: the true net difference, and ONLY this touches
            #    real cash ──────────────────────────────────────────────────
            product = rec.new_product_id
            if not product.account_clearing_id:
                raise UserError(_(
                    "Please configure the Loan Clearing account on product '%s'."
                ) % product.name)

            net_cash = rec.new_principal - rec.settlement_amount - (rec.refinance_fee_amount or 0.0)
            if abs(net_cash) > 0.01:
                rec._ensure_payment_method_line()
                outstanding_account = (
                    rec.payment_method_line_id.payment_account_id
                    or rec.journal_id.default_account_id
                )
                if not outstanding_account:
                    raise UserError(
                        _(
                            'Journal "%s" has no bank/cash account configured. '
                            'Please set the journal default account or the payment method account.'
                        ) % rec.journal_id.name
                    )

                if net_cash > 0:
                    # Cashback to customer: DR Clearing, CR Bank (cash out)
                    net_lines = [
                        (0, 0, {
                            "account_id": product.account_clearing_id.id,
                            "name": _("Refinance cashback — %s") % rec.name,
                            "debit": net_cash, "credit": 0.0,
                            "partner_id": rec.partner_id.id,
                        }),
                        (0, 0, {
                            "account_id": outstanding_account.id,
                            "name": _("Refinance cashback paid — %s") % rec.name,
                            "debit": 0.0, "credit": net_cash,
                            "partner_id": rec.partner_id.id,
                        }),
                    ]
                    net_label = _("cashback to customer")
                else:
                    # Shortfall from customer: DR Bank (cash in), CR Clearing
                    amount = -net_cash
                    net_lines = [
                        (0, 0, {
                            "account_id": outstanding_account.id,
                            "name": _("Refinance top-up received — %s") % rec.name,
                            "debit": amount, "credit": 0.0,
                            "partner_id": rec.partner_id.id,
                        }),
                        (0, 0, {
                            "account_id": product.account_clearing_id.id,
                            "name": _("Refinance top-up — %s") % rec.name,
                            "debit": 0.0, "credit": amount,
                            "partner_id": rec.partner_id.id,
                        }),
                    ]
                    net_label = _("collected from customer")

                net_move = self.env["account.move"].create({
                    "journal_id": rec.journal_id.id,
                    "date": fields.Date.today(),
                    "ref": _("Refinance Net Settlement — %s") % rec.name,
                    "alba_loan_id": loan.id,
                    "currency_id": rec.currency_id.id,
                    "line_ids": net_lines,
                })
                net_move.action_post()
                rec.message_post(body=_(
                    "<b>REFINANCE NET SETTLEMENT</b>: %s %s %s → Journal Entry: %s"
                ) % (rec.currency_id.symbol, f"{abs(net_cash):,.2f}", net_label, net_move.name))

            rec.write({
                "state": "disbursed",
                "new_loan_id": loan.id,
            })

            rec.message_post(body=_(
                "<b>NEW LOAN DISBURSED</b>: %s (Principal: %s %s)"
            ) % (loan.loan_number, rec.currency_id.symbol, rec.new_principal))
    
    def action_complete(self):
        """Complete refinance process"""
        for rec in self:
            if rec.state != "disbursed":
                raise UserError(_("New loan must be disbursed first."))
            
            rec.write({"state": "completed"})
            
            # Send Email
            template = self.env.ref('alba_loans.email_template_refinance', raise_if_not_found=False)
            if template:
                template.send_mail(rec.id, force_send=True)

            rec.message_post(body=Markup(_("<b>REFINANCE COMPLETED</b>")))
    
    def action_reject(self):
        """Reject refinance"""
        for rec in self:
            rec.write({"state": "rejected"})
            rec.message_post(body=_("Refinance rejected."))

    def action_view_original_loan(self):
        """Navigate to the original loan"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Original Loan"),
            "res_model": "alba.loan",
            "view_mode": "form",
            "res_id": self.original_loan_id.id,
        }

    def action_view_new_loan(self):
        """Navigate to the new loan"""
        self.ensure_one()
        if not self.new_loan_id:
            raise UserError(_("New loan has not been created yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("New Loan"),
            "res_model": "alba.loan",
            "view_mode": "form",
            "res_id": self.new_loan_id.id,
        }

    def _inverse_noop(self):
        pass
