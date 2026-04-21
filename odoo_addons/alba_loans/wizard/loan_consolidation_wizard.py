# -*- coding: utf-8 -*-
"""
Consolidation Wizard
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaLoanConsolidationWizard(models.TransientModel):
    _name = "alba.loan.consolidation.wizard"
    _description = "Loan Consolidation Wizard"
    
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        required=True,
    )
    loan_ids = fields.Many2many(
        "alba.loan",
        string="Loans to Consolidate",
        domain="[('customer_id', '=', customer_id), ('state', 'in', ['active', 'overdue'])]",
        required=True,
    )
    
    consolidation_type = fields.Selection([
        ("blend", "Blend Rates"),
        ("best", "Best Rate"),
        ("new", "New Rate"),
    ], string="Rate Method", default="blend")
    
    currency_id = fields.Many2one(
        "res.currency",
        related="customer_id.currency_id",
    )
    
    def action_create_consolidation(self):
        self.ensure_one()
        
        if len(self.loan_ids) < 2:
            raise UserError(_("Select at least 2 loans to consolidate."))
        
        consolidation = self.env["alba.loan.consolidation"].create({
            "customer_id": self.customer_id.id,
            "loan_ids": [(6, 0, self.loan_ids.ids)],
            "consolidation_type": self.consolidation_type,
        })
        
        consolidation.action_generate_quote()
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Consolidation Quote"),
            "res_model": "alba.loan.consolidation",
            "res_id": consolidation.id,
            "view_mode": "form",
            "target": "current",
        }
