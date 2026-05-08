# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class AlbaInvestorPro(models.Model):
    _inherit = "alba.investor"
    _rec_name = "display_name"
    _order = "create_date desc"

    # ── Partner link ──────────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )
    display_name = fields.Char(
        string="Name",
        compute="_compute_display_name",
        store=True,
        index=True,
    )

    # ── Investor Number ───────────────────────────────────────────────────────
    investor_number = fields.Char(
        string="Investor Number",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _("New"),
    )

    # ── Django sync ───────────────────────────────────────────────────────────
    django_investor_id = fields.Integer(
        string="Django Investor ID",
        index=True,
        copy=False,
        help="Primary key of the corresponding Investor record in the Django portal.",
    )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    # ── Identity (Related to Partner) ────────────────────────────────────────
    id_number = fields.Char(related="partner_id.id_number", store=True, readonly=False)
    id_type = fields.Selection(related="partner_id.id_type", store=True, readonly=False)
    date_of_birth = fields.Date(related="partner_id.date_of_birth", store=True, readonly=False)
    age = fields.Integer(string="Age", compute="_compute_age", store=False)
    gender = fields.Selection(related="partner_id.gender", store=True, readonly=False)
    nationality = fields.Char(string="Nationality", default="Kenyan")

    # ── Location ─────────────────────────────────────────────────────────────
    county_id = fields.Many2one(
        "alba.county",
        string="County",
        tracking=True,
        index=True,
    )
    sub_county_id = fields.Many2one(
        "alba.sub.county",
        string="Sub-County",
        domain="[('county_id', '=', county_id)]",
        tracking=True,
        index=True,
    )
    ward_id = fields.Many2one(
        "alba.ward",
        string="Ward",
        domain="[('sub_county_id', '=', sub_county_id)]",
        tracking=True,
        index=True,
    )
    location_display = fields.Char(
        string="Location",
        compute="_compute_location_display",
        store=True,
    )

    # ── Tags ─────────────────────────────────────────────────────────────────
    tag_ids = fields.Many2many(
        "alba.customer.tag",
        "alba_investor_tag_rel",
        "investor_id",
        "tag_id",
        string="Tags",
        tracking=True,
    )

    # ── KYC ───────────────────────────────────────────────────────────────────
    kyc_status = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("partial", "Partially Complete"),
            ("complete", "Complete — Awaiting Verification"),
            ("verified", "Verified"),
            ("rejected", "Rejected"),
        ],
        string="KYC Status",
        default="pending",
        tracking=True,
        index=True,
    )
    kyc_verified_by = fields.Many2one(
        "res.users",
        string="KYC Verified By",
        readonly=True,
        tracking=True,
    )
    kyc_verified_date = fields.Datetime(
        string="KYC Verified On",
        readonly=True,
        tracking=True,
    )
    document_ids = fields.One2many(
        "alba.investor.document",
        "investor_id",
        string="Documents",
    )
    document_count = fields.Integer(
        string="Document Count",
        compute="_compute_document_count",
    )

    state = fields.Selection(
        selection_add=[
            ("blacklisted", "Blacklisted"),
        ],
        ondelete={'blacklisted': 'set default'}
    )

    # ── Banking / Payout ──────────────────────────────────────────────────────
    bank_name = fields.Char(string="Bank Name")
    bank_account_number = fields.Char(string="Bank Account Number")
    bank_branch = fields.Char(string="Bank Branch")
    mpesa_number = fields.Char(
        string="M-Pesa Number",
        help="Must start with 254 e.g. 254712345678",
    )
    preferred_payment_method = fields.Selection(
        selection=[
            ("bank_transfer", "Bank Transfer"),
            ("mpesa", "M-Pesa"),
            ("cheque", "Cheque"),
        ],
        string="Preferred Payout Method",
        default="bank_transfer",
        tracking=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    investment_ids = fields.One2many(
        "alba.investment",
        "investor_id",
        string="Investments",
    )

    # ── Computed Portfolio ────────────────────────────────────────────────────
    active_investment_count = fields.Integer(
        string="Active Investments",
        compute="_compute_portfolio",
        store=True,
    )
    total_invested = fields.Monetary(
        string="Total Principal Invested",
        compute="_compute_portfolio",
        store=True,
        currency_field="currency_id",
    )
    total_interest_earned = fields.Monetary(
        string="Total Interest Accrued",
        compute="_compute_portfolio",
        store=True,
        currency_field="currency_id",
    )
    current_portfolio_value = fields.Monetary(
        string="Current Portfolio Value",
        compute="_compute_portfolio",
        store=True,
        currency_field="currency_id",
        help="Sum of all active investments' current values (principal + accrued interest).",
    )
    total_interest_paid_out = fields.Monetary(
        string="Total Interest Paid Out",
        compute="_compute_portfolio",
        store=True,
        currency_field="currency_id",
    )

    # ── Currency ──────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        string="Preferred Currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
        tracking=True,
        help="Currency the investor typically uses for investments.",
    )

    # ── UX Helpers ────────────────────────────────────────────────────────────
    is_high_value = fields.Boolean(
        string="High Value Investor",
        compute="_compute_ux_helpers",
        store=True,
        help="Investors with portfolio > 1,000,000",
    )
    kyc_progress = fields.Integer(
        string="KYC Completion %",
        compute="_compute_kyc_progress",
    )
    has_active_investments = fields.Boolean(
        string="Has Active Investments",
        compute="_compute_ux_helpers",
        store=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string="Internal Notes")
    active = fields.Boolean(default=True)

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _investor_number_unique = models.Constraint(
        "UNIQUE(investor_number)",
        "An investor with this investor number already exists.",
    )
    _unique_id_number = models.Constraint(
        "UNIQUE(id_number)",
        "An investor with this ID / Passport number already exists.",
    )
    _unique_django_investor_id = models.Constraint(
        "UNIQUE(django_investor_id)",
        "An investor with this Django Investor ID already exists.",
    )

    # =========================================================================
    # Computed methods
    # =========================================================================

    def action_auto_verify_kyc(self):
        """🚀 PHASE 5: Automated KYC for Investors"""
        for rec in self:
            if not rec.id_number:
                raise ValidationError(_("Please provide an ID number before verifying KYC."))
            
            # Use the KYC Provider architecture from alba_loans
            provider = self.env["alba.kyc.provider"].search([("is_active", "=", True)], limit=1)
            if not provider:
                # If no provider configured, fall back to manual verification or raise warning
                rec.message_post(body=_("⚠️ No active KYC Provider found. Please configure one in Settings."))
                return False
                
            rec.message_post(body=_("🔍 Initiating automated KYC verification via %s...") % provider.name)
            
            # Call the provider
            result = provider.verify_identity(rec.id_number, rec.partner_id.name)
            
            # Log full result in chatter
            log_body = (
                "<div style='border: 1px solid #dee2e6; padding: 10px; border-radius: 5px; background-color: #f8f9fa;'>"
                "<b>KYC API Response (%s)</b><br/>"
                "Status: <span class='badge bg-%s'>%s</span><br/>"
                "Confidence: %s%%<br/>"
                "Reference: %s<br/>"
                "Notes: %s"
                "</div>"
            ) % (
                provider.name,
                "success" if result['status'] == 'verified' else "warning" if result['status'] == 'manual_review' else "danger",
                result['status'].upper(),
                result['confidence_score'],
                result['provider_reference'],
                result['notes']
            )
            rec.message_post(body=log_body)
            
            # Update Investor Status
            if result['status'] == 'verified':
                rec.write({
                    'kyc_status': 'verified',
                    'kyc_verified_by': self.env.uid,
                    'kyc_verified_date': fields.Datetime.now(),
                })
            elif result['status'] == 'rejected':
                rec.write({'kyc_status': 'rejected'})
            
        return True

    @api.depends("partner_id", "partner_id.name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.partner_id.name or _("New Investor")

    @api.depends("county_id", "sub_county_id", "ward_id")
    def _compute_location_display(self):
        for rec in self:
            parts = []
            if rec.ward_id:
                parts.append(rec.ward_id.name)
            if rec.sub_county_id:
                parts.append(rec.sub_county_id.name)
            if rec.county_id:
                parts.append(rec.county_id.name)
            rec.location_display = ", ".join(parts) if parts else ""

    @api.depends("date_of_birth")
    def _compute_age(self):
        today = fields.Date.today()
        for rec in self:
            if rec.date_of_birth:
                rec.age = int((today - rec.date_of_birth).days / 365.25)
            else:
                rec.age = 0

    @api.depends(
        "investment_ids",
        "investment_ids.state",
        "investment_ids.principal_amount",
        "investment_ids.current_value",
        "investment_ids.total_interest_accrued",
        "investment_ids.total_interest_paid",
        "kyc_status",
    )
    def _compute_portfolio(self):
        for rec in self:
            active = rec.investment_ids.filtered(lambda i: i.state == "active")
            all_inv = rec.investment_ids

            rec.active_investment_count = len(active)
            rec.total_invested = sum(active.mapped("principal_amount"))
            rec.total_interest_earned = sum(all_inv.mapped("total_interest_accrued"))
            rec.current_portfolio_value = sum(active.mapped("current_value"))
            rec.total_interest_paid_out = sum(all_inv.mapped("total_interest_paid"))

    @api.depends("current_portfolio_value", "kyc_status", "active_investment_count")
    def _compute_ux_helpers(self):
        for rec in self:
            rec.is_high_value = rec.current_portfolio_value >= 1000000
            rec.has_active_investments = rec.active_investment_count > 0

    def _compute_kyc_progress(self):
        for rec in self:
            # Base progress from selection
            progress = 0
            if rec.kyc_status == "verified":
                progress = 100
            elif rec.kyc_status == "complete":
                progress = 80
            elif rec.kyc_status == "partial":
                progress = 50
            elif rec.kyc_status == "pending":
                progress = 10
            
            # Boost progress if documents are uploaded
            if rec.document_ids:
                verified_docs = rec.document_ids.filtered(lambda d: d.status == 'verified')
                if verified_docs:
                    progress = max(progress, 90 if rec.kyc_status != 'verified' else 100)
            
            rec.kyc_progress = progress

    @api.depends("document_ids")
    def _compute_document_count(self):
        for rec in self:
            rec.document_count = len(rec.document_ids)

    # =========================================================================
    # Constraint methods
    # =========================================================================

    @api.constrains("mpesa_number")
    def _check_mpesa_number(self):
        for rec in self:
            if rec.mpesa_number and not rec.mpesa_number.startswith("254"):
                raise ValidationError(
                    _("M-Pesa number must start with 254 (e.g. 254712345678).")
                )

    # =========================================================================
    # Business actions
    # =========================================================================

    def action_verify_kyc(self):
        self.ensure_one()
        self.write(
            {
                "kyc_status": "verified",
                "kyc_verified_by": self.env.uid,
                "kyc_verified_date": fields.Datetime.now(),
            }
        )
        self.message_post(
            body=_("KYC status marked as <b>Verified</b> by %s.") % self.env.user.name
        )
        # Automation: Send Welcome Notification
        template = self.env.ref("alba_investors.email_template_investor_welcome", raise_if_not_found=False)
        if template and self.partner_id.email:
            template.send_mail(self.id, force_send=False)

    def action_reject_kyc(self):
        self.ensure_one()
        self.write({"kyc_status": "rejected"})
        self.message_post(
            body=_("KYC status marked as <b>Rejected</b> by %s.") % self.env.user.name
        )

    def action_suspend(self):
        self.ensure_one()
        self.write({"state": "suspended"})
        self.message_post(body=_("Investor account <b>suspended</b>."))

    def action_activate(self):
        self.ensure_one()
        self.write({"state": "active"})
        self.message_post(body=_("Investor account <b>reactivated</b>."))

    def action_blacklist(self):
        self.ensure_one()
        self.write({"state": "blacklisted"})
        self.message_post(body=_("Investor account has been <b>blacklisted</b>."))

    def action_view_investments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Investments — %s") % self.display_name,
            "res_model": "alba.investment",
            "view_mode": "list,kanban,form",
            "domain": [("investor_id", "=", self.id)],
            "context": {"default_investor_id": self.id},
        }

    def action_view_statements(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Statements — %s") % self.display_name,
            "res_model": "alba.investment.statement",
            "view_mode": "list,form",
            "domain": [("investor_id", "=", self.id)],
            "context": {"default_investor_id": self.id},
        }

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("investor_number", _("New")) == _("New"):
                vals["investor_number"] = seq.next_by_code("alba.investor.seq") or _(
                    "New"
                )
        return super().create(vals_list)

    def name_get(self):
        return [
            (
                rec.id,
                "[%s] %s"
                % (rec.investor_number, rec.partner_id.name or _("New Investor")),
            )
            for rec in self
        ]


