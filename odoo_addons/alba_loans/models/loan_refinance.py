# -*- coding: utf-8 -*-
"""
Alba Capital Loan Refinance
Switch to different loan product - old loan settled, new loan created
Fee: 1% of new principal (lower than restructure 3%)
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaLoanRefinance(models.Model):
    """Loan Refinance - Switch to new product"""
    
    _name = "alba.loan.refinance"
    _description = "Loan Refinance"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    
    # Identification
    name = fields.Char(string="Reference", required=True, copy=False, default="New")
    
    # Original Loan
    original_loan_id = fields.Many2one(
        "alba.loan",
        string="Original Loan",
        required=True,
        ondelete="restrict",
        domain="[('state', 'in', ['active', 'overdue'])]",
        tracking=True,
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="original_loan_id.customer_id",
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
        tracking=True,
    )
    new_principal = fields.Monetary(
        string="New Principal Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
        help="Can be same, higher (top-up), or lower than original",
    )
    new_interest_rate = fields.Float(
        string="New Interest Rate (% p.m.)",
        digits=(5, 2),
        required=True,
        tracking=True,
    )
    new_tenure_months = fields.Integer(
        string="New Tenure (Months)",
        required=True,
        tracking=True,
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
    monthly_savings = fields.Monetary(
        string="Monthly Savings",
        currency_field="currency_id",
        compute="_compute_settlement",
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
    ], string="Status", default="draft", tracking=True)
    
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
            
            # Settlement = outstanding + accrued interest to settlement date
            rec.settlement_amount = loan.outstanding_balance
            rec.accrued_interest_to_date = loan.accrued_interest or 0
            
            # Add accrued interest if any
            if rec.accrued_interest_to_date:
                rec.settlement_amount += rec.accrued_interest_to_date
            
            # Refinance fee = 1% of new principal
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
                "<b>REFINANCE QUOTE GENERATED</b><br/>"
                "Quote Ref: %s<br/>"
                "Original Product: %s → New Product: %s<br/>"
                "Settlement Amount: %s %s<br/>"
                "New Principal: %s %s<br/>"
                "Refinance Fee: %s %s<br/>"
                "Cashback to Customer: %s %s<br/>"
                "Monthly Savings: %s %s<br/>"
                "Valid Until: %s"
            ) % (
                rec.name,
                rec.original_product_id.name, rec.new_product_id.name,
                rec.currency_id.symbol, rec.settlement_amount,
                rec.currency_id.symbol, rec.new_principal,
                rec.currency_id.symbol, rec.refinance_fee_amount,
                rec.currency_id.symbol, rec.cashback_to_customer,
                rec.currency_id.symbol, rec.monthly_savings,
                rec.quote_valid_until,
            ))
    
    def action_customer_accept(self):
        """Customer accepts quote"""
        for rec in self:
            rec.write({
                "state": "customer_accepted",
                "customer_acceptance_date": fields.Date.today(),
            })
            rec.message_post(body=_("Customer accepted refinance quote."))
    
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
            rec.message_post(body=_("Refinance approved by %s.") % self.env.user.name)
    
    def action_settle_original_loan(self):
        """Create repayment to settle original loan"""
        for rec in self:
            if rec.state != "approved":
                raise UserError(_("Refinance must be approved first."))
            
            # Create final repayment for original loan
            repayment = self.env["alba.loan.repayment"].create({
                "loan_id": rec.original_loan_id.id,
                "payment_date": fields.Date.today(),
                "amount_paid": rec.settlement_amount,
                "payment_method": "bank_transfer",
                "payment_reference": _("Refinance settlement - %s") % rec.name,
                "notes": _("Loan refinanced - settlement via %s") % rec.name,
            })
            repayment.action_post()
            
            # Close original loan
            rec.original_loan_id.write({
                "state": "closed",
            })
            rec.original_loan_id.message_post(body=_(
                "<b>LOAN SETTLED VIA REFINANCE</b><br/>"
                "Refinance Ref: %s<br/>"
                "Settlement Amount: %s %s"
            ) % (rec.name, rec.currency_id.symbol, rec.settlement_amount))
            
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
            })
            
            # Generate schedule
            loan.action_generate_schedule()
            
            # Post disbursement entry
            loan.action_post_disbursement_entry()
            
            rec.write({
                "state": "disbursed",
                "new_loan_id": loan.id,
            })
            
            rec.message_post(body=_(
                "<b>NEW LOAN DISBURSED</b><br/>"
                "Loan Number: %s<br/>"
                "Principal: %s %s<br/>"
                "EMI: %s %s"
            ) % (loan.loan_number, rec.currency_id.symbol, rec.new_principal, rec.currency_id.symbol, rec.new_emi))
    
    def action_complete(self):
        """Complete refinance process"""
        for rec in self:
            if rec.state != "disbursed":
                raise UserError(_("New loan must be disbursed first."))
            
            rec.write({"state": "completed"})
            rec.message_post(body=_("<b>REFINANCE COMPLETED</b>"))
    
    def action_reject(self):
        """Reject refinance"""
        for rec in self:
            rec.write({"state": "rejected"})
            rec.message_post(body=_("Refinance rejected by %s.") % self.env.user.name)
