# -*- coding: utf-8 -*-
"""
Alba Capital Full Guarantor Management
Tracks guarantor details, verifications, and liability
Syncs with Django portal guarantor data
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from markupsafe import Markup


class AlbaGuarantor(models.Model):
    """Guarantor Master Data - Independent of specific loans"""
    
    _name = "alba.guarantor"
    _description = "Loan Guarantor"
    _order = "name asc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    
    # Basic Information
    partner_id = fields.Many2one(
        "res.partner",
        string="Related Contact",
        required=True,
        ondelete="restrict",
        help="The partner record for this guarantor. Stores name, phone, email, and documents.",
    )
    name = fields.Char(related="partner_id.name", store=True, readonly=False)
    id_number = fields.Char(related="partner_id.id_number", store=True, readonly=False)
    id_type = fields.Selection(related="partner_id.id_type", store=True, readonly=False)
    
    # Contact (Related to Partner)
    phone = fields.Char(related="partner_id.phone", store=True, readonly=False)
    email = fields.Char(related="partner_id.email", store=True, readonly=False)
    address = fields.Char(related="partner_id.street", string="Physical Address", readonly=False)
    
    # Employment (Related to Partner)
    employer_id = fields.Many2one(related="partner_id.employer_id", store=True, readonly=False)
    employer_name = fields.Char(related="employer_id.name", string="Employer Name", readonly=True)
    employer_phone = fields.Char(related="employer_id.phone", string="Employer Phone", readonly=True)
    job_title = fields.Char(related="partner_id.job_title", store=True, readonly=False)
    monthly_income = fields.Monetary(related="partner_id.monthly_income", store=True, readonly=False)
    
    # Currency
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    
    # Status
    kyc_status = fields.Selection([
        ("pending", "Pending Verification"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
    ], string="KYC Status", default="pending", tracking=True)
    blacklisted = fields.Boolean(
        string="Blacklisted",
        default=False,
        help="Set to True if this guarantor has defaulted on guarantee before",
    )
    blacklist_reason = fields.Text(string="Blacklist Reason")
    
    # Guarantor Limits
    max_guarantee_limit = fields.Monetary(
        string="Max Guarantee Limit",
        currency_field="currency_id",
        compute="_compute_limits",
        store=True,
        help="Maximum amount this guarantor can guarantee (typically 3x monthly income)",
    )
    total_guaranteed = fields.Monetary(
        string="Total Currently Guaranteed",
        currency_field="currency_id",
        compute="_compute_limits",
        store=True,
    )
    available_capacity = fields.Monetary(
        string="Available Guarantee Capacity",
        currency_field="currency_id",
        compute="_compute_limits",
        store=True,
    )
    guarantee_count = fields.Integer(
        string="Active Guarantees",
        compute="_compute_limits",
        store=True,
    )
    
    # Relations
    loan_guarantor_ids = fields.One2many(
        "alba.loan.guarantor",
        "guarantor_id",
        string="Loan Guarantees",
    )
    
    # Django Sync
    django_guarantor_id = fields.Integer(
        string="Django Guarantor ID",
        index=True,
        copy=False,
        help="Primary key from Django portal",
    )
    
    # Documents
    document_ids = fields.One2many(
        "alba.guarantor.document",
        "guarantor_id",
        string="Documents",
    )
    
    # Activity
    last_verification_date = fields.Date(string="Last Verified On")
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.depends("monthly_income", "loan_guarantor_ids", "loan_guarantor_ids.status")
    def _compute_limits(self):
        for rec in self:
            # Max limit = 3x monthly income
            rec.max_guarantee_limit = (rec.monthly_income or 0) * 3
            
            # Calculate active guarantees
            active_guarantees = rec.loan_guarantor_ids.filtered(
                lambda g: g.status in ["confirmed", "pledged"]
            )
            rec.guarantee_count = len(active_guarantees)
            rec.total_guaranteed = sum(g.guarantee_amount for g in active_guarantees)
            rec.available_capacity = rec.max_guarantee_limit - rec.total_guaranteed
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_verify(self):
        """Mark guarantor KYC as verified"""
        for rec in self:
            rec.write({
                "kyc_status": "verified",
                "last_verification_date": fields.Date.today(),
            })
            rec.message_post(body=_("Guarantor KYC verified by %s.") % self.env.user.name)
    
    def action_reject(self):
        """Reject guarantor verification"""
        for rec in self:
            rec.write({
                "kyc_status": "rejected",
            })
            rec.message_post(body=_("Guarantor KYC rejected by %s.") % self.env.user.name)
    
    def action_blacklist(self):
        """Blacklist guarantor"""
        for rec in self:
            if not rec.blacklist_reason:
                raise UserError(_("Please provide a blacklist reason."))
            rec.write({
                "blacklisted": True,
            })
            body = (
                "<b>GUARANTOR BLACKLISTED</b><br/>"
                "Reason: %s"
            ) % rec.blacklist_reason
            rec.message_post(body=body)
    
    def action_unblacklist(self):
        """Remove guarantor from blacklist"""
        for rec in self:
            rec.write({
                "blacklisted": False,
                "blacklist_reason": False,
            })
            rec.message_post(body=_("Guarantor removed from blacklist by %s.") % self.env.user.name)
    
    def action_view_active_guarantees(self):
        """View active loan guarantees"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Active Guarantees - %s") % self.name,
            "res_model": "alba.loan.guarantor",
            "view_mode": "list,form",
            "domain": [
                ("guarantor_id", "=", self.id),
                ("status", "in", ["confirmed", "pledged"]),
            ],
        }
    
    # =========================================================================
    # Constraints
    # =========================================================================
    
    @api.constrains("phone")
    def _check_phone(self):
        for rec in self:
            if rec.phone and len(rec.phone) < 10:
                raise UserError(_("Phone number must be at least 10 digits."))
    
    _unique_id = models.Constraint(
        "unique(id_number)",
        "A guarantor with this ID number already exists."
    )


