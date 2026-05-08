# -*- coding: utf-8 -*-
from odoo import fields, models


class AlbaCustomerTag(models.Model):
    """Tags for customer categorization and segmentation"""
    _name = "alba.customer.tag"
    _description = "Customer Tag"
    _order = "category, name"
    
    name = fields.Char(string="Tag Name", required=True, translate=True)
    color = fields.Integer(string="Color Index", default=0)
    description = fields.Text(string="Description")
    category = fields.Selection([
        ("risk", "Risk Level"),
        ("segment", "Customer Segment"),
        ("source", "Lead Source"),
        ("custom", "Custom"),
    ], string="Category", default="custom", required=True)
    active = fields.Boolean(default=True)
    
    customer_count = fields.Integer(
        string="Customers",
        compute="_compute_customer_count",
    )
    
    def _compute_customer_count(self):
        for tag in self:
            tag.customer_count = self.env["alba.customer"].search_count(
                [("tag_ids", "in", tag.id)]
            )
