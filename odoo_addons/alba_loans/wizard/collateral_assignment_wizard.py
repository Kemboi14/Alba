# -*- coding: utf-8 -*-
"""
Collateral Assignment Wizard
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaCollateralAssignmentWizard(models.TransientModel):
    _name = "alba.collateral.assignment.wizard"
    _description = "Collateral Assignment Wizard"
    
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        default=lambda self: self._default_loan(),
    )
    customer_id = fields.Many2one(
        "alba.customer",
        related="loan_id.customer_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="loan_id.currency_id",
        readonly=True,
    )
    collateral_id = fields.Many2one(
        "alba.collateral",
        string="Collateral",
        required=True,
        domain="['|', ('status', '=', 'available'), ('status', '=', 'pledged')]",
    )
    
    ltv_ratio = fields.Float(
        string="LTV Ratio (%)",
        compute="_compute_ltv",
    )
    ltv_status = fields.Selection([
        ("good", "Good"),
        ("caution", "Caution"),
        ("exceeded", "Exceeded"),
    ], string="LTV Status", compute="_compute_ltv")
    
    def _default_loan(self):
        return self.env.context.get("active_id")
    
    @api.depends("loan_id", "collateral_id")
    def _compute_ltv(self):
        for rec in self:
            if rec.loan_id and rec.collateral_id and rec.collateral_id.valuation_amount:
                rec.ltv_ratio = (rec.loan_id.principal_amount / rec.collateral_id.valuation_amount) * 100
                # Simple check
                if rec.ltv_ratio > 70:
                    rec.ltv_status = "exceeded"
                elif rec.ltv_ratio > 60:
                    rec.ltv_status = "caution"
                else:
                    rec.ltv_status = "good"
            else:
                rec.ltv_ratio = 0
                rec.ltv_status = "good"
    
    def action_assign(self):
        self.ensure_one()
        
        if not self.collateral_id:
            raise UserError(_("Please select collateral."))
        
        if self.ltv_status == "exceeded":
            raise UserError(_("LTV ratio exceeds limit. Please select different collateral or add more."))
        
        assignment = self.env["alba.loan.collateral"].create({
            "loan_id": self.loan_id.id,
            "collateral_id": self.collateral_id.id,
            "status": "pledged",
        })
        
        # Update collateral status
        self.collateral_id.write({"status": "pledged"})
        
        return {"type": "ir.actions.act_window_close"}
