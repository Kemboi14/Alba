# -*- coding: utf-8 -*-
"""
Refinance Wizard
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaLoanRefinanceWizard(models.TransientModel):
    _name = "alba.loan.refinance.wizard"
    _description = "Loan Refinance Wizard"
    
    original_loan_id = fields.Many2one(
        "alba.loan",
        string="Original Loan",
        required=True,
        default=lambda self: self._default_loan(),
    )
    customer_id = fields.Many2one(
        "alba.customer",
        related="original_loan_id.customer_id",
        readonly=True,
    )
    original_outstanding = fields.Monetary(
        related="original_loan_id.outstanding_balance",
        currency_field="currency_id",
        readonly=True,
    )
    original_rate = fields.Float(
        related="original_loan_id.interest_rate",
        readonly=True,
    )
    
    new_product_id = fields.Many2one(
        "alba.loan.product",
        string="New Product",
        required=True,
    )
    new_principal = fields.Monetary(
        string="New Principal",
        currency_field="currency_id",
        required=True,
    )
    new_interest_rate = fields.Float(
        string="New Interest Rate (%)",
        digits=(5, 2),
        required=True,
    )
    new_tenure_months = fields.Integer(
        string="New Tenure (Months)",
        required=True,
    )
    
    currency_id = fields.Many2one(
        "res.currency",
        related="original_loan_id.currency_id",
    )
    
    def _default_loan(self):
        return self.env.context.get("active_id")
    
    def action_create_refinance(self):
        self.ensure_one()
        
        if not self.new_product_id:
            raise UserError(_("Please select a new product."))
        
        refinance = self.env["alba.loan.refinance"].create({
            "original_loan_id": self.original_loan_id.id,
            "new_product_id": self.new_product_id.id,
            "new_principal": self.new_principal,
            "new_interest_rate": self.new_interest_rate,
            "new_tenure_months": self.new_tenure_months,
        })
        
        refinance.action_generate_quote()
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Refinance Quote"),
            "res_model": "alba.loan.refinance",
            "res_id": refinance.id,
            "view_mode": "form",
            "target": "current",
        }
