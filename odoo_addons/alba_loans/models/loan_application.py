# -*- coding: utf-8 -*-
import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from markupsafe import Markup

_logger = logging.getLogger(__name__)


class AlbaLoanApplication(models.Model):
    _name = "alba.loan.application"
    _description = "Alba Capital Loan Application"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"
    _rec_name = "application_number"

    # ── Identification ────────────────────────────────────────────────────────
    application_number = fields.Char(
        string="Application Number",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _("New"),
    )
    django_application_id = fields.Integer(
        string="Django Application ID",
        index=True,
        copy=False,
        help="Primary key of the corresponding LoanApplication record in the Django portal.",
    )

    # ── Parties ───────────────────────────────────────────────────────────────
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="customer_id.partner_id",
        store=True,
        readonly=True,
    )
    # Employment details (related from customer)
    employer_id = fields.Many2one(
        "alba.employer",
        string="Employer",
        related="customer_id.employer_id",
        store=True,
        readonly=True,
    )
    monthly_income = fields.Monetary(
        string="Monthly Income",
        related="customer_id.monthly_income",
        store=True,
        readonly=True,
        currency_field="currency_id",
    )
    job_title = fields.Char(
        string="Job Title",
        related="customer_id.job_title",
        store=True,
        readonly=True,
    )
    loan_product_id = fields.Many2one(
        "alba.loan.product",
        string="Loan Product",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    product_category = fields.Selection(
        related="loan_product_id.category",
        string="Product Category",
        store=True,
    )

    # ── Loan Details ──────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    requested_amount = fields.Monetary(
        string="Requested Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    approved_amount = fields.Monetary(
        string="Approved Amount",
        currency_field="currency_id",
        tracking=True,
    )
    tenure_months = fields.Integer(
        string="Tenure (Months)",
        required=True,
        tracking=True,
    )
    repayment_frequency = fields.Selection(
        selection=[
            ("weekly", "Weekly"),
            ("fortnightly", "Fortnightly"),
            ("monthly", "Monthly"),
        ],
        string="Repayment Frequency",
        required=True,
        default="monthly",
        tracking=True,
    )
    purpose = fields.Text(
        string="Loan Purpose",
        required=True,
    )

    # ── Computed totals (indicative) ──────────────────────────────────────────
    estimated_total_interest = fields.Monetary(
        string="Estimated Total Interest",
        currency_field="currency_id",
        compute="_compute_estimated_totals",
        store=False,
    )
    estimated_total_fees = fields.Monetary(
        string="Estimated Total Fees",
        currency_field="currency_id",
        compute="_compute_estimated_totals",
        store=False,
    )
    estimated_total_repayable = fields.Monetary(
        string="Estimated Total Repayable",
        currency_field="currency_id",
        compute="_compute_estimated_totals",
        store=False,
    )

    # ── Workflow State ────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("under_review", "Under Review"),
            ("credit_analysis", "Credit Analysis"),
            ("pending_approval", "Pending Approval"),
            ("approved", "Approved"),
            ("employer_verification", "Employer Verification"),
            ("guarantor_confirmation", "Guarantor Confirmation"),
            ("disbursed", "Disbursed"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        index=True,
        copy=False,
    )

    # ── Stage Timestamps ──────────────────────────────────────────────────────
    submitted_date = fields.Datetime(string="Submitted On", readonly=True, copy=False)
    reviewed_date = fields.Datetime(
        string="Review Started On", readonly=True, copy=False
    )
    can_auto_disburse = fields.Boolean(
        compute="_compute_button_visibility", store=False
    )
    credit_analysis_date = fields.Datetime(
        string="Credit Analysis On", readonly=True, copy=False
    )
    pending_approval_date = fields.Datetime(
        string="Sent for Approval On", readonly=True, copy=False
    )
    approved_date = fields.Datetime(string="Approved On", readonly=True, copy=False)
    employer_verification_date = fields.Datetime(
        string="Employer Verification On", readonly=True, copy=False
    )
    guarantor_confirmation_date = fields.Datetime(
        string="Guarantor Confirmation On", readonly=True, copy=False
    )
    disbursed_date = fields.Datetime(string="Disbursed On", readonly=True, copy=False)
    rejected_date = fields.Datetime(string="Rejected On", readonly=True, copy=False)
    cancelled_date = fields.Datetime(string="Cancelled On", readonly=True, copy=False)

    # ── Personnel ─────────────────────────────────────────────────────────────
    reviewed_by = fields.Many2one(
        "res.users",
        string="Reviewed By",
        readonly=True,
        tracking=True,
        copy=False,
    )
    approved_by = fields.Many2one(
        "res.users",
        string="Approved By",
        readonly=True,
        tracking=True,
        copy=False,
    )
    disbursed_by = fields.Many2one(
        "res.users",
        string="Disbursed By",
        readonly=True,
        tracking=True,
        copy=False,
    )

    # ── Decision fields ───────────────────────────────────────────────────────
    rejection_reason = fields.Text(string="Rejection Reason", tracking=True)
    cancellation_reason = fields.Text(string="Cancellation Reason", tracking=True)
    internal_notes = fields.Text(string="Internal Notes")
    conditions_of_approval = fields.Text(
        string="Conditions of Approval",
        tracking=True,
        help="Any special conditions that must be met before disbursement.",
    )

    # ── Documents ─────────────────────────────────────────────────────────────
    loan_document_ids = fields.One2many(
        "alba.loan.document",
        "loan_application_id",
        string="Documents",
        copy=False,
    )
    all_partner_document_ids = fields.Many2many(
        "alba.loan.document",
        string="All Related Documents",
        compute="_compute_all_partner_documents",
        help="All documents belonging to the borrower and guarantors.",
    )

    # ── Linked Loan ───────────────────────────────────────────────────────────
    loan_id = fields.Many2one(
        "alba.loan",
        string="Disbursed Loan",
        readonly=True,
        copy=False,
    )
    loan_count = fields.Integer(
        string="Loans",
        compute="_compute_loan_count",
    )

    # ── UX Helpers ────────────────────────────────────────────────────────────
    application_progress = fields.Integer(
        string="Progress",
        compute="_compute_ux_helpers",
    )
    has_guarantor_block = fields.Boolean(
        string="Guarantor Block",
        compute="_compute_ux_helpers",
    )
    has_collateral_block = fields.Boolean(
        string="Collateral Block",
        compute="_compute_ux_helpers",
    )
    risk_score = fields.Float(
        string="Credit Risk Score",
        compute="_compute_risk_score",
        store=True,
    )

    # ── Guarantors ────────────────────────────────────────────────────────────
    loan_guarantor_ids = fields.One2many(
        "alba.loan.guarantor",
        "loan_application_id",
        string="Guarantors",
    )
    guarantor_count = fields.Integer(
        string="Guarantor Count",
        compute="_compute_guarantor_count",
    )
    confirmed_guarantor_count = fields.Integer(
        string="Confirmed Guarantors",
        compute="_compute_guarantor_count",
    )

    total_guaranteed_amount = fields.Monetary(
        string="Total Guaranteed",
        currency_field="currency_id",
        compute="_compute_guarantor_count",
    )

    # ── Collateral ────────────────────────────────────────────────────────────
    loan_collateral_ids = fields.One2many(
        "alba.loan.collateral",
        "loan_application_id",
        string="Collateral",
    )
    total_collateral_value = fields.Monetary(
        string="Total Collateral Value",
        currency_field="currency_id",
        compute="_compute_collateral_totals",
    )
    overall_ltv = fields.Float(
        string="Overall LTV (%)",
        compute="_compute_collateral_totals",
    )

    def _compute_collateral_totals(self):
        for rec in self:
            pledged = rec.loan_collateral_ids.filtered(lambda c: c.status == 'pledged')
            total_val = sum(pledged.mapped('collateral_value'))
            rec.total_collateral_value = total_val
            rec.overall_ltv = (rec.requested_amount / total_val * 100) if total_val > 0 else 0.0

    # ── Company ───────────────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    
    # ── Business Related (from Customer) ──────────────────────────────────────
    business_name = fields.Char(related="customer_id.business_name", readonly=True)
    business_registration_number = fields.Char(related="customer_id.business_registration_number", readonly=True)
    business_type = fields.Selection(related="customer_id.business_type", readonly=True)
    monthly_business_turnover = fields.Monetary(related="customer_id.monthly_business_turnover", readonly=True)

    # ── Product-requirement mirrors (drive form visibility — no double-fill) ───
    # These are read-only; set on the Loan Product, consumed here.
    product_requires_employer = fields.Boolean(
        related="loan_product_id.requires_employer", store=False,
        string="Product Requires Employer",
    )
    product_requires_guarantor = fields.Boolean(
        related="loan_product_id.requires_guarantor", store=False,
        string="Product Requires Guarantor",
    )
    product_min_guarantors = fields.Integer(
        related="loan_product_id.min_guarantors", store=False,
        string="Min Guarantors",
    )
    product_requires_collateral = fields.Boolean(
        related="loan_product_id.requires_collateral", store=False,
        string="Product Requires Collateral",
    )
    product_requires_business = fields.Boolean(
        related="loan_product_id.requires_business_info", store=False,
        string="Product Requires Business Info",
    )
    product_requires_payslip = fields.Boolean(
        related="loan_product_id.requires_payslip", store=False,
        string="Product Requires Payslip",
    )

    # ── Boolean helpers for button visibility ─────────────────────────────────
    can_submit = fields.Boolean(compute="_compute_button_visibility")
    can_review = fields.Boolean(compute="_compute_button_visibility")
    can_credit_analysis = fields.Boolean(compute="_compute_button_visibility")
    can_pending_approval = fields.Boolean(compute="_compute_button_visibility")
    can_approve = fields.Boolean(compute="_compute_button_visibility")
    can_employer_verify = fields.Boolean(compute="_compute_button_visibility")
    can_guarantor_confirm = fields.Boolean(compute="_compute_button_visibility")
    can_disburse = fields.Boolean(compute="_compute_button_visibility")
    can_reject = fields.Boolean(compute="_compute_button_visibility")
    can_cancel = fields.Boolean(compute="_compute_button_visibility")

    # =========================================================================
    # Valid state transitions
    # =========================================================================

    _VALID_TRANSITIONS = {
        "draft": ["submitted", "cancelled"],
        "submitted": ["under_review", "cancelled"],
        "under_review": ["credit_analysis", "rejected"],
        "credit_analysis": ["pending_approval", "rejected"],
        "pending_approval": ["approved", "rejected"],
        "approved": ["employer_verification", "disbursed"],
        "employer_verification": ["guarantor_confirmation", "disbursed", "rejected"],
        "guarantor_confirmation": ["disbursed", "rejected"],
        "disbursed": [],
        "rejected": [],
        "cancelled": [],
    }

    def can_transition_to(self, new_state):
        self.ensure_one()
        return new_state in self._VALID_TRANSITIONS.get(self.state, [])

    # =========================================================================
    # Computed methods
    # =========================================================================

    def _compute_ux_helpers(self):
        state_map = {
            "draft": 10, "submitted": 25, "under_review": 40,
            "credit_analysis": 55, "pending_approval": 70,
            "approved": 85, "employer_verification": 90,
            "guarantor_confirmation": 95, "disbursed": 100,
            "rejected": 100, "cancelled": 100
        }
        for rec in self:
            rec.application_progress = state_map.get(rec.state, 0)
            
            # Block indicators
            rec.has_guarantor_block = rec.product_requires_guarantor and rec.confirmed_guarantor_count < (rec.product_min_guarantors or 1)
            rec.has_collateral_block = rec.product_requires_collateral and not rec.loan_collateral_ids

    def _compute_risk_score(self):
        for rec in self:
            # Risk Score (fetch from last credit score if exists)
            last_score = self.env["alba.credit.score"].search([("application_id", "=", rec.id)], order="create_date desc", limit=1)
            rec.risk_score = last_score.final_score if last_score else 0.0

    @api.depends("loan_product_id", "requested_amount", "tenure_months")
    def _compute_estimated_totals(self):
        for rec in self:
            product = rec.loan_product_id
            amount = rec.requested_amount or 0.0
            months = rec.tenure_months or 0
            if not product or amount <= 0 or months <= 0:
                rec.estimated_total_interest = 0.0
                rec.estimated_total_fees = 0.0
                rec.estimated_total_repayable = 0.0
                continue
            if product.interest_method == "flat_rate":
                interest = product.calculate_flat_interest(amount, months)
            else:
                schedule = product.calculate_reducing_schedule(amount, months)
                interest = sum(row["interest_due"] for row in schedule)
            fees = product.calculate_total_fees(amount)
            rec.estimated_total_interest = interest
            rec.estimated_total_fees = fees
            rec.estimated_total_repayable = amount + interest + fees

    def _compute_loan_count(self):
        for rec in self:
            rec.loan_count = 1 if rec.loan_id else 0

    @api.depends("loan_guarantor_ids", "loan_guarantor_ids.status")
    def _compute_guarantor_count(self):
        for rec in self:
            rec.guarantor_count = len(rec.loan_guarantor_ids)
            rec.confirmed_guarantor_count = len(
                rec.loan_guarantor_ids.filtered(lambda g: g.status == "confirmed")
            )
            rec.total_guaranteed_amount = sum(
                rec.loan_guarantor_ids.filtered(lambda g: g.status == "confirmed").mapped("guarantee_amount")
            )

    def _compute_all_partner_documents(self):
        """Fetch all documents for the customer and all guarantors."""
        for rec in self:
            partner_ids = [rec.customer_id.partner_id.id]
            partner_ids += rec.loan_guarantor_ids.mapped("guarantor_id.partner_id.id")
            documents = self.env["alba.loan.document"].search([
                ("partner_id", "in", list(filter(None, partner_ids)))
            ])
            rec.all_partner_document_ids = documents

    @api.depends("state", "loan_product_id",
                 "loan_product_id.requires_employer",
                 "loan_product_id.requires_guarantor")
    def _compute_button_visibility(self):
        for rec in self:
            product = rec.loan_product_id
            needs_employer = product.requires_employer if product else False
            needs_guarantor = product.requires_guarantor if product else False

            rec.can_submit = rec.state == "draft"
            rec.can_review = rec.state == "submitted"
            rec.can_credit_analysis = rec.state == "under_review"
            rec.can_pending_approval = rec.state == "credit_analysis"
            rec.can_approve = rec.state == "pending_approval"
            # Employer verification only shown when product requires it
            rec.can_employer_verify = rec.state == "approved" and needs_employer
            # Guarantor confirmation only shown when product requires it
            rec.can_guarantor_confirm = (
                rec.state in ("approved", "employer_verification")
                and needs_guarantor
            )
            # Allow disbursement from approved, or after optional steps
            rec.can_disburse = rec.state in (
                "approved",
                "employer_verification",
                "guarantor_confirmation",
            )
            rec.can_auto_disburse = rec.can_disburse and (product.auto_disburse if product else False)
            rec.can_reject = rec.state in (
                "under_review",
                "credit_analysis",
                "pending_approval",
                "employer_verification",
                "guarantor_confirmation",
            )
            rec.can_cancel = rec.state in ("draft", "submitted")

    # =========================================================================
    # Workflow action methods
    # =========================================================================

    def _assert_transition(self, target):
        self.ensure_one()
        if not self.can_transition_to(target):
            raise UserError(
                _("Cannot move application from '%s' to '%s'.") % (self.state, target)
            )



    def action_submit(self):
        for rec in self:
            rec._assert_transition("submitted")
            rec.write(
                {
                    "state": "submitted",
                    "submitted_date": fields.Datetime.now(),
                }
            )
            # 🚀 PHASE 5: Omnichannel (Email - Submission)
            template = self.env.ref("alba_loans.email_template_application_submitted", raise_if_not_found=False)
            if template and rec.customer_id.email:
                template.send_mail(rec.id, force_send=False)
                rec.message_post(body=_("📧 Automated submission email sent to %s") % rec.customer_id.email)

            # Auto-Verify KYC on submission if still pending
            if rec.customer_id.kyc_status == "pending" and rec.customer_id.id_number:
                try:
                    rec.customer_id.action_auto_verify_kyc()
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Failed to auto-verify KYC: %s", str(e))
                    
            # Auto-calculate Credit Score on submission
            score = None
            try:
                score = self.env["alba.credit.score"].create({"application_id": rec.id})
                score.action_calculate()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Failed to auto-calculate credit score: %s", str(e))

            # Automated Employer Notification for Salary Advance / Employer-required products
            if rec.loan_product_id.requires_employer and rec.customer_id.employer_id:
                rec._send_automated_employer_email()

            # 🚀 PHASE 4: AUTO-DECISIONING ENGINE
            # Check if application meets all criteria for instant auto-approval
            if score and rec.customer_id.kyc_status == "verified":
                threshold = rec.loan_product_id.auto_approve_score_threshold or 85
                if score.total_score >= threshold:
                    # Check blockers
                    collateral_ok = not rec.loan_product_id.requires_collateral or bool(rec.loan_collateral_ids)
                    guarantors_ok = not rec.loan_product_id.requires_guarantor or (rec.guarantor_count >= (rec.loan_product_id.min_guarantors or 1))
                    
                    if collateral_ok and guarantors_ok:
                        rec.message_post(body=_(
                            "🤖 <b>Auto-Decisioning Engine</b><br/>"
                            "Credit score (%s) exceeds auto-approve threshold (%s).<br/>"
                            "KYC Verified. No blockers found.<br/>"
                            "➡️ Triggering Auto-Approval."
                        ) % (score.total_score, threshold))
                        
                        # We must bypass the UI transition checks, so we call action_under_review, etc.
                        rec.write({"state": "pending_approval"})
                        rec.action_approve()
        return True

    def _send_automated_employer_email(self):
        """Internal helper to send the employer verification email."""
        self.ensure_one()
        template = self.env.ref("alba_loans.email_template_employer_verification", raise_if_not_found=False)
        if template and self.customer_id.employer_id.email:
            template.send_mail(self.id, force_send=False)
            _logger.info("Automated employer verification email sent for %s", self.application_number)
        else:
            _logger.warning("Could not send automated employer email for %s: Template or Employer Email missing.", self.application_number)

    def write(self, vals):
        if 'state' in vals:
            for rec in self:
                if rec.state != vals['state']:
                    rec._log_professional_status_change(rec.state, vals['state'])
        return super(AlbaLoanApplication, self).write(vals)

    def _log_professional_status_change(self, old_state, new_state):
        """Post a professional, formatted message to the chatter on status change."""
        state_labels = dict(self._fields['state'].selection)
        old_label = state_labels.get(old_state, old_state)
        new_label = state_labels.get(new_state, new_state)
        
        icon = "📝"
        if new_state == "submitted": icon = "📥"
        if new_state == "under_review": icon = "🔍"
        if new_state == "approved": icon = "✅"
        if new_state == "disbursed": icon = "💸"
        if new_state == "rejected": icon = "❌"
        
        body = (
            "<div class='o_alba_status_change'>"
            "<strong>%s Application Status Changed</strong><br/>"
            "From: <span class='badge badge-secondary' style='color: #666;'>%s</span> "
            "To: <span class='badge badge-primary' style='background-color: #004a99; color: white; padding: 2px 6px; border-radius: 4px;'>%s</span><br/>"
            "Changed by: %s"
            "</div>"
        ) % (icon, old_label.upper(), new_label.upper(), self.env.user.name)
        self.message_post(body=body)

    def action_under_review(self):
        for rec in self:
            rec._assert_transition("under_review")
            rec.write(
                {
                    "state": "under_review",
                    "reviewed_date": fields.Datetime.now(),
                    "reviewed_by": self.env.uid,
                }
            )
        return True

    def action_credit_analysis(self):
        for rec in self:
            rec._assert_transition("credit_analysis")
            rec.write(
                {
                    "state": "credit_analysis",
                    "credit_analysis_date": fields.Datetime.now(),
                }
            )
        return True

    def action_pending_approval(self):
        for rec in self:
            rec._assert_transition("pending_approval")
            rec.write(
                {
                    "state": "pending_approval",
                    "pending_approval_date": fields.Datetime.now(),
                }
            )
        return True

    def action_approve(self):
        for rec in self:
            rec._assert_transition("approved")
            
            # Enforce collateral if required by product
            if rec.loan_product_id.requires_collateral and not rec.loan_collateral_ids:
                raise UserError(_("This product requires collateral. Please add collateral details before approving."))
            
            # Enforce minimum guarantors if required
            if rec.loan_product_id.requires_guarantor:
                min_g = rec.loan_product_id.min_guarantors or 1
                if rec.guarantor_count < min_g:
                    raise UserError(_("This product requires at least %d guarantor(s). Current count: %d") % (min_g, rec.guarantor_count))

            if not rec.approved_amount:
                rec.approved_amount = rec.requested_amount
            rec.write(
                {
                    "state": "approved",
                    "approved_date": fields.Datetime.now(),
                    "approved_by": self.env.uid,
                }
            )
            
            # Auto-trigger next steps
            # 🚀 PHASE 5: Omnichannel (Email - Approval)
            template = self.env.ref("alba_loans.email_template_application_approved", raise_if_not_found=False)
            if template and rec.customer_id.email:
                template.send_mail(rec.id, force_send=False)
                rec.message_post(body=_("📧 Automated approval email sent to %s") % rec.customer_id.email)

            if rec.loan_product_id.requires_guarantor:
                rec.action_guarantor_confirmation()

            elif rec.loan_product_id.requires_employer:
                rec.action_employer_verification()
            elif rec.loan_product_id.auto_disburse:
                rec.action_auto_disburse()
                
        return True

    def action_auto_disburse(self):
        """
        Futuristic Automation: Instantly disburse funds via M-Pesa B2C API.
        Called automatically by the workflow if the product is configured for auto-disburse.
        """
        for rec in self:
            if rec.state not in ("approved", "employer_verification", "guarantor_confirmation"):
                raise UserError(_("Cannot auto-disburse application in state %s.") % rec.state)
                
            config = self.env["alba.mpesa.config"].search([("is_active", "=", True), ("company_id", "=", rec.company_id.id)], limit=1)
            if not config:
                raise UserError(_("No active M-Pesa configuration found for company %s.") % rec.company_id.name)
                
            # Fire B2C API
            amount = rec.approved_amount or rec.requested_amount
            phone = rec.customer_id.mpesa_number or rec.customer_id.partner_id.mobile or rec.customer_id.partner_id.phone
            if not phone:
                raise UserError(_("Customer has no phone number configured for M-Pesa."))
                
            response = config.b2c_payment(
                phone_number=phone,
                amount=amount,
                occasion=f"Loan {rec.application_number}",
                remarks="Loan Disbursement",
                command_id="BusinessPayment"
            )
            
            # Create pending transaction
            self.env["alba.mpesa.transaction"].create({
                "transaction_type": "b2c",
                "status": "pending",
                "amount": amount,
                "phone_number": phone,
                "conversation_id": response.get("ConversationID"),
                "originator_conversation_id": response.get("OriginatorConversationID"),
                "account_reference": rec.application_number,
                "description": f"Loan Disbursement to {rec.customer_id.name}",
                "config_id": config.id,
                "company_id": rec.company_id.id,
                # We link it to the application by saving the app ID in a new field or using account_reference
            })
            
            rec.message_post(body=Markup(_("🚀 <b>Zero-Touch Disbursement Initiated</b><br/>M-Pesa B2C Request sent. Awaiting Daraja confirmation.")))

    def action_employer_verification(self):
        for rec in self:
            rec._assert_transition("employer_verification")
            rec.write(
                {
                    "state": "employer_verification",
                    "employer_verification_date": fields.Datetime.now(),
                }
            )
        return True

    def action_guarantor_confirmation(self):
        for rec in self:
            rec._assert_transition("guarantor_confirmation")
            rec.write(
                {
                    "state": "guarantor_confirmation",
                    "guarantor_confirmation_date": fields.Datetime.now(),
                }
            )
            # Automate: Send confirmation request to all guarantors who haven't received it
            pending_g = rec.loan_guarantor_ids.filtered(lambda g: g.status == 'pending')
            if pending_g:
                pending_g.action_send_confirmation()
                rec.message_post(body=_("Automated confirmation requests sent to %d guarantor(s).") % len(pending_g))
        return True

    def action_reject(self):
        for rec in self:
            rec._assert_transition("rejected")
            if not rec.rejection_reason:
                raise UserError(
                    _("Please provide a rejection reason before rejecting.")
                )
            rec.write(
                {
                    "state": "rejected",
                    "rejected_date": fields.Datetime.now(),
                }
            )
            # 🚀 PHASE 5: Omnichannel (Email - Rejection)
            template = self.env.ref("alba_loans.email_template_application_rejected", raise_if_not_found=False)
            if template and rec.customer_id.email:
                template.send_mail(rec.id, force_send=False)
                rec.message_post(body=_("📧 Automated rejection email sent to %s") % rec.customer_id.email)

        return True

    def action_cancel(self):
        for rec in self:
            rec._assert_transition("cancelled")
            rec.write(
                {
                    "state": "cancelled",
                    "cancelled_date": fields.Datetime.now(),
                }
            )
        return True

    def action_open_disburse_wizard(self):
        """Open the disbursement wizard."""
        self.ensure_one()
        if self.state not in (
            "approved",
            "employer_verification",
            "guarantor_confirmation",
        ):
            raise UserError(_("Only approved applications can be disbursed."))

        # -- ENFORCEMENT CHECKS --
        # 1. Guarantors
        if self.loan_product_id.requires_guarantor:
            min_g = self.loan_product_id.min_guarantors or 1
            if self.confirmed_guarantor_count < min_g:
                raise UserError(_(
                    "Disbursement Blocked: %d confirmed guarantors required, but only %d are confirmed."
                ) % (min_g, self.confirmed_guarantor_count))

        # 2. Collateral
        if self.loan_product_id.requires_collateral:
            if not self.loan_collateral_ids:
                raise UserError(_("Disbursement Blocked: This product requires collateral to be pledged."))
            
            unpledged = self.loan_collateral_ids.filtered(lambda c: c.status != 'pledged')
            if unpledged:
                # Attempt to auto-pledge if they are available
                for col in unpledged:
                    if col.collateral_id.status == 'available':
                        col.collateral_id.action_pledge()
                    else:
                        raise UserError(_(
                            "Disbursement Blocked: Collateral '%s' is not available or already pledged elsewhere."
                        ) % col.collateral_id.name)

        # 3. Employer (if applicable)
        # Note: Usually employer verification is a "best effort" or soft check, 
        # but we can enforce it if the state hasn't been bypassed.

        # Ensure loan product has all accounting accounts configured
        self.loan_product_id._ensure_accounting_defaults()

        return {
            "type": "ir.actions.act_window",
            "name": _("Disburse Loan"),
            "res_model": "alba.loan.disburse.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_application_id": self.id,
                "default_approved_amount": self.approved_amount
                or self.requested_amount,
            },
        }

    def action_view_loan(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loan"),
            "res_model": "alba.loan",
            "view_mode": "form",
            "res_id": self.loan_id.id,
        }

    def action_view_guarantors(self):
        """View guarantors for this application"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Guarantors — %s") % self.application_number,
            "res_model": "alba.loan.guarantor",
            "view_mode": "list,form",
            "domain": [("loan_application_id", "=", self.id)],
            "context": {"default_loan_application_id": self.id},
        }

    def action_add_guarantor(self):
        """Add a guarantor to this application"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Add Guarantor"),
            "res_model": "alba.loan.guarantor",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_loan_application_id": self.id,
                "default_guarantee_amount": self.approved_amount or self.requested_amount,
            },
        }

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains("requested_amount", "loan_product_id")
    def _check_amount_within_product_limits(self):
        for rec in self:
            if not rec.loan_product_id:
                continue
            product = rec.loan_product_id
            if rec.requested_amount < product.min_amount:
                raise ValidationError(
                    _(
                        "Requested amount %s is below the minimum of %s for product '%s'."
                    )
                    % (rec.requested_amount, product.min_amount, product.name)
                )
            if rec.requested_amount > product.max_amount:
                raise ValidationError(
                    _("Requested amount %s exceeds the maximum of %s for product '%s'.")
                    % (rec.requested_amount, product.max_amount, product.name)
                )

    @api.constrains("tenure_months", "loan_product_id")
    def _check_tenure_within_product_limits(self):
        for rec in self:
            if not rec.loan_product_id:
                continue
            product = rec.loan_product_id
            if rec.tenure_months < product.min_tenure_months:
                raise ValidationError(
                    _(
                        "Tenure %s months is below the minimum of %s months for product '%s'."
                    )
                    % (rec.tenure_months, product.min_tenure_months, product.name)
                )
            if rec.tenure_months > product.max_tenure_months:
                raise ValidationError(
                    _(
                        "Tenure %s months exceeds the maximum of %s months for product '%s'."
                    )
                    % (rec.tenure_months, product.max_tenure_months, product.name)
                )

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("application_number", _("New")) == _("New"):
                vals["application_number"] = self.env["ir.sequence"].next_by_code(
                    "alba.loan.application.seq"
                ) or _("New")
        return super().create(vals_list)

    def name_get(self):
        return [
            (rec.id, "%s — %s" % (rec.application_number, rec.customer_id.display_name))
            for rec in self
        ]