class AlbaLoanGuarantor(models.Model):
    """Junction table: Links Guarantors to Loan Applications"""
    
    _name = "alba.loan.guarantor"
    _description = "Loan Guarantor Assignment"
    _order = "create_date desc"
    _inherit = ["mail.thread"]
    
    # Links
    loan_application_id = fields.Many2one(
        "alba.loan.application",
        string="Loan Application",
        required=True,
        ondelete="cascade",
        index=True,
    )
    guarantor_id = fields.Many2one(
        "alba.guarantor",
        string="Guarantor",
        required=True,
        ondelete="restrict",
        index=True,
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Principal Borrower",
        related="loan_application_id.customer_id",
        store=True,
    )
    
    # Guarantee Details
    guarantee_amount = fields.Monetary(
        string="Guarantee Amount",
        currency_field="currency_id",
        required=True,
        help="Amount this guarantor is guaranteeing",
    )
    guarantee_type = fields.Selection([
        ("full", "Full Guarantee"),
        ("partial", "Partial Guarantee"),
        ("secured", "Secured with Collateral"),
    ], string="Guarantee Type", default="full", required=True)
    
    # Relationship to Borrower
    relationship = fields.Selection([
        ("spouse", "Spouse"),
        ("parent", "Parent"),
        ("child", "Child"),
        ("sibling", "Sibling"),
        ("relative", "Other Relative"),
        ("friend", "Friend"),
        ("colleague", "Colleague"),
        ("employer", "Employer"),
        ("other", "Other"),
    ], string="Relationship to Borrower", required=True)
    relationship_notes = fields.Char(string="Relationship Details")
    
    # Status
    status = fields.Selection([
        ("pending", "Pending"),
        ("confirmation_sent", "Confirmation Sent"),
        ("confirmed", "Confirmed"),
        ("rejected", "Rejected"),
        ("pledged", "Pledged"),
        ("released", "Released"),
        ("liability", "Under Liability"),
        ("recovered", "Recovered"),
    ], string="Status", default="pending", tracking=True)
    
    # Confirmation
    confirmation_code = fields.Char(string="Confirmation Code", readonly=True)
    confirmation_sent_date = fields.Datetime(string="Confirmation Sent")
    confirmed_date = fields.Datetime(string="Confirmed On")
    confirmed_method = fields.Selection([
        ("sms", "SMS Reply"),
        ("phone", "Phone Call"),
        ("in_person", "In Person"),
        ("email", "Email"),
    ], string="Confirmation Method")
    
    # Rejection
    rejected_date = fields.Datetime(string="Rejected On")
    rejection_reason = fields.Text(string="Rejection Reason")
    
    # Release
    release_date = fields.Date(string="Released On")
    release_reason = fields.Selection([
        ("loan_closed", "Loan Closed Normally"),
        ("loan_restructured", "Loan Restructured"),
        ("guarantee_replaced", "Replaced by Other Guarantor"),
        ("other", "Other"),
    ], string="Release Reason")
    
    # Currency
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="loan_application_id.currency_id",
        store=True,
    )
    
    # Django Sync
    django_loan_guarantor_id = fields.Integer(
        string="Django Loan Guarantor ID",
        index=True,
        help="ID from Django portal GuarantorVerification",
    )
    
    # Liability (if loan defaults)
    liability_amount = fields.Monetary(
        string="Liability Amount",
        currency_field="currency_id",
        help="Amount guarantor became liable for",
    )
    liability_date = fields.Date(string="Liability Date")
    recovery_amount = fields.Monetary(
        string="Amount Recovered",
        currency_field="currency_id",
    )
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.onchange("guarantor_id")
    def _onchange_guarantor(self):
        """Auto-fill details from guarantor record"""
        if self.guarantor_id:
            # Check if guarantor is blacklisted
            if self.guarantor_id.blacklisted:
                return {
                    "warning": {
                        "title": _("Blacklisted Guarantor"),
                        "message": _("This guarantor is blacklisted and cannot be used."),
                    }
                }
            
            # Check capacity
            if self.guarantor_id.available_capacity <= 0:
                return {
                    "warning": {
                        "title": _("No Available Capacity"),
                        "message": _("This guarantor has no remaining guarantee capacity."),
                    }
                }
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_send_confirmation(self):
        """Send SMS confirmation request to guarantor"""
        for rec in self:
            # Generate random 6-digit code
            import random
            code = str(random.randint(100000, 999999))
            
            rec.write({
                "confirmation_code": code,
                "confirmation_sent_date": fields.Datetime.now(),
                "status": "confirmation_sent",
            })
            
            
            body = (
                "<b>CONFIRMATION REQUEST SENT</b><br/>"
                "Code: %s<br/>"
                "Sent to: %s<br/>"
                "Guarantor: %s"
            ) % (code, rec.guarantor_id.phone, rec.guarantor_id.name)
            rec.message_post(body=body)
            
            # 🚀 PHASE 5: Omnichannel (Email)
            template = self.env.ref("alba_loans.email_template_guarantor_confirmation", raise_if_not_found=False)
            if template and rec.guarantor_id.email:
                template.send_mail(rec.id, force_send=False)
                rec.message_post(body=_("📧 Automated guarantor confirmation email sent to %s") % rec.guarantor_id.email)
    
    def action_confirm(self, method="phone"):
        """Confirm guarantor acceptance"""
        for rec in self:
            rec.write({
                "status": "confirmed",
                "confirmed_date": fields.Datetime.now(),
                "confirmed_method": method,
            })
            
            # Update guarantor KYC if pending
            if rec.guarantor_id.kyc_status == "pending":
                rec.guarantor_id.action_verify()
            
            body = (
                "<b>GUARANTOR CONFIRMED</b><br/>"
                "Confirmed by: %s<br/>"
                "Method: %s<br/>"
                "Amount: %s %s"
            ) % (rec.guarantor_id.name, method, rec.currency_id.symbol, rec.guarantee_amount)
            rec.message_post(body=body)
            
            # Update loan application
            rec.loan_application_id.message_post(body=_(
                "Guarantor %s confirmed for %s %s"
            ) % (rec.guarantor_id.name, rec.currency_id.symbol, rec.guarantee_amount))
    
    def action_reject(self, reason=""):
        """Reject guarantor"""
        for rec in self:
            rec.write({
                "status": "rejected",
                "rejected_date": fields.Datetime.now(),
                "rejection_reason": reason,
            })
            rec.message_post(body=_(
                "<b>GUARANTOR REJECTED</b><br/>"
                "Reason: %s"
            ) % (reason or "No reason provided"))
    
    def action_pledge(self):
        """Mark as pledged (loan disbursed with guarantee active)"""
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Guarantor must be confirmed before pledging."))
            
            rec.write({
                "status": "pledged",
            })
            rec.message_post(body=_("Guarantee pledged - loan disbursed."))
    
    def action_release(self, reason="loan_closed"):
        """Release guarantor from liability"""
        for rec in self:
            rec.write({
                "status": "released",
                "release_date": fields.Date.today(),
                "release_reason": reason,
            })
            rec.message_post(body=_(
                "<b>GUARANTOR RELEASED</b><br/>"
                "Reason: %s<br/>"
                "Date: %s"
            ) % (dict(self._fields["release_reason"].selection).get(reason), rec.release_date))
    
    def action_activate_liability(self, amount):
        """Activate guarantor liability when loan defaults"""
        for rec in self:
            rec.write({
                "status": "liability",
                "liability_amount": amount,
                "liability_date": fields.Date.today(),
            })
            rec.message_post(body=_(
                "<b>GUARANTOR LIABILITY ACTIVATED</b><br/>"
                "Liable for: %s %s<br/>"
                "Date: %s"
            ) % (rec.currency_id.symbol, amount, rec.liability_date))
    
    def action_record_recovery(self, amount):
        """Record recovery from guarantor"""
        for rec in self:
            new_total = (rec.recovery_amount or 0) + amount
            rec.write({
                "recovery_amount": new_total,
            })
            
            if new_total >= (rec.liability_amount or 0):
                rec.write({
                    "status": "recovered",
                })
                rec.message_post(body=Markup(_("<b>FULLY RECOVERED</b>")))
            else:
                remaining = (rec.liability_amount or 0) - new_total
                rec.message_post(body=_(
                    "Recovery: %s %s<br/>Remaining: %s %s"
                ) % (rec.currency_id.symbol, amount, rec.currency_id.symbol, remaining))


class AlbaGuarantorDocument(models.Model):
    """Documents attached to guarantor (ID, payslip, etc.)"""
    
    _name = "alba.guarantor.document"
    _description = "Guarantor Document"
    _order = "create_date desc"
    
    guarantor_id = fields.Many2one(
        "alba.guarantor",
        string="Guarantor",
        required=True,
        ondelete="cascade",
    )
    
    document_type = fields.Selection([
        ("id_front", "ID (Front)"),
        ("id_back", "ID (Back)"),
        ("photo", "Passport Photo"),
        ("payslip", "Payslip"),
        ("bank_statement", "Bank Statement"),
        ("employment_letter", "Employment Letter"),
        ("utility_bill", "Utility Bill"),
        ("other", "Other"),
    ], string="Document Type", required=True)
    
    name = fields.Char(string="Description", required=True)
    attachment = fields.Binary(string="File", required=True, attachment=True)
    file_name = fields.Char(string="File Name")
    
    verified = fields.Boolean(string="Verified", default=False)
    verified_by = fields.Many2one("res.users", string="Verified By")
    verified_date = fields.Date(string="Verified On")
    
    notes = fields.Text(string="Notes")
