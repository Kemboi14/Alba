# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlbaLoanStatusReason(models.Model):
    _inherit = ["mail.thread", "mail.activity.mixin"]
    """
    Loan Status Reason (Req #8)
    Configurable dropdown reasons for Deferred and Declined statuses.
    CBK compliance for audit trail and decision documentation.
    """
    _name = "alba.loan.status.reason"
    _description = "Loan Application Status Reason"
    _order = "category, sequence, name"
    _rec_name = "name"

    # ── Status Categories ─────────────────────────────────────────────────────
    CATEGORY_CHOICES = [
        ("deferred", "Deferred"),
        ("declined", "Declined"),
    ]

    name = fields.Char(
        string="Reason",
        required=True,
        translate=True,
    )
    category = fields.Selection(
        selection=CATEGORY_CHOICES,
        string="Status Category",
        required=True,
        index=True,
        help="Whether this reason is for Deferred or Declined status",
    )
    code = fields.Char(
        string="Code",
        size=20,
        help="Short code for reporting",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Display order in dropdowns",
    )
    description = fields.Text(
        string="Description",
        translate=True,
        help="Detailed description of this reason",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )

    # ── Usage Tracking ────────────────────────────────────────────────────────
    application_count = fields.Integer(
        string="Application Count",
        compute="_compute_application_count",
        store=True,
        help="How many applications have used this reason",
    )

    @api.depends("name")  # dummy dependency to trigger recompute
    def _compute_application_count(self):
        for rec in self:
            rec.application_count = self.env["alba.loan.application"].search_count(
                [("status_reason_id", "=", rec.id)]
            )

    class Meta:
        db_table = "alba_loan_status_reason"

    def __str__(self):
        return f"{self.get_category_display()} - {self.name}"

    @api.constrains('name', 'category')
    def _check_name_category_unique(self):
        """Ensure reason name is unique within each category"""
        if self.search([('name', '=', self.name), ('category', '=', self.category), ('id', '!=', self.id)]):
            raise ValidationError(_("Reason name must be unique within each category!"))
