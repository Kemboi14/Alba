# -*- coding: utf-8 -*-
"""
Alba Capital Loan Top-Up
Quick principal increase without full restructure workflow
Top-Up is FREE (0% fee) - encourages usage over restructure
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta


class AlbaLoanTopup(models.Model):
    """Loan Top-Up - Increase principal on active loan"""
    
    _name = "alba.loan.topup"
    _description = "Loan Top-Up"
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
        index=True,
        domain="[('state', '=', 'active')]",
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="loan_id.customer_id",
        store=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="loan_id.customer_id.partner_id",
        store=True,
    )
    
    # Current Loan Details (for reference)
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
    
    # Top-Up Details
    topup_amount = fields.Monetary(
        string="Top-Up Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
        help="Additional funds to disburse to customer",
    )
    new_principal = fields.Monetary(
        string="New Principal Amount",
        currency_field="currency_id",
        compute="_compute_new_principal",
        store=True,
    )
    purpose = fields.Selection([
        ("emergency", "Emergency/Medical"),
        ("business", "Business Expansion"),
        ("education", "Education/School Fees"),
        ("home_improvement", "Home Improvement"),
        ("debt_consolidation", "Debt Consolidation"),
        ("other", "Other"),
    ], string="Purpose", required=True, tracking=True)
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
        tracking=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Disbursement Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Bank or Cash journal for disbursement",
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
        ("pending", "Pending Approval"),
        ("approved", "Approved"),
        ("disbursed", "Disbursed"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ], string="Status", default="draft", tracking=True)
    
    # Approval
    requested_by = fields.Many2one(
        "res.users",
        string="Requested By",
        default=lambda self: self.env.user,
        readonly=True,
    )
    approved_by = fields.Many2one(
        "res.users",
        string="Approved By",
        readonly=True,
    )
    approved_date = fields.Date(string="Approved Date")
    rejection_reason = fields.Text(string="Rejection Reason")
    
    # Accounting
    disbursement_move_id = fields.Many2one(
        "account.move",
        string="Disbursement Journal Entry",
        readonly=True,
        copy=False,
    )
    
    # Schedule
    schedule_regenerated = fields.Boolean(string="Schedule Regenerated", default=False)
    
    # Eligibility Check Results
    is_eligible = fields.Boolean(string="Eligible", compute="_compute_eligibility")
    eligibility_warnings = fields.Text(string="Eligibility Warnings", compute="_compute_eligibility")
    
    # =========================================================================
    # Constraints
    # =========================================================================
    
    _positive_topup = models.Constraint(
        "CHECK(topup_amount > 0)",
        "Top-up amount must be positive."
    )
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.depends("loan_id", "topup_amount")
    def _compute_new_principal(self):
        for rec in self:
            if rec.loan_id:
                rec.new_principal = rec.loan_id.principal_amount + rec.topup_amount
            else:
                rec.new_principal = rec.topup_amount
    
    @api.depends("loan_id", "topup_amount")
    def _compute_eligibility(self):
        for rec in self:
            warnings = []
            eligible = True
            
            if not rec.loan_id:
                rec.is_eligible = False
                rec.eligibility_warnings = "No loan selected"
                continue
            
            loan = rec.loan_id
            
            # Check loan state
            if loan.state != "active":
                eligible = False
                warnings.append("Loan must be active (not %s)" % loan.state)
            
            # Check days in arrears
            if loan.days_in_arrears > 90:
                eligible = False
                warnings.append("Loan is 90+ days overdue")
            
            # Check recent repayment history
            recent_missed = self.env["alba.repayment.schedule"].search_count([
                ("loan_id", "=", loan.id),
                ("due_date", ">=", fields.Date.today() - timedelta(days=180)),
                ("status", "!=", "paid"),
                ("due_date", "<", fields.Date.today()),
            ])
            if recent_missed > 2:
                warnings.append("More than 2 missed payments in last 6 months")
            
            # Check if already has pending topup
            existing = self.search([
                ("loan_id", "=", loan.id),
                ("state", "in", ["draft", "pending"]),
                ("id", "!=", rec.id),
            ])
            if existing:
                eligible = False
                warnings.append("Another pending top-up exists for this loan")
            
            rec.is_eligible = eligible
            rec.eligibility_warnings = "\n".join(warnings) if warnings else "Eligible"
    
    # =========================================================================
    # ORM Overrides
    # =========================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("alba.loan.topup") or "New"
        return super().create(vals_list)
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_submit(self):
        """Submit top-up for approval"""
        for rec in self:
            if not rec.is_eligible:
                raise UserError(_("Top-up is not eligible:\n%s") % rec.eligibility_warnings)
            
            rec.write({
                "state": "pending",
            })
            rec.message_post(body=_("Top-up request submitted for approval."))
    
    def action_approve(self):
        """Approve top-up request"""
        for rec in self:
            # Check approval authority based on amount
            if rec.topup_amount > 200000:  # 200K threshold
                if not self.env.user.has_group("alba_loans.group_operations_manager"):
                    raise UserError(_("Top-ups over 200K require Operations Manager approval."))
            elif rec.topup_amount > 50000:  # 50K threshold
                if not self.env.user.has_group("alba_loans.group_loan_manager"):
                    raise UserError(_("Top-ups over 50K require Loan Manager approval."))
            
            rec.write({
                "state": "approved",
                "approved_by": self.env.user.id,
                "approved_date": fields.Date.today(),
            })
            rec.message_post(body=_("Top-up approved by %s.") % self.env.user.name)
    
    def action_disburse(self):
        """Disburse top-up amount and update loan"""
        for rec in self:
            if rec.state != "approved":
                raise UserError(_("Top-up must be approved before disbursement."))
            
            loan = rec.loan_id
            
            # Post disbursement entry
            rec._post_disbursement_entry()
            
            # Update loan principal
            new_principal = loan.principal_amount + rec.topup_amount
            new_outstanding = loan.outstanding_balance + rec.topup_amount
            
            loan.write({
                "principal_amount": new_principal,
                "outstanding_balance": new_outstanding,
            })
            
            # Regenerate schedule
            loan.action_generate_schedule()
            rec.schedule_regenerated = True
            
            rec.write({
                "state": "disbursed",
                "disbursement_date": fields.Date.today(),
            })
            
            # Send Email
            template = self.env.ref('alba_loans.email_template_loan_topup', raise_if_not_found=False)
            if template:
                template.send_mail(rec.id, force_send=True)

            rec.message_post(body=_(
                "<b>TOP-UP DISBURSED</b><br/>"
                "Amount: %s %s<br/>"
                "New Principal: %s %s<br/>"
                "Method: %s"
            ) % (rec.currency_id.symbol, rec.topup_amount, 
                 rec.currency_id.symbol, new_principal,
                 dict(rec._fields["disbursement_method"].selection).get(rec.disbursement_method)))
            
            loan.message_post(body=_(
                "<b>TOP-UP APPLIED</b><br/>"
                "Reference: %s<br/>"
                "Amount Added: %s %s<br/>"
                "New Principal: %s %s"
            ) % (rec.name, rec.currency_id.symbol, rec.topup_amount,
                 rec.currency_id.symbol, new_principal))
    
    def _post_disbursement_entry(self):
        """Create accounting entry for top-up disbursement"""
        self.ensure_one()
        
        loan_product = self.loan_id.loan_product_id
        if not loan_product.account_loan_receivable_id:
            raise UserError(_("Loan receivable account not configured for product %s") % loan_product.name)
        
        if not self.journal_id:
            # Auto-select journal if not specified
            self.journal_id = self.env["account.journal"].search([
                ("type", "=", "bank"),
            ], limit=1)
        
        if not self.journal_id:
            raise UserError(_("No bank journal available for disbursement."))
        
        # DR Loan Receivable (increase balance)
        # CR Bank/Cash (disburse funds)
        move_vals = {
            "journal_id": self.journal_id.id,
            "date": self.disbursement_date,
            "ref": _("Top-Up: %s - %s") % (self.name, self.loan_id.loan_number),
            "line_ids": [
                (0, 0, {
                    "account_id": loan_product.account_loan_receivable_id.id,
                    "partner_id": self.partner_id.id,
                    "name": _("Top-Up - %s") % self.name,
                    "debit": self.topup_amount,
                }),
                (0, 0, {
                    "account_id": self.journal_id.default_account_id.id,
                    "partner_id": self.partner_id.id,
                    "name": _("Top-Up Disbursement - %s") % self.name,
                    "credit": self.topup_amount,
                }),
            ],
        }
        
        move = self.env["account.move"].create(move_vals)
        move.action_post()
        self.disbursement_move_id = move.id
    
    def action_reject(self):
        """Reject top-up request"""
        for rec in self:
            rec.write({
                "state": "rejected",
            })
            rec.message_post(body=_("Top-up rejected by %s.") % self.env.user.name)
    
    def action_cancel(self):
        """Cancel draft/pending top-up"""
        for rec in self:
            if rec.state not in ["draft", "pending"]:
                raise UserError(_("Only draft or pending top-ups can be cancelled."))
            rec.write({
                "state": "cancelled",
            })
    
    def action_reset_to_draft(self):
        """Reset rejected top-up to draft"""
        for rec in self:
            if rec.state != "rejected":
                raise UserError(_("Only rejected top-ups can be reset."))
            rec.write({
                "state": "draft",
                "approved_by": False,
                "approved_date": False,
            })

    def action_view_loan(self):
        """Navigate to the linked loan"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loan"),
            "res_model": "alba.loan",
            "view_mode": "form",
            "res_id": self.loan_id.id,
        }