class AlbaInvestorDocument(models.Model):
    _name = "alba.investor.document"
    _description = "Investor Document"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    investor_id = fields.Many2one(
        "alba.investor",
        string="Investor",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(string="Document Name", required=True)
    document_type = fields.Selection(
        [
            ("id_card", "ID Card / Passport"),
            ("agreement", "Investment Agreement"),
            ("nda", "NDA"),
            ("tax_certificate", "Tax Certificate (KRA PIN)"),
            ("proof_of_funds", "Proof of Funds"),
            ("other", "Other"),
        ],
        string="Document Type",
        required=True,
        tracking=True,
    )
    attachment = fields.Binary(string="File Content", required=True)
    filename = fields.Char(string="Filename")
    
    status = fields.Selection(
        [
            ("pending", "Pending Verification"),
            ("verified", "Verified"),
            ("rejected", "Rejected"),
            ("expired", "Expired"),
        ],
        string="Verification Status",
        default="pending",
        tracking=True,
    )
    expiry_date = fields.Date(string="Expiry Date")
    verified_by = fields.Many2one("res.users", string="Verified By", readonly=True)
    verified_date = fields.Datetime(string="Verified On", readonly=True)
    notes = fields.Text(string="Notes")

    def action_verify(self):
        self.write({
            "status": "verified",
            "verified_by": self.env.uid,
            "verified_date": fields.Datetime.now(),
        })
        # If this is the first verified doc, maybe update investor KYC
        if self.investor_id.kyc_status == 'pending':
            self.investor_id.write({'kyc_status': 'partial'})
        
        self.message_post(body=_("Document verified successfully."))

    @api.model
    def _check_company(self, company_id):
        """Ensure company consistency for multi-company setup"""
        if company_id:
            self.company_id = company_id
    
    def action_reject(self):
        self.write({"status": "rejected"})
        self.message_post(body=_("Document rejected."))
