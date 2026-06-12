# -*- coding: utf-8 -*-
"""
Alba Capital Loan Refinance
Switch to different loan product - old loan settled, new loan created
Fee: 1% of new principal (lower than restructure 3%)
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
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
        domain="[('state', 'in', ['active', 'overdue'])]",
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="original_loan_id.customer_id",
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
        compute="_compute_settlement",
        store=True,
        help="Amount to pay off original loan",
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
                rec.new_emi = 0
                rec.new_total_repayable = 0
                continue
            
            principal = rec.new_principal
            rate = rec.new_interest_rate / 100
            months = rec.new_tenure_months
            
            # Simple flat rate calculation for estimate
            interest = principal * rate * months
            rec.new_total_repayable = principal + interest
            rec.new_emi = rec.new_total_repayable / months if months > 0 else 0
    
    @api.depends("original_loan_id", "new_principal", "refinance_fee_rate", "original_loan_id.outstanding_balance")
    def _compute_settlement(self):
        for rec in self:
            if not rec.original_loan_id:
                rec.settlement_amount = 0
                rec.accrued_interest_to_date = 0
                rec.refinance_fee_amount = 0
                rec.cashback_to_customer = 0
                rec.customer_to_pay = 0
                rec.monthly_savings = 0
                continue
            
            loan = rec.original_loan_id
            
            # Settlement = outstanding principal + accrued interest + outstanding charges
            rec.settlement_amount = loan.outstanding_principal + (loan.accrued_interest or 0.0) + (loan.outstanding_charges or 0.0)
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
            
            total_required = rec.settlement_amount + rec.refinance_fee_amount
            
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
            
            rec.write({
                "state": "approved",
                "approved_by": self.env.user.id,
                "approved_date": fields.Date.today(),
            })
            rec.message_post(body=_("Refinance approved."))
    
    def action_settle_original_loan(self):
        """Create repayment to settle original loan and post the refinance fee"""
        for rec in self:
            if rec.state != "approved":
                raise UserError(_("Refinance must be approved first."))

            # Auto-select journal if not set
            if not rec.journal_id:
                rec.journal_id = self.env["account.journal"].search([
                    ("type", "=", "bank"),
                ], limit=1)

            if not rec.journal_id:
                raise UserError(_("Please select a Settlement Journal before settling the loan."))
            
            rec._ensure_payment_method_line()
            
            outstanding_account = (
                rec.payment_method_line_id.payment_account_id
                or rec.journal_id.default_account_id
            )
            if not outstanding_account:
                raise UserError(
                    _(
                        'Journal "%s" has no Outstanding Receipts account configured. '
                        'Please set it under Accounting > Configuration > Journals > '
                        'Incoming Payments tab before settling the loan.'
                    ) % rec.journal_id.name
                ) 

            # ── 1. Create final repayment for the original loan ───────────────
            repayment = self.env["alba.loan.repayment"].create({
                "loan_id": rec.original_loan_id.id,
                "payment_date": fields.Date.today(),
                "amount_paid": rec.settlement_amount,
                "payment_method": "bank_transfer",
                "payment_reference": _("Refinance settlement - %s") % rec.name,
                "journal_id": rec.journal_id.id,
                "payment_method_line_id": rec.payment_method_line_id.id,
                "notes": _("Loan refinanced - settlement via %s") % rec.name,
            })
            repayment.action_post()

            # ── 2. Post refinance fee journal entry ───────────────────────────
            if rec.refinance_fee_amount and rec.refinance_fee_amount > 0:
                product = rec.original_loan_id.loan_product_id
                fee_account = product.account_fees_income_id if product else False

                if not fee_account:
                    raise UserError(_(
                        "Please configure the Fee Income account on loan product '%s' "
                        "before settling this refinance."
                    ) % (product.name if product else "Unknown"))

                # DR Outstanding Receipts transit (fee collected from customer — bank-matchable)
                # CR Fee Income  (income recognised for the refinance)
                # outstanding_account already computed above from payment_method_line_id
                fee_move_vals = {
                    "journal_id": rec.journal_id.id,
                    "date": fields.Date.today(),
                    "ref": _("Refinance Fee — %s") % rec.name,
                    "preferred_payment_method_line_id": rec.payment_method_line_id.id if rec.payment_method_line_id else False,
                    "narration": _(
                        "Refinance fee @ %.2f%% on new principal %s %s"
                    ) % (
                        rec.refinance_fee_rate,
                        rec.currency_id.symbol,
                        rec.new_principal,
                    ),
                    "currency_id": rec.currency_id.id,
                    "line_ids": [
                        # DR Outstanding Receipts transit — fee collected from customer (bank feed will match this)
                        (0, 0, {
                            "account_id": outstanding_account.id,  # FIX: use Outstanding Receipts transit, not direct bank
                            "name": _("Refinance Fee received — %s") % rec.name,
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

            # ── 3. Close original loan & forgive future interest/principal ───
            rec.original_loan_id.write({"state": "closed"})
            
            # Set unpaid future schedule lines due amounts to 0 (forgive future interest and principal since they are settled)
            schedule_to_adjust = rec.original_loan_id.repayment_schedule_ids.filtered(lambda s: s.balance_due > 0)
            for line in schedule_to_adjust:
                line.write({
                    "principal_due": line.principal_paid,
                    "interest_due": line.interest_paid,
                })
            # Force compute of financial totals on the loan to update outstanding_balance to 0
            rec.original_loan_id._compute_financial_totals()
            
            rec.original_loan_id.message_post(body=_(
                "<b>SETTLED VIA REFINANCE</b>: %s %s settled. Future schedule adjusted."
            ) % (rec.currency_id.symbol, rec.settlement_amount))

            rec.write({"state": "settled"})
            rec.message_post(body=_("Original loan settled."))
    
    def action_create_new_loan(self):
        """Create new loan application and disburse"""
        for rec in self:
            if rec.state != "settled":
                raise UserError(_("Original loan must be settled first."))
            
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
            
            # Disburse new loan
            loan = self.env["alba.loan"].create({
                "application_id": application.id,
                "loan_number": self.env["ir.sequence"].next_by_code("alba.loan.seq"),
                "principal_amount": rec.new_principal,
                "interest_rate": rec.new_interest_rate,
                "interest_method": rec.new_product_id.interest_method,
                "tenure_months": rec.new_tenure_months,
                "repayment_frequency": rec.new_repayment_frequency,
                "disbursement_date": fields.Date.today(),
                "installment_amount": rec.new_emi,
                "outstanding_balance": rec.new_principal,
                "state": "active",
                "journal_id": rec.journal_id.id,
            })
            
            # Generate schedule
            loan.action_generate_schedule()
            
            # Post disbursement accounting for the new loan
            loan.action_post_disbursement_entry()  # FIX: create the new refinance loan disbursement move

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
