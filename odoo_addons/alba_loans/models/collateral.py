# -*- coding: utf-8 -*-
"""
Alba Capital Collateral Management
Tracks land, vehicle, equipment, shares, and other collateral
LTV validation, margin call alerts, release on loan closure
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaCollateral(models.Model):
    """Collateral Master Data - Registry of all assets"""
    
    _name = "alba.collateral"
    _description = "Loan Collateral"
    _order = "name asc"
    _inherit = ["mail.thread"]
    
    # Basic Information
    name = fields.Char(string="Description", required=True, tracking=True)
    collateral_type = fields.Selection([
        ("land", "Land / Property"),
        ("vehicle", "Vehicle"),
        ("equipment", "Equipment / Machinery"),
        ("shares", "Shares / Securities"),
        ("deposit", "Fixed Deposit / Chattel"),
        ("guarantee", "Bank Guarantee"),
        ("other", "Other"),
    ], string="Collateral Type", required=True, tracking=True)
    
    # Identification
    registration_number = fields.Char(
        string="Registration Number",
        tracking=True,
        help="Title deed, logbook number, serial number, etc.",
    )
    
    # Type-Specific Fields
    # -- Land
    land_title_deed = fields.Char(string="Title Deed Number")
    land_reference = fields.Char(string="Land Reference Number")
    land_size = fields.Char(string="Size (Acres/Sq Ft)")
    land_use = fields.Selection([
        ("residential", "Residential"),
        ("commercial", "Commercial"),
        ("agricultural", "Agricultural"),
        ("industrial", "Industrial"),
    ], string="Land Use")
    land_encumbrances = fields.Selection([
        ("none", "None"),
        ("mortgage", "Existing Mortgage"),
        ("caveat", "Caveat / Restriction"),
        ("dispute", "Under Dispute"),
    ], string="Encumbrances", default="none")
    
    # -- Vehicle
    vehicle_make = fields.Char(string="Make")
    vehicle_model = fields.Char(string="Model")
    vehicle_year = fields.Integer(string="Year")
    vehicle_color = fields.Char(string="Color")
    vehicle_chassis = fields.Char(string="Chassis Number")
    vehicle_engine = fields.Char(string="Engine Number")
    vehicle_logbook_held = fields.Boolean(string="Logbook Held")
    vehicle_insurance_expiry = fields.Date(string="Insurance Expiry")
    vehicle_condition = fields.Selection([
        ("excellent", "Excellent"),
        ("good", "Good"),
        ("fair", "Fair"),
        ("poor", "Poor"),
    ], string="Condition")
    
    # -- Equipment
    equipment_manufacturer = fields.Char(string="Manufacturer")
    equipment_serial = fields.Char(string="Serial Number")
    equipment_year = fields.Integer(string="Year of Manufacture")
    equipment_depreciation = fields.Float(string="Depreciation Rate (%)", digits=(5, 2))
    
    # -- Shares
    shares_cds_account = fields.Char(string="CDS Account Number")
    shares_company = fields.Char(string="Company Name")
    shares_quantity = fields.Integer(string="Number of Shares")
    shares_current_value = fields.Monetary(
        string="Current Value per Share",
        currency_field="currency_id",
    )
    
    # Location
    location_county = fields.Char(string="County")
    location_subcounty = fields.Char(string="Sub-County")
    location_ward = fields.Char(string="Ward")
    location_description = fields.Text(string="Location Description")
    
    # Valuation
    valuation_amount = fields.Monetary(
        string="Market Value",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    valuation_date = fields.Date(string="Valuation Date", required=True)
    valued_by = fields.Char(string="Valued By")
    valuation_expiry = fields.Date(
        string="Valuation Expires",
        compute="_compute_valuation_expiry",
        store=True,
    )
    forced_sale_value = fields.Monetary(
        string="Forced Sale Value (70%)",
        currency_field="currency_id",
        compute="_compute_forced_sale",
        store=True,
    )
    
    # Owner
    owner_id = fields.Many2one(
        "res.partner",
        string="Registered Owner",
        help="May differ from borrower",
    )
    owner_name = fields.Char(
        string="Owner Name",
        related="owner_id.name",
        readonly=True,
    )
    
    # Status
    status = fields.Selection([
        ("available", "Available"),
        ("pledged", "Pledged"),
        ("released", "Released"),
        ("liquidated", "Liquidated"),
    ], string="Status", default="available", tracking=True)
    
    # Currency
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    
    # Documents
    document_ids = fields.One2many(
        "alba.collateral.document",
        "collateral_id",
        string="Documents",
    )
    
    # Relations
    loan_collateral_ids = fields.One2many(
        "alba.loan.collateral",
        "collateral_id",
        string="Loan Assignments",
    )
    active_loan_count = fields.Integer(
        string="Active Loans Using This",
        compute="_compute_loan_count",
        store=True,
    )
    
    # Physical Document Tracking
    physical_document_location = fields.Selection([
        ("safe", "Company Safe"),
        ("file", "Filing Cabinet"),
        ("bank", "Bank Safe Custody"),
        ("held", "Held by Customer"),
    ], string="Physical Document Location")
    document_returned_date = fields.Date(string="Document Returned to Owner")
    document_returned_to = fields.Char(string="Returned To")
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.depends("valuation_date")
    def _compute_valuation_expiry(self):
        from datetime import date, timedelta
        for rec in self:
            if rec.valuation_date:
                rec.valuation_expiry = rec.valuation_date + timedelta(days=365)
            else:
                rec.valuation_expiry = False
    
    @api.depends("valuation_amount")
    def _compute_forced_sale(self):
        for rec in self:
            rec.forced_sale_value = rec.valuation_amount * 0.7  # 70% forced sale value
    
    @api.depends("loan_collateral_ids", "loan_collateral_ids.status")
    def _compute_loan_count(self):
        for rec in self:
            rec.active_loan_count = len(
                rec.loan_collateral_ids.filtered(lambda c: c.status == "pledged")
            )
    
    # =========================================================================
    # ORM Overrides
    # =========================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name"):
                vals["name"] = self.env["ir.sequence"].next_by_code("alba.collateral") or "New Collateral"
        return super().create(vals_list)
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_pledge(self):
        """Mark as pledged to a loan"""
        for rec in self:
            rec.write({"status": "pledged"})
            rec.message_post(body=_("Collateral pledged to loan."))
    
    def action_release(self):
        """Release collateral"""
        for rec in self:
            # Check if still used by active loans
            if rec.active_loan_count > 0:
                raise UserError(_(
                    "Cannot release - still pledged to %s active loan(s). "
                    "Release from loans first."
                ) % rec.active_loan_count)
            
            rec.write({"status": "released"})
            rec.message_post(body=_("<b>COLLATERAL RELEASED</b>"))
    
    def action_liquidate(self):
        """Mark for liquidation (recovery)"""
        for rec in self:
            rec.write({"status": "liquidated"})
            rec.message_post(body=_("<b>COLLATERAL MARKED FOR LIQUIDATION</b>"))
    
    def action_view_active_loans(self):
        """View loans using this collateral"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Active Loans - %s") % self.name,
            "res_model": "alba.loan.collateral",
            "view_mode": "list,form",
            "domain": [
                ("collateral_id", "=", self.id),
                ("status", "=", "pledged"),
            ],
        }


