# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlbaBusinessSector(models.Model):
    """
    Business Sector Classification - CBK Compliance (Req #5)
    Top-level industry classification for customer segmentation.
    Examples: Agriculture, Manufacturing, Finance, Trade, etc.
    """
    _name = "alba.business.sector"
    _description = "Business Sector"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"
    _rec_name = "name"

    name = fields.Char(
        string="Sector Name",
        required=True,
        translate=True,
    )
    code = fields.Char(
        string="Sector Code",
        required=True,
        size=20,
        copy=False,
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Display order in dropdowns and reports",
    )
    description = fields.Text(
        string="Description",
        translate=True,
        help="Detailed description of this sector for reference",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    subsector_ids = fields.One2many(
        "alba.business.subsector",
        "sector_id",
        string="Subsectors",
        help="All subsectors under this sector",
    )
    subsector_count = fields.Integer(
        string="Subsector Count",
        compute="_compute_subsector_count",
        store=True,
    )
    customer_ids = fields.One2many(
        "alba.customer",
        "sector_id",
        string="Customers",
    )
    customer_count = fields.Integer(
        string="Customer Count",
        compute="_compute_customer_count",
        store=True,
    )

    # ── Computed Fields ───────────────────────────────────────────────────────
    @api.depends("subsector_ids")
    def _compute_subsector_count(self):
        for rec in self:
            rec.subsector_count = len(rec.subsector_ids)

    @api.depends("customer_ids")
    def _compute_customer_count(self):
        for rec in self:
            rec.customer_count = len(rec.customer_ids)

    @api.constrains("code")
    def _check_code_unique(self):
        for rec in self:
            if self.search([("code", "=", rec.code), ("id", "!=", rec.id)]):
                raise ValidationError(_("Sector code must be unique!"))


class AlbaBusinessSubsector(models.Model):
    """
    Business Subsector Classification - CBK Compliance (Req #5)
    Child of sector with dynamic filtering (e.g. Agriculture > Crop Farming)
    """
    _name = "alba.business.subsector"
    _description = "Business Subsector"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sector_id, sequence, name"
    _rec_name = "name"

    name = fields.Char(
        string="Subsector Name",
        required=True,
        translate=True,
    )
    code = fields.Char(
        string="Subsector Code",
        required=True,
        size=20,
        copy=False,
    )
    sector_id = fields.Many2one(
        "alba.business.sector",
        string="Sector",
        required=True,
        ondelete="restrict",
        index=True,
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Display order within the sector",
    )
    description = fields.Text(
        string="Description",
        translate=True,
        help="Detailed description of this subsector",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    customer_ids = fields.One2many(
        "alba.customer",
        "subsector_id",
        string="Customers",
    )
    customer_count = fields.Integer(
        string="Customer Count",
        compute="_compute_customer_count",
        store=True,
    )

    # ── Computed Fields ───────────────────────────────────────────────────────
    sector_name = fields.Char(
        string="Sector Name",
        compute="_compute_sector_name",
        store=True,
    )

    @api.depends("sector_id", "sector_id.name")
    def _compute_sector_name(self):
        for rec in self:
            rec.sector_name = rec.sector_id.name or ""

    @api.depends("customer_ids")
    def _compute_customer_count(self):
        for rec in self:
            rec.customer_count = len(rec.customer_ids)

    @api.constrains("code", "sector_id")
    def _check_code_sector_unique(self):
        for rec in self:
            if self.search([
                ("code", "=", rec.code),
                ("sector_id", "=", rec.sector_id.id),
                ("id", "!=", rec.id),
            ]):
                raise ValidationError(_("Subsector code must be unique within each sector!"))