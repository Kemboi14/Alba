# -*- coding: utf-8 -*-
"""
Alba Capital Loan Partial Payoff
Allow customers to pay extra to reduce principal without full settlement
Two modes: Reduce EMI (keep tenure) or Reduce Tenure (keep EMI)
NO FEE - encourages faster loan repayment
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from datetime import date, timedelta


class AlbaLoanPartialPayoff(models.Model):
    """Partial Payoff - Extra payment to reduce principal"""
    
    _name = "alba.loan.partial.payoff"
    _description = "Loan Partial Payoff"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    
    # Identification
    name = fields.Char(string="Reference", required=True, copy=False, default="New")
    
    # Links
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="restrict",
        tracking=True,
        domain="[('state', '=', 'active')]",
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="loan_id.customer_id",
        store=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="loan_id.customer_id.partner_id",
        store=True,
    )
    
    # Current Loan Details
    current_outstanding = fields.Monetary(
        string="Current Outstanding",
        currency_field="currency_id",
        related="loan_id.outstanding_balance",
        store=True,
    )
    current_principal = fields.Monetary(
        string="Current Principal",
        currency_field="currency_id",
        related="loan_id.principal_amount",
        store=True,
    )
    current_emi = fields.Monetary(
        string="Current EMI",
        currency_field="currency_id",
        related="loan_id.installment_amount",
        store=True,
    )
    remaining_tenure = fields.Integer(
        string="Remaining Months",
        related="loan_id.remaining_tenure",
        store=True,
    )
    
    # Payoff Details
    payoff_amount = fields.Monetary(
        string="Payoff Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
        help="Extra amount customer wants to pay to reduce principal",
    )
    reduction_mode = fields.Selection([
        ("reduce_emi", "Reduce EMI (Keep Same Tenure)"),
        ("reduce_tenure", "Reduce Tenure (Keep Same EMI)"),
    ], string="Reduction Mode", required=True, default="reduce_emi",
       help="Reduce EMI: Lower monthly payment, same duration\nReduce Tenure: Same payment, finish earlier")
    
    # Calculated Results
    principal_reduction = fields.Monetary(
        string="Principal Reduction",
        currency_field="currency_id",
        compute="_compute_reduction",
        store=True,
    )
    interest_saved = fields.Monetary(
        string="Interest Saved",
        currency_field="currency_id",
        compute="_compute_reduction",
        store=True,
    )
    new_outstanding = fields.Monetary(
        string="New Outstanding",
        currency_field="currency_id",
        compute="_compute_reduction",
        store=True,
    )
    new_emi = fields.Monetary(
        string="New EMI",
        currency_field="currency_id",
        compute="_compute_reduction",
        store=True,
    )
    new_tenure = fields.Integer(
        string="New Tenure (Months)",
        compute="_compute_reduction",
        store=True,
    )
    emi_reduction = fields.Monetary(
        string="EMI Reduction",
        currency_field="currency_id",
        compute="_compute_reduction",
        store=True,
    )
    tenure_reduction = fields.Integer(
        string="Tenure Reduction (Months)",
        compute="_compute_reduction",
        store=True,
    )
    
    # Quote Validity
    quote_date = fields.Date(string="Quote Date", default=fields.Date.today)
    quote_valid_until = fields.Date(
        string="Quote Valid Until",
        compute="_compute_quote_validity",
        store=True,
    )
    
    # Currency
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="loan_id.currency_id",
        store=True,
    )
    
    # Status
    state = fields.Selection([
        ("draft", "Draft"),
        ("quoted", "Quoted"),
        ("accepted", "Accepted"),
        ("applied", "Applied"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    ], string="Status", default="draft", tracking=True)
    
    # Processing
    payment_date = fields.Date(string="Payment Date")
    payment_method = fields.Selection([
        ("cash", "Cash"),
        ("bank_transfer", "Bank Transfer"),
        ("mpesa", "M-Pesa"),
        ("cheque", "Cheque"),
    ], string="Payment Method")
    payment_reference = fields.Char(string="Payment Reference")
    
    # Links
    repayment_id = fields.Many2one(
        "alba.loan.repayment",
        string="Repayment Record",
        readonly=True,
    )
    
    # Applied By
    processed_by = fields.Many2one("res.users", string="Processed By", readonly=True)
    processed_date = fields.Date(string="Processed Date")
    
    # =========================================================================
    # Constraints
    # =========================================================================
    
    _positive_payoff = models.Constraint(
        "CHECK(payoff_amount > 0)",
        "Payoff amount must be positive."
    )
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.depends("quote_date")
    def _compute_quote_validity(self):
        for rec in self:
            if rec.quote_date:
                rec.quote_valid_until = rec.quote_date + timedelta(days=7)
            else:
                rec.quote_valid_until = False
    
    @api.depends("loan_id", "payoff_amount", "reduction_mode")
    def _compute_reduction(self):
        for rec in self:
            if not rec.loan_id or not rec.payoff_amount:
                rec.principal_reduction = 0
                rec.interest_saved = 0
                rec.new_outstanding = 0
                rec.new_emi = 0
                rec.new_tenure = 0
                rec.emi_reduction = 0
                rec.tenure_reduction = 0
                continue
            
            loan = rec.loan_id
            current_outstanding = loan.outstanding_balance
            
            # Principal reduction = payoff amount (all goes to principal)
            rec.principal_reduction = rec.payoff_amount
            rec.new_outstanding = current_outstanding - rec.payoff_amount
            
            # Calculate interest saved
            if loan.interest_method == "flat_rate":
                # Flat rate: Interest = Principal * Rate * Time
                rate_per_month = loan.interest_rate / 100
                rec.interest_saved = rec.payoff_amount * rate_per_month * loan.remaining_tenure
            else:
                # Reducing balance: Complex calculation - approximate
                # Simplified: assume average interest on reduced principal
                rate_per_month = loan.interest_rate / 100
                avg_reduction = rec.payoff_amount / 2  # Principal reduces over time
                rec.interest_saved = avg_reduction * rate_per_month * loan.remaining_tenure
            
            # Calculate new terms based on mode
            if rec.reduction_mode == "reduce_emi":
                # Keep same tenure, reduce EMI
                rec.new_tenure = loan.remaining_tenure
                if loan.remaining_tenure > 0:
                    rec.new_emi = rec.new_outstanding / loan.remaining_tenure
                else:
                    rec.new_emi = 0
                rec.emi_reduction = loan.installment_amount - rec.new_emi
                rec.tenure_reduction = 0
            else:  # reduce_tenure
                # Keep same EMI, reduce tenure
                rec.new_emi = loan.installment_amount
                if loan.installment_amount > 0:
                    rec.new_tenure = int(rec.new_outstanding / loan.installment_amount)
                else:
                    rec.new_tenure = 0
                rec.emi_reduction = 0
                rec.tenure_reduction = loan.remaining_tenure - rec.new_tenure
    
    # =========================================================================
    # ORM Overrides
    # =========================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("alba.loan.partial.payoff") or "New"
        return super().create(vals_list)
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_generate_quote(self):
        """Generate quote for customer"""
        for rec in self:
            # Validate
            if rec.payoff_amount >= rec.current_outstanding:
                raise UserError(_("Payoff amount must be less than outstanding balance. Use Early Settlement for full payoff."))
            
            if rec.payoff_amount <= 0:
                raise UserError(_("Payoff amount must be positive."))
            
            rec.write({
                "state": "quoted",
                "quote_date": fields.Date.today(),
            })
            
            # Generate message for customer
            if rec.reduction_mode == "reduce_emi":
                mode_desc = _(
                    "EMI will reduce from %s to %s (save %s per month)<br/>"
                    "Tenure remains %s months"
                ) % (rec.currency_id.symbol, rec.current_emi, rec.currency_id.symbol, rec.new_emi,
                     rec.currency_id.symbol, rec.emi_reduction, rec.remaining_tenure)
            else:
                mode_desc = _(
                    "Tenure will reduce from %s to %s months (finish %s months earlier)<br/>"
                    "EMI remains %s"
                ) % (rec.remaining_tenure, rec.new_tenure, rec.tenure_reduction, rec.currency_id.symbol, rec.new_emi)
            
            rec.message_post(body=_(
                "<b>PARTIAL PAYOFF QUOTE GENERATED</b><br/>"
                "Quote Ref: %s<br/>"
                "Payoff Amount: %s %s<br/>"
                "Principal Reduction: %s %s<br/>"
                "Interest Saved: %s %s<br/>"
                "New Outstanding: %s %s<br/><br/>"
                "%s<br/><br/>"
                "Quote valid until: %s"
            ) % (
                rec.name,
                rec.currency_id.symbol, rec.payoff_amount,
                rec.currency_id.symbol, rec.principal_reduction,
                rec.currency_id.symbol, rec.interest_saved,
                rec.currency_id.symbol, rec.new_outstanding,
                mode_desc,
                rec.quote_valid_until,
            ))
    
    def action_accept(self):
        """Customer accepts quote"""
        for rec in self:
            # Check if quote expired
            if fields.Date.today() > rec.quote_valid_until:
                rec.state = "expired"
                raise UserError(_("Quote has expired. Please generate a new quote."))
            
            rec.write({
                "state": "accepted",
            })
            rec.message_post(body=_("Quote accepted by customer."))
    
    def action_apply(self):
        """Apply partial payoff to loan"""
        for rec in self:
            if rec.state not in ["quoted", "accepted"]:
                raise UserError(_("Payoff must be quoted and accepted before application."))
            
            # Check if quote expired
            if fields.Date.today() > rec.quote_valid_until:
                rec.state = "expired"
                raise UserError(_("Quote has expired. Please generate a new quote."))
            
            loan = rec.loan_id
            
            # Create repayment record
            repayment = self.env["alba.loan.repayment"].create({
                "loan_id": loan.id,
                "payment_date": rec.payment_date or fields.Date.today(),
                "amount_paid": rec.payoff_amount,
                "payment_method": rec.payment_method or "bank_transfer",
                "payment_reference": rec.payment_reference or rec.name,
                "notes": _("Partial Payoff - %s") % rec.name,
            })
            repayment.action_post()
            
            # Apply principal reduction to loan
            new_outstanding = loan.outstanding_balance - rec.principal_reduction
            loan.write({
                "outstanding_balance": new_outstanding,
                "installment_amount": rec.new_emi if rec.reduction_mode == "reduce_emi" else loan.installment_amount,
            })
            
            # Regenerate schedule
            loan.action_generate_schedule()
            
            # Update payoff record
            rec.write({
                "state": "applied",
                "repayment_id": repayment.id,
                "processed_by": self.env.user.id,
                "processed_date": fields.Date.today(),
            })
            
            # Log
            if rec.reduction_mode == "reduce_emi":
                mode_result = _(
                    "New EMI: %s %s (reduced by %s %s)<br/>"
                    "Tenure unchanged: %s months"
                ) % (rec.currency_id.symbol, rec.new_emi, rec.currency_id.symbol, rec.emi_reduction, rec.remaining_tenure)
            else:
                mode_result = _(
                    "Tenure reduced to %s months (save %s months)<br/>"
                    "EMI unchanged: %s %s"
                ) % (rec.new_tenure, rec.tenure_reduction, rec.currency_id.symbol, rec.new_emi)
            
            rec.message_post(body=_(
                "<b>PARTIAL PAYOFF APPLIED</b><br/>"
                "Principal Reduced: %s %s<br/>"
                "Interest Saved: %s %s<br/>"
                "New Outstanding: %s %s<br/><br/>"
                "%s"
            ) % (
                rec.currency_id.symbol, rec.principal_reduction,
                rec.currency_id.symbol, rec.interest_saved,
                rec.currency_id.symbol, rec.new_outstanding,
                mode_result,
            ))
            
            loan.message_post(body=_(
                "<b>PARTIAL PAYOFF APPLIED</b><br/>"
                "Reference: %s<br/>"
                "Amount: %s %s<br/>"
                "Principal Reduction: %s %s"
            ) % (rec.name, rec.currency_id.symbol, rec.payoff_amount,
                 rec.currency_id.symbol, rec.principal_reduction))
    
    def action_cancel(self):
        """Cancel draft/quoted payoff"""
        for rec in self:
            if rec.state not in ["draft", "quoted", "accepted"]:
                raise UserError(_("Only draft, quoted, or accepted payoffs can be cancelled."))
            rec.write({
                "state": "cancelled",
            })
    
    def action_reset_to_draft(self):
        """Reset to draft"""
        for rec in self:
            if rec.state not in ["quoted", "accepted", "expired"]:
                raise UserError(_("Can only reset quoted, accepted, or expired payoffs."))
            rec.write({
                "state": "draft",
                "quote_date": False,
            })
