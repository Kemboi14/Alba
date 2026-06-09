# -*- coding: utf-8 -*-
import base64
import mimetypes
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .investment_product import INVESTOR_DOCUMENT_TYPES

_logger = logging.getLogger(__name__)


class AlbaInvestorPro(models.Model):
    _inherit = "alba.investor"
    # IMPORT-EXPORT FIX: _rec_name set to investor_number (unique stored Char) so Odoo can
    # resolve Many2one references during import. display_name is kept for UI display.
    _rec_name = "investor_number"
    _order = "create_date desc"

    investor_name = fields.Char(
        string="Investor Full Name",  # IMPORT-FIX: must NOT be 'Display Name' — Odoo's built-in
        compute="_compute_investor_name",
        store=True,
        index=True,
    )

    # ── Investor Number ───────────────────────────────────────────────────────
    investor_number = fields.Char(
        string="Investor Number",
        readonly=False,  # IMPORT-FIX: must be writable so the CSV importer can set INV-XXXX
        copy=True,
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
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        required=True,
        ondelete="restrict",
        index=True,
    )
    image_1920 = fields.Image(related="partner_id.image_1920", string="Image", readonly=False)
    avatar_128 = fields.Image(related="partner_id.avatar_128", string="Avatar", readonly=False)
    id_number = fields.Char(
        string="ID / Passport Number",
        store=True,
        readonly=False,
        required=True,
    )  # IMPORT-FIX: plain Char with correct header matching
    id_type = fields.Selection(related="partner_id.id_type", store=True, readonly=False)
    date_of_birth = fields.Date(related="partner_id.date_of_birth", store=True, readonly=False, required=True)
    age = fields.Integer(string="Age", compute="_compute_age", store=False)
    gender = fields.Selection(related="partner_id.gender", store=True, readonly=False)
    nationality = fields.Char(string="Nationality", default="Kenyan", required=True)
    payment_details = fields.Text(
        string="Payment Details",
        required=True,
        help="Specify bank account details or mobile money info for payouts."
    )

    @api.constrains('image_1920')
    def _check_image_file_size(self):
        max_bytes = 50 * 1024 * 1024
        for rec in self:
            image_data = rec.image_1920
            if image_data:
                try:
                    if len(base64.b64decode(image_data)) > max_bytes:
                        raise ValidationError(
                            _("Investor image cannot exceed 50 MB. Please upload a smaller file.")
                        )
                except (TypeError, ValueError):
                    raise ValidationError(
                        _("Unable to validate investor image size. Please re-upload the file.")
                    )

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
        inverse="_inverse_noop",
        store=True,
    )
    total_invested = fields.Monetary(
        string="Total Principal Invested",
        compute="_compute_portfolio",
        inverse="_inverse_noop",
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
        inverse="_inverse_noop",
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
        help="Currency investor typically uses for investments.",
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

    def _inverse_noop(self):
        # IMPORT-FIX: no-op inverse to satisfy Odoo's import requirements
        pass

    @api.depends("investor_number", "partner_id", "partner_id.name")
    def _compute_investor_name(self):
        for rec in self:
            name = rec.partner_id.name or _("New Investor")
            if rec.investor_number and rec.investor_number != _("New"):
                rec.investor_name = "[%s] %s" % (rec.investor_number, name)
            else:
                rec.investor_name = name

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike',
                     limit=100, order=None):
        domain = list(domain or [])
        if name:
            domain = ['|',
                ('investor_number', '=', name),
                ('name', operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)

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
        "currency_id",
    )
    def _compute_portfolio(self):
        for rec in self:
            active = rec.investment_ids.filtered(lambda i: i.state == "active")
            all_inv = rec.investment_ids

            rec.active_investment_count = len(active)
            
            # Group investments by currency for safe multi-currency portfolio totals
            active_by_currency = {}
            all_by_currency = {}
            
            for inv in active:
                currency_id = inv.currency_id.id
                if currency_id not in active_by_currency:
                    active_by_currency[currency_id] = []
                active_by_currency[currency_id].append(inv)
                
            for inv in all_inv:
                currency_id = inv.currency_id.id
                if currency_id not in all_by_currency:
                    all_by_currency[currency_id] = []
                all_by_currency[currency_id].append(inv)

            # Convert all amounts to investor's preferred currency for accurate totals
            investor_currency = rec.currency_id or self.env.company.currency_id
            
            total_invested = 0.0
            total_interest_earned = 0.0
            current_portfolio_value = 0.0
            total_interest_paid_out = 0.0
            
            for currency_id, investments in active_by_currency.items():
                currency_total = sum(inv.principal_amount for inv in investments)
                if currency_id != investor_currency.id:
                    # Convert to investor's currency using current rates
                    from_currency = self.env['res.currency'].browse(currency_id)
                    converted_total = from_currency._convert(
                        currency_total, 
                        investor_currency, 
                        self.env.company or self.env['res.company']._company_default_get()
                    )
                    total_invested += converted_total
                else:
                    total_invested += currency_total
            
            for currency_id, investments in all_by_currency.items():
                interest_total = sum(inv.total_interest_accrued for inv in investments)
                if currency_id != investor_currency.id:
                    from_currency = self.env['res.currency'].browse(currency_id)
                    converted_total = from_currency._convert(
                        interest_total,
                        investor_currency,
                        self.env.company or self.env['res.company']._company_default_get()
                    )
                    total_interest_earned += converted_total
                else:
                    total_interest_earned += interest_total
                    
                paid_total = sum(inv.total_interest_paid for inv in investments)
                if currency_id != investor_currency.id:
                    from_currency = self.env['res.currency'].browse(currency_id)
                    converted_total = from_currency._convert(
                        paid_total,
                        investor_currency,
                        self.env.company or self.env['res.company']._company_default_get()
                    )
                    total_interest_paid_out += converted_total
                else:
                    total_interest_paid_out += paid_total
            
            # Calculate current portfolio value with currency conversion
            for currency_id, investments in active_by_currency.items():
                value_total = sum(inv.current_value for inv in investments)
                if currency_id != investor_currency.id:
                    from_currency = self.env['res.currency'].browse(currency_id)
                    converted_total = from_currency._convert(
                        value_total,
                        investor_currency,
                        self.env.company or self.env['res.company']._company_default_get()
                    )
                    current_portfolio_value += converted_total
                else:
                    current_portfolio_value += value_total
            
            rec.total_invested = total_invested
            rec.total_interest_earned = total_interest_earned
            rec.current_portfolio_value = current_portfolio_value
            rec.total_interest_paid_out = total_interest_paid_out

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
        if self.investment_ids.filtered(lambda inv: inv.state == "active"):
            raise UserError(_("You cannot suspend an investor with active investments."))
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
            "name": _("Investments — %s") % self.investor_name,
            "res_model": "alba.investment",
            "view_mode": "list,kanban,form",
            "domain": [("investor_id", "=", self.id)],
            "context": {"default_investor_id": self.id},
        }

    def action_view_statements(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Statements — %s") % self.investor_name,
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

    def _get_default_list_export_fields(self):
        fields = super()._get_default_list_export_fields()
        return [f for f in fields 
                if f not in ('display_name', '__last_update')]

    def name_get(self):
        result = []
        for rec in self:
            # Use investor_number as the display value so export and
            # import use the same identifier
            label = rec.investor_number or rec.name or str(rec.id)
            result.append((rec.id, label))
        return result

    def write(self, vals):
        if vals.get("state") == "suspended":
            blocked = self.filtered(lambda rec: rec.investment_ids.filtered(lambda inv: inv.state == "active"))
            if blocked:
                raise UserError(
                    _("You cannot suspend investors with active investments: %s")
                    % ", ".join(blocked.mapped("investor_name"))
                )
        return super().write(vals)

    @api.model
    def _check_company(self, company_id):
        """Ensure company consistency for multi-company setup"""
        if company_id:
            self.company_id = company_id


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
        INVESTOR_DOCUMENT_TYPES,
        string="Document Type",
        required=True,
        tracking=True,
    )
    attachment = fields.Binary(string="File Content", required=True)
    filename = fields.Char(string="Filename")
    file_name = fields.Char(string="File Name", compute="_compute_file_metadata", store=True)
    mimetype = fields.Char(string="MIME Type", compute="_compute_file_metadata", store=True)
    has_file = fields.Boolean(compute="_compute_file_metadata", store=True)
    
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

    @api.constrains('attachment')
    def _check_attachment_size(self):
        max_bytes = 50 * 1024 * 1024
        for rec in self:
            if rec.attachment and len(base64.b64decode(rec.attachment)) > max_bytes:
                raise ValidationError(_("Document file size cannot exceed 50 MB."))

    @api.depends("attachment", "filename", "name")
    def _compute_file_metadata(self):
        for doc in self:
            filename = doc.filename or doc.name or ""
            doc.file_name = filename
            doc.mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            doc.has_file = bool(doc.attachment)

    def action_preview(self):
        self.ensure_one()
        if not self.has_file:
            raise UserError(_("Please upload a file before previewing this document."))
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s/%s/attachment/%s?download=false"
            % (self._name, self.id, self.filename or self.name or "document"),
            "target": "new",
        }

    def action_verify(self):
        for doc in self:
            if not doc.has_file:
                raise UserError(_("Upload a file before verifying this document."))
            doc.write({
                "status": "verified",
                "verified_by": self.env.uid,
                "verified_date": fields.Datetime.now(),
            })
            if doc.investor_id.kyc_status == 'pending':
                doc.investor_id.write({'kyc_status': 'partial'})
            doc.message_post(body=_("Document verified successfully."))

    def action_reject(self):
        self.write({"status": "rejected"})
        self.message_post(body=_("Document rejected."))
