# -*- coding: utf-8 -*-
"""
Payment Holiday Wizard
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaLoanPaymentHolidayWizard(models.TransientModel):
    _name = "alba.loan.payment.holiday.wizard"
    _description = "Payment Holiday Wizard"
    
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
    current_outstanding = fields.Monetary(
        related="loan_id.outstanding_balance",
        currency_field="currency_id",
        readonly=True,
    )
    
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    reason = fields.Selection([
        ("job_loss", "Job Loss / Income Reduction"),
        ("medical", "Medical Emergency"),
        ("business_loss", "Business Loss"),
        ("family_emergency", "Family Emergency"),
        ("natural_disaster", "Natural Disaster"),
        ("other", "Other"),
    ], string="Reason", required=True)
    reason_notes = fields.Text(string="Additional Notes")
    interest_accrual = fields.Selection([
        ("continue", "Continue Accruing (Capitalize)"),
        ("pause", "Pause Interest"),
    ], string="Interest Handling", default="continue")
    
    currency_id = fields.Many2one(
        "res.currency",
        related="loan_id.currency_id",
    )
    
    is_eligible = fields.Boolean(string="Eligible", compute="_compute_eligibility")
    eligibility_message = fields.Text(string="Eligibility", compute="_compute_eligibility")
    
    def _default_loan(self):
        return self.env.context.get("active_id")
    
    @api.depends("loan_id")
    def _compute_eligibility(self):
        for rec in self:
            if not rec.loan_id:
                rec.is_eligible = False
                rec.eligibility_message = "No loan selected"
                return
            
            loan = rec.loan_id
            warnings = []
            
            if loan.state != "active":
                warnings.append("❌ Loan not active")
            if loan.days_in_arrears > 90:
                warnings.append("❌ 90+ days overdue")
            
            if warnings:
                rec.is_eligible = False
                rec.eligibility_message = "\n".join(warnings)
            else:
                rec.is_eligible = True
                rec.eligibility_message = "✅ Eligible"
    
    def action_create_holiday(self):
        self.ensure_one()
        if not self.is_eligible:
            raise UserError(_("Not eligible: %s") % self.eligibility_message)
        
        holiday = self.env["alba.loan.payment.holiday"].create({
            "loan_id": self.loan_id.id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "reason": self.reason,
            "reason_notes": self.reason_notes,
            "interest_accrual": self.interest_accrual,
        })
        
        holiday.action_submit()
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Payment Holiday Created"),
            "res_model": "alba.loan.payment.holiday",
            "res_id": holiday.id,
            "view_mode": "form",
            "target": "current",
        }
