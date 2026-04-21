# -*- coding: utf-8 -*-
"""
Alba Capital Loan Partial Payoff Wizard
Quick interface for calculating and processing partial payoffs
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaLoanPartialPayoffWizard(models.TransientModel):
    """Wizard to calculate and process partial payoff"""
    
    _name = "alba.loan.partial.payoff.wizard"
    _description = "Loan Partial Payoff Wizard"
    
    # Loan
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="cascade",
        default=lambda self: self._default_loan(),
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="loan_id.customer_id",
        readonly=True,
    )
    
    # Current Details
    current_outstanding = fields.Monetary(
        string="Current Outstanding",
        currency_field="currency_id",
        related="loan_id.outstanding_balance",
        readonly=True,
    )
    current_emi = fields.Monetary(
        string="Current EMI",
        currency_field="currency_id",
        related="loan_id.installment_amount",
        readonly=True,
    )
    remaining_tenure = fields.Integer(
        string="Remaining Months",
        related="loan_id.remaining_tenure",
        readonly=True,
    )
    
    # Payoff Details
    payoff_amount = fields.Monetary(
        string="Payoff Amount",
        currency_field="currency_id",
        required=True,
        help="Extra amount customer wants to pay to reduce principal",
    )
    reduction_mode = fields.Selection([
        ("reduce_emi", "Reduce EMI (Keep Same Tenure)"),
        ("reduce_tenure", "Reduce Tenure (Keep Same EMI)"),
    ], string="Reduction Mode", required=True, default="reduce_emi")
    
    # Calculated Results
    principal_reduction = fields.Monetary(
        string="Principal Reduction",
        currency_field="currency_id",
        compute="_compute_results",
    )
    interest_saved = fields.Monetary(
        string="Interest Saved",
        currency_field="currency_id",
        compute="_compute_results",
    )
    new_outstanding = fields.Monetary(
        string="New Outstanding",
        currency_field="currency_id",
        compute="_compute_results",
    )
    new_emi = fields.Monetary(
        string="New EMI",
        currency_field="currency_id",
        compute="_compute_results",
    )
    new_tenure = fields.Integer(
        string="New Tenure (Months)",
        compute="_compute_results",
    )
    emi_reduction = fields.Monetary(
        string="EMI Reduction",
        currency_field="currency_id",
        compute="_compute_results",
    )
    tenure_reduction = fields.Integer(
        string="Tenure Reduction (Months)",
        compute="_compute_results",
    )
    
    # Currency
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="loan_id.currency_id",
    )
    
    # Validation
    is_valid = fields.Boolean(string="Valid", compute="_compute_validation")
    validation_message = fields.Char(string="Validation", compute="_compute_validation")
    
    # =========================================================================
    # Defaults
    # =========================================================================
    
    def _default_loan(self):
        return self.env.context.get("active_id") or False
    
    # =========================================================================
    # Compute
    # =========================================================================
    
    @api.depends("loan_id", "payoff_amount", "reduction_mode")
    def _compute_results(self):
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
            
            # Principal reduction = payoff amount
            rec.principal_reduction = rec.payoff_amount
            rec.new_outstanding = current_outstanding - rec.payoff_amount
            
            # Interest saved calculation
            if loan.interest_method == "flat_rate":
                rate_per_month = loan.interest_rate / 100
                rec.interest_saved = rec.payoff_amount * rate_per_month * loan.remaining_tenure
            else:
                rate_per_month = loan.interest_rate / 100
                avg_reduction = rec.payoff_amount / 2
                rec.interest_saved = avg_reduction * rate_per_month * loan.remaining_tenure
            
            # Calculate based on mode
            if rec.reduction_mode == "reduce_emi":
                rec.new_tenure = loan.remaining_tenure
                if loan.remaining_tenure > 0:
                    rec.new_emi = rec.new_outstanding / loan.remaining_tenure
                else:
                    rec.new_emi = 0
                rec.emi_reduction = loan.installment_amount - rec.new_emi
                rec.tenure_reduction = 0
            else:
                rec.new_emi = loan.installment_amount
                if loan.installment_amount > 0:
                    rec.new_tenure = int(rec.new_outstanding / loan.installment_amount)
                else:
                    rec.new_tenure = 0
                rec.emi_reduction = 0
                rec.tenure_reduction = loan.remaining_tenure - rec.new_tenure
    
    @api.depends("loan_id", "payoff_amount", "current_outstanding")
    def _compute_validation(self):
        for rec in self:
            if not rec.loan_id:
                rec.is_valid = False
                rec.validation_message = "No loan selected"
                return
            
            if rec.payoff_amount <= 0:
                rec.is_valid = False
                rec.validation_message = "Payoff amount must be positive"
            elif rec.payoff_amount >= rec.current_outstanding:
                rec.is_valid = False
                rec.validation_message = "Use Early Settlement for full payoff"
            else:
                rec.is_valid = True
                rec.validation_message = "✅ Valid payoff amount"
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_generate_quote(self):
        """Generate quote"""
        self.ensure_one()
        
        if not self.is_valid:
            raise UserError(_("Invalid payoff: %s") % self.validation_message)
        
        # Create partial payoff record
        payoff = self.env["alba.loan.partial.payoff"].create({
            "loan_id": self.loan_id.id,
            "payoff_amount": self.payoff_amount,
            "reduction_mode": self.reduction_mode,
        })
        
        # Generate quote
        payoff.action_generate_quote()
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Payoff Quote"),
            "res_model": "alba.loan.partial.payoff",
            "res_id": payoff.id,
            "view_mode": "form",
            "target": "current",
        }
    
    def action_apply_immediately(self):
        """Apply payoff immediately (if customer paying now)"""
        self.ensure_one()
        
        if not self.is_valid:
            raise UserError(_("Invalid payoff: %s") % self.validation_message)
        
        # Create and quote
        result = self.action_generate_quote()
        payoff = self.env["alba.loan.partial.payoff"].browse(result["res_id"])
        
        # Auto-accept (since customer is paying now)
        payoff.action_accept()
        
        # Apply
        payoff.action_apply()
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Payoff Applied"),
            "res_model": "alba.loan.partial.payoff",
            "res_id": payoff.id,
            "view_mode": "form",
            "target": "current",
        }
