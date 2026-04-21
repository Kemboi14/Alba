# -*- coding: utf-8 -*-
"""
Alba Capital Loan Top-Up Wizard
Quick interface for creating top-up requests from loan form
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaLoanTopupWizard(models.TransientModel):
    """Wizard to create loan top-up quickly"""
    
    _name = "alba.loan.topup.wizard"
    _description = "Loan Top-Up Wizard"
    
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
    current_outstanding = fields.Monetary(
        string="Current Outstanding",
        currency_field="currency_id",
        related="loan_id.outstanding_balance",
        readonly=True,
    )
    current_principal = fields.Monetary(
        string="Current Principal",
        currency_field="currency_id",
        related="loan_id.principal_amount",
        readonly=True,
    )
    
    # Top-Up Details
    topup_amount = fields.Monetary(
        string="Top-Up Amount",
        currency_field="currency_id",
        required=True,
    )
    new_principal = fields.Monetary(
        string="New Principal",
        currency_field="currency_id",
        compute="_compute_new_principal",
    )
    purpose = fields.Selection([
        ("emergency", "Emergency/Medical"),
        ("business", "Business Expansion"),
        ("education", "Education/School Fees"),
        ("home_improvement", "Home Improvement"),
        ("debt_consolidation", "Debt Consolidation"),
        ("other", "Other"),
    ], string="Purpose", required=True)
    purpose_notes = fields.Text(string="Additional Notes")
    
    # Disbursement
    disbursement_method = fields.Selection([
        ("bank_transfer", "Bank Transfer"),
        ("mpesa", "M-Pesa"),
        ("cash", "Cash"),
    ], string="Disbursement Method", required=True, default="bank_transfer")
    disbursement_date = fields.Date(
        string="Disbursement Date",
        required=True,
        default=fields.Date.today,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Disbursement Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
    )
    
    # Currency
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="loan_id.currency_id",
    )
    
    # Eligibility
    is_eligible = fields.Boolean(string="Eligible", compute="_compute_eligibility")
    eligibility_message = fields.Text(string="Eligibility", compute="_compute_eligibility")
    
    # =========================================================================
    # Defaults
    # =========================================================================
    
    def _default_loan(self):
        """Get loan from context"""
        return self.env.context.get("active_id") or False
    
    # =========================================================================
    # Compute
    # =========================================================================
    
    @api.depends("loan_id", "topup_amount")
    def _compute_new_principal(self):
        for rec in self:
            if rec.loan_id and rec.topup_amount:
                rec.new_principal = rec.loan_id.principal_amount + rec.topup_amount
            else:
                rec.new_principal = 0
    
    @api.depends("loan_id", "topup_amount")
    def _compute_eligibility(self):
        for rec in self:
            if not rec.loan_id:
                rec.is_eligible = False
                rec.eligibility_message = "No loan selected"
                return
            
            warnings = []
            loan = rec.loan_id
            
            # Check loan state
            if loan.state != "active":
                warnings.append("❌ Loan must be active (currently: %s)" % loan.state)
            
            # Check arrears
            if loan.days_in_arrears > 90:
                warnings.append("❌ Loan is 90+ days overdue")
            
            # Check existing pending topup
            existing = self.env["alba.loan.topup"].search([
                ("loan_id", "=", loan.id),
                ("state", "in", ["draft", "pending"]),
            ])
            if existing:
                warnings.append("❌ Pending top-up already exists")
            
            if warnings:
                rec.is_eligible = False
                rec.eligibility_message = "\n".join(warnings)
            else:
                rec.is_eligible = True
                rec.eligibility_message = "✅ Loan is eligible for top-up"
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_create_topup(self):
        """Create the top-up request"""
        self.ensure_one()
        
        if not self.is_eligible:
            raise UserError(_("Cannot create top-up:\n%s") % self.eligibility_message)
        
        if self.topup_amount <= 0:
            raise UserError(_("Top-up amount must be positive."))
        
        # Auto-select journal if not specified
        journal = self.journal_id
        if not journal:
            journal = self.env["account.journal"].search([
                ("type", "=", "bank"),
            ], limit=1)
        
        # Create top-up
        topup = self.env["alba.loan.topup"].create({
            "loan_id": self.loan_id.id,
            "topup_amount": self.topup_amount,
            "purpose": self.purpose,
            "purpose_notes": self.purpose_notes,
            "disbursement_method": self.disbursement_method,
            "disbursement_date": self.disbursement_date,
            "journal_id": journal.id if journal else False,
        })
        
        # Auto-submit for approval
        topup.action_submit()
        
        # Return action to view created top-up
        return {
            "type": "ir.actions.act_window",
            "name": _("Top-Up Created"),
            "res_model": "alba.loan.topup",
            "res_id": topup.id,
            "view_mode": "form",
            "target": "current",
        }
    
    def action_create_and_approve(self):
        """Create and auto-approve (for small amounts < 50K)"""
        self.ensure_one()
        
        if self.topup_amount >= 50000:
            raise UserError(_("Auto-approval only for amounts under 50K."))
        
        # Create
        result = self.action_create_topup()
        topup = self.env["alba.loan.topup"].browse(result["res_id"])
        
        # Approve
        topup.action_approve()
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Top-Up Approved"),
            "res_model": "alba.loan.topup",
            "res_id": topup.id,
            "view_mode": "form",
            "target": "current",
        }