class AlbaLoanCollateral(models.Model):
    """Junction: Collateral assigned to specific loans"""
    
    _name = "alba.loan.collateral"
    _description = "Loan Collateral Assignment"
    _order = "create_date desc"
    _inherit = ["mail.thread"]
    
    # Links
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="cascade",
    )
    loan_application_id = fields.Many2one(
        "alba.loan.application",
        string="Loan Application",
        related="loan_id.application_id",
        store=True,
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="loan_id.customer_id",
        store=True,
    )
    collateral_id = fields.Many2one(
        "alba.collateral",
        string="Collateral",
        required=True,
        ondelete="restrict",
        domain="[('status', 'in', ['available', 'pledged'])]",
    )
    
    # Assignment Details
    assignment_date = fields.Date(
        string="Assigned On",
        required=True,
        default=fields.Date.today,
    )
    release_date = fields.Date(string="Released On")
    
    # Loan-to-Value
    loan_amount = fields.Monetary(
        string="Loan Amount",
        currency_field="currency_id",
        related="loan_id.principal_amount",
        store=True,
    )
    collateral_value = fields.Monetary(
        string="Collateral Value",
        currency_field="currency_id",
        related="collateral_id.valuation_amount",
        store=True,
    )
    forced_sale_value = fields.Monetary(
        string="Forced Sale Value",
        currency_field="currency_id",
        related="collateral_id.forced_sale_value",
        store=True,
    )
    ltv_ratio = fields.Float(
        string="LTV Ratio (%)",
        digits=(5, 2),
        compute="_compute_ltv",
        store=True,
    )
    ltv_status = fields.Selection([
        ("good", "Good"),
        ("caution", "Caution"),
        ("exceeded", "Limit Exceeded"),
    ], string="LTV Status", compute="_compute_ltv", store=True)
    
    # LTV Limits by Type
    ltv_limit = fields.Float(
        string="LTV Limit (%)",
        compute="_compute_ltv_limit",
        store=True,
    )
    
    # Margin Call (for shares/fluctuating)
    margin_call_threshold = fields.Float(
        string="Margin Call Threshold (%)",
        default=150.0,
        help="If LTV exceeds this percentage, action required",
    )
    margin_call_triggered = fields.Boolean(
        string="Margin Call Triggered",
        compute="_compute_margin_call",
        store=True,
    )
    
    # Status
    status = fields.Selection([
        ("pledged", "Pledged"),
        ("released", "Released"),
        ("liquidated", "Liquidated"),
    ], string="Status", default="pledged", tracking=True)
    
    # Liquidation
    liquidation_date = fields.Date(string="Liquidation Date")
    liquidation_amount = fields.Monetary(
        string="Liquidation Proceeds",
        currency_field="currency_id",
    )
    liquidation_buyer = fields.Char(string="Buyer")
    liquidation_notes = fields.Text(string="Liquidation Notes")
    
    # Currency
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="loan_id.currency_id",
        store=True,
    )
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.depends("collateral_id", "collateral_id.collateral_type")
    def _compute_ltv_limit(self):
        limits = {
            "land": 70.0,
            "vehicle": 60.0,
            "equipment": 50.0,
            "shares": 40.0,
            "deposit": 90.0,
            "guarantee": 80.0,
            "other": 50.0,
        }
        for rec in self:
            if rec.collateral_id:
                rec.ltv_limit = limits.get(rec.collateral_id.collateral_type, 50.0)
            else:
                rec.ltv_limit = 50.0
    
    @api.depends("loan_amount", "collateral_value", "ltv_limit")
    def _compute_ltv(self):
        for rec in self:
            if rec.collateral_value and rec.collateral_value > 0:
                rec.ltv_ratio = (rec.loan_amount / rec.collateral_value) * 100
                
                # Determine status
                if rec.ltv_ratio > rec.ltv_limit:
                    rec.ltv_status = "exceeded"
                elif rec.ltv_ratio > rec.ltv_limit * 0.9:  # Within 10% of limit
                    rec.ltv_status = "caution"
                else:
                    rec.ltv_status = "good"
            else:
                rec.ltv_ratio = 0
                rec.ltv_status = "good"
    
    @api.depends("ltv_ratio", "margin_call_threshold")
    def _compute_margin_call(self):
        for rec in self:
            rec.margin_call_triggered = rec.ltv_ratio > rec.margin_call_threshold
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_check_ltv(self):
        """Validate LTV against limits"""
        for rec in self:
            if rec.ltv_status == "exceeded":
                raise UserError(_(
                    "LTV ratio of %.2f%% exceeds limit of %.2f%% for %s collateral. "
                    "Need additional collateral or reduce loan amount."
                ) % (rec.ltv_ratio, rec.ltv_limit, rec.collateral_id.collateral_type))
            elif rec.ltv_status == "caution":
                return {
                    "warning": {
                        "title": _("LTV Near Limit"),
                        "message": _(
                            "LTV is %.2f%%, approaching limit of %.2f%%. Monitor closely."
                        ) % (rec.ltv_ratio, rec.ltv_limit),
                    }
                }
    
    def action_release(self):
        """Release collateral from this loan"""
        for rec in self:
            # Check if collateral still needed (loan not closed)
            if rec.loan_id.state not in ["closed", "written_off"]:
                # Check if this is the only collateral
                other_collateral = self.search([
                    ("loan_id", "=", rec.loan_id.id),
                    ("id", "!=", rec.id),
                    ("status", "=", "pledged"),
                ])
                if not other_collateral:
                    raise UserError(_(
                        "Cannot release - this is the only collateral for active loan %s"
                    ) % rec.loan_id.loan_number)
            
            rec.write({
                "status": "released",
                "release_date": fields.Date.today(),
            })
            rec.message_post(body=_("Collateral released from loan %s") % rec.loan_id.loan_number)
            
            # Check if collateral can be marked available
            rec.collateral_id.action_release()
    
    def action_liquidate(self):
        """Mark for liquidation"""
        for rec in self:
            rec.write({
                "status": "liquidated",
                "liquidation_date": fields.Date.today(),
            })
            rec.collateral_id.action_liquidate()


class AlbaCollateralDocument(models.Model):
    """Documents for collateral (title deeds, logbooks, etc.)"""
    
    _name = "alba.collateral.document"
    _description = "Collateral Document"
    _order = "create_date desc"
    
    collateral_id = fields.Many2one(
        "alba.collateral",
        string="Collateral",
        required=True,
        ondelete="cascade",
    )
    
    document_type = fields.Selection([
        ("title_deed", "Title Deed"),
        ("logbook", "Vehicle Logbook"),
        ("valuation", "Valuation Report"),
        ("insurance", "Insurance Policy"),
        ("photo", "Photograph"),
        ("survey", "Survey Plan"),
        ("id", "Owner ID"),
        ("power_attorney", "Power of Attorney"),
        ("other", "Other"),
    ], string="Document Type", required=True)
    
    name = fields.Char(string="Description", required=True)
    attachment = fields.Binary(string="File", required=True, attachment=True)
    file_name = fields.Char(string="File Name")
    
    date_received = fields.Date(string="Date Received")
    verified = fields.Boolean(string="Verified", default=False)
    verified_by = fields.Many2one("res.users", string="Verified By")
    verified_date = fields.Date(string="Verified On")
    
    notes = fields.Text(string="Notes")
