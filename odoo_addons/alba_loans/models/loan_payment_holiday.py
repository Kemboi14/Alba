# -*- coding: utf-8 -*-
"""
Alba Capital Loan Payment Holiday / Deferment
Pause payments for unlimited duration during hardship
Two interest options: Continue (capitalize) or Pause (extend only)
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from datetime import date, timedelta


class AlbaLoanPaymentHoliday(models.Model):
    """Payment Holiday - Pause loan payments during hardship"""
    
    _name = "alba.loan.payment.holiday"
    _description = "Loan Payment Holiday"
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
        index=True,
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
    current_emi = fields.Monetary(
        string="Current EMI",
        currency_field="currency_id",
        related="loan_id.installment_amount",
        store=True,
    )
    
    # Holiday Details
    start_date = fields.Date(
        string="Holiday Start Date",
        required=True,
        tracking=True,
        help="First payment date that will be deferred",
    )
    end_date = fields.Date(
        string="Holiday End Date",
        required=True,
        tracking=True,
        help="Last payment date that will be deferred",
    )
    holiday_months = fields.Integer(
        string="Holiday Duration (Months)",
        compute="_compute_duration",
        store=True,
    )
    
    reason = fields.Selection([
        ("job_loss", "Job Loss / Income Reduction"),
        ("medical", "Medical Emergency"),
        ("business_loss", "Business Loss"),
        ("family_emergency", "Family Emergency"),
        ("natural_disaster", "Natural Disaster"),
        ("other", "Other"),
    ], string="Reason", required=True, tracking=True)
    reason_notes = fields.Text(string="Additional Details")
    
    # Interest Handling
    interest_accrual = fields.Selection([
        ("continue", "Continue Accruing (Capitalize to Principal)"),
        ("pause", "Pause Interest (Extend Maturity Only)"),
    ], string="Interest During Holiday", required=True, default="continue",
       help="Continue: Interest accrues and is added to principal\nPause: No interest, just push dates forward")
    
    # Calculated Financial Impact
    deferred_principal = fields.Monetary(
        string="Deferred Principal",
        currency_field="currency_id",
        compute="_compute_deferred_amounts",
        store=True,
    )
    deferred_interest = fields.Monetary(
        string="Deferred Interest",
        currency_field="currency_id",
        compute="_compute_deferred_amounts",
        store=True,
    )
    total_deferred = fields.Monetary(
        string="Total Deferred Amount",
        currency_field="currency_id",
        compute="_compute_deferred_amounts",
        store=True,
    )
    new_outstanding = fields.Monetary(
        string="New Outstanding (After Holiday)",
        currency_field="currency_id",
        compute="_compute_deferred_amounts",
        store=True,
    )
    new_maturity_date = fields.Date(
        string="New Maturity Date",
        compute="_compute_deferred_amounts",
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
        ("pending", "Pending Approval"),
        ("approved", "Approved"),
        ("active", "Active"),
        ("completed", "Completed"),
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
    
    # Schedule Impact
    schedule_modified = fields.Boolean(string="Schedule Modified", default=False)
    affected_installment_ids = fields.Many2many(
        "alba.repayment.schedule",
        string="Affected Installments",
        readonly=True,
    )
    
    # Eligibility
    is_eligible = fields.Boolean(string="Eligible", compute="_compute_eligibility")
    eligibility_warnings = fields.Text(string="Eligibility Warnings", compute="_compute_eligibility")
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.depends("start_date", "end_date")
    def _compute_duration(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                # Approximate month difference
                delta = rec.end_date - rec.start_date
                rec.holiday_months = max(1, int(delta.days / 30))
            else:
                rec.holiday_months = 0
    
    @api.depends("loan_id", "start_date", "end_date", "interest_accrual", "current_emi")
    def _compute_deferred_amounts(self):
        for rec in self:
            if not rec.loan_id or not rec.start_date or not rec.end_date:
                rec.deferred_principal = 0
                rec.deferred_interest = 0
                rec.total_deferred = 0
                rec.new_outstanding = rec.loan_id.outstanding_balance if rec.loan_id else 0
                rec.new_maturity_date = False
                continue
            
            loan = rec.loan_id
            
            # Find affected installments
            affected = self.env["alba.repayment.schedule"].search([
                ("loan_id", "=", loan.id),
                ("due_date", ">=", rec.start_date),
                ("due_date", "<=", rec.end_date),
                ("status", "!=", "paid"),
            ])
            
            # Calculate deferred principal (sum of principal components)
            rec.deferred_principal = sum(affected.mapped("principal_due"))
            
            # Calculate interest
            if rec.interest_accrual == "continue":
                # Interest continues on current outstanding
                if loan.interest_method == "flat_rate":
                    rate_per_month = loan.interest_rate / 100
                    rec.deferred_interest = rec.deferred_principal * rate_per_month * rec.holiday_months
                else:
                    # Reducing balance - approximate
                    rate_per_month = loan.interest_rate / 100
                    avg_balance = loan.outstanding_balance - (rec.deferred_principal / 2)
                    rec.deferred_interest = avg_balance * rate_per_month * rec.holiday_months
                
                rec.total_deferred = rec.deferred_principal + rec.deferred_interest
                rec.new_outstanding = loan.outstanding_balance + rec.deferred_interest
            else:
                # Pause - no additional interest
                rec.deferred_interest = 0
                rec.total_deferred = rec.deferred_principal
                rec.new_outstanding = loan.outstanding_balance
            
            # Calculate new maturity date
            if loan.maturity_date:
                rec.new_maturity_date = loan.maturity_date + timedelta(days=rec.holiday_months * 30)
            else:
                rec.new_maturity_date = False
    
    @api.depends("loan_id", "start_date", "end_date")
    def _compute_eligibility(self):
        for rec in self:
            if not rec.loan_id:
                rec.is_eligible = False
                rec.eligibility_warnings = "No loan selected"
                return
            
            warnings = []
            loan = rec.loan_id
            
            # Check loan state
            if loan.state != "active":
                warnings.append("❌ Loan must be active")
            
            # Check arrears
            if loan.days_in_arrears > 90:
                warnings.append("❌ Loan is 90+ days overdue")
            
            # Check for existing active holiday
            existing = self.search([
                ("loan_id", "=", loan.id),
                ("state", "in", ["approved", "active"]),
                ("id", "!=", rec.id),
            ])
            if existing:
                warnings.append("❌ Another holiday is already active for this loan")
            
            # Check for pending holiday
            pending = self.search([
                ("loan_id", "=", loan.id),
                ("state", "in", ["draft", "pending"]),
                ("id", "!=", rec.id),
            ])
            if pending:
                warnings.append("⚠️ Another holiday is pending approval")
            
            # Check recent payment history
            if loan.days_in_arrears > 60:
                warnings.append("⚠️ Loan has >60 days arrears - manager approval required")
            
            if warnings:
                rec.is_eligible = False
                rec.eligibility_warnings = "\n".join(warnings)
            else:
                rec.is_eligible = True
                rec.eligibility_warnings = "✅ Loan is eligible for payment holiday"
    
    # =========================================================================
    # ORM Overrides
    # =========================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("alba.loan.payment.holiday") or "New"
        return super().create(vals_list)
    
    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                if rec.end_date < rec.start_date:
                    raise UserError(_("End date must be after start date."))
                if rec.start_date < fields.Date.today():
                    raise UserError(_("Holiday cannot start in the past."))
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_submit(self):
        """Submit holiday request for approval"""
        for rec in self:
            if not rec.is_eligible:
                raise UserError(_("Holiday request is not eligible:\n%s") % rec.eligibility_warnings)
            
            rec.write({"state": "pending"})
            rec.message_post(body=_("Payment holiday request submitted for approval."))
    
    def action_approve(self):
        """Approve holiday request"""
        for rec in self:
            # Longer holidays need higher approval
            if rec.holiday_months > 3:
                if not self.env.user.has_group("alba_loans.group_operations_manager"):
                    raise UserError(_("Holidays over 3 months require Operations Manager approval."))
            elif rec.loan_id.days_in_arrears > 60:
                if not self.env.user.has_group("alba_loans.group_loan_manager"):
                    raise UserError(_("Holidays for loans with >60 days arrears require Loan Manager approval."))
            else:
                if not self.env.user.has_group("alba_loans.group_loan_manager"):
                    raise UserError(_("Payment holidays require Loan Manager approval."))
            
            rec.write({
                "state": "approved",
                "approved_by": self.env.user.id,
                "approved_date": fields.Date.today(),
            })
            rec.message_post(body=_("Payment holiday approved by %s.") % self.env.user.name)
    
    def action_activate(self):
        """Activate the holiday and modify schedule"""
        for rec in self:
            if rec.state != "approved":
                raise UserError(_("Holiday must be approved before activation."))
            
            # Find affected installments
            affected = self.env["alba.repayment.schedule"].search([
                ("loan_id", "=", rec.loan_id.id),
                ("due_date", ">=", rec.start_date),
                ("due_date", "<=", rec.end_date),
                ("is_paid", "=", False),
            ])
            
            if not affected:
                raise UserError(_("No unpaid installments found in the holiday period."))
            
            # Mark as deferred
            for inst in affected:
                inst.write({
                    "status": "deferred",
                    "notes": (inst.notes or "") + " [Deferred due to payment holiday]",
                })
            
            # Push subsequent installments forward
            subsequent = self.env["alba.repayment.schedule"].search([
                ("loan_id", "=", rec.loan_id.id),
                ("due_date", ">", rec.end_date),
                ("is_paid", "=", False),
            ])
            
            for inst in subsequent:
                new_due_date = inst.due_date + timedelta(days=rec.holiday_months * 30)
                inst.write({"due_date": new_due_date})
            
            # Handle interest capitalization
            if rec.interest_accrual == "continue" and rec.deferred_interest > 0:
                rec.loan_id.write({
                    "outstanding_balance": rec.loan_id.outstanding_balance + rec.deferred_interest,
                    "accrued_interest": (rec.loan_id.accrued_interest or 0) + rec.deferred_interest,
                })
            
            rec.write({
                "state": "active",
                "schedule_modified": True,
                "affected_installment_ids": [(6, 0, affected.ids)],
            })
            
            rec.message_post(body=_(
                "<b>PAYMENT HOLIDAY ACTIVATED</b><br/>"
                "Period: %s to %s<br/>"
                "Duration: %s months<br/>"
                "Interest Mode: %s<br/>"
                "Installments Deferred: %s"
            ) % (rec.start_date, rec.end_date, rec.holiday_months,
                 dict(rec._fields["interest_accrual"].selection).get(rec.interest_accrual),
                 len(affected)))
    
    def action_complete(self):
        """Mark holiday as completed"""
        for rec in self:
            if rec.state != "active":
                raise UserError(_("Only active holidays can be completed."))
            
            # Check if end date has passed
            if fields.Date.today() < rec.end_date:
                raise UserError(_("Cannot complete - holiday end date has not passed yet."))
            
            rec.write({"state": "completed"})
            rec.message_post(body=_("Payment holiday completed. Normal repayments resumed."))
    
    def action_reject(self):
        """Reject holiday request"""
        for rec in self:
            rec.write({"state": "rejected"})
            rec.message_post(body=_("Payment holiday rejected by %s.") % self.env.user.name)
    
    def action_cancel(self):
        """Cancel draft/pending holiday"""
        for rec in self:
            if rec.state not in ["draft", "pending"]:
                raise UserError(_("Only draft or pending holidays can be cancelled."))
            rec.write({"state": "cancelled"})
