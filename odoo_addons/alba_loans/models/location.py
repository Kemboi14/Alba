# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AlbaCounty(models.Model):
    """Kenyan County - Top level of location hierarchy"""
    _name = "alba.county"
    _description = "County"
    _order = "name"
    
    name = fields.Char(string="County Name", required=True, translate=True)
    code = fields.Char(string="County Code", required=True, size=10)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string="Color Index", default=0)
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    
    sub_county_ids = fields.One2many(
        "alba.sub.county",
        "county_id",
        string="Sub-Counties",
    )
    sub_county_count = fields.Integer(
        string="Sub-Counties Count",
        compute="_compute_counts",
        store=True,
    )
    
    @api.depends("sub_county_ids")
    def _compute_counts(self):
        for rec in self:
            rec.sub_county_count = len(rec.sub_county_ids)


class AlbaSubCounty(models.Model):
    """Sub-County - Second level of location hierarchy"""
    _name = "alba.sub.county"
    _description = "Sub-County"
    _order = "county_id, name"
    
    name = fields.Char(string="Sub-County Name", required=True, translate=True)
    code = fields.Char(string="Sub-County Code", required=True, size=10)
    county_id = fields.Many2one(
        "alba.county",
        string="County",
        required=True,
        ondelete="restrict",
        index=True,
    )
    sequence = fields.Integer(default=10)
    color = fields.Integer(string="Color Index", default=0)
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    
    ward_ids = fields.One2many(
        "alba.ward",
        "sub_county_id",
        string="Wards",
    )
    ward_count = fields.Integer(
        string="Wards Count",
        compute="_compute_counts",
        store=True,
    )
    
    @api.depends("ward_ids")
    def _compute_counts(self):
        for rec in self:
            rec.ward_count = len(rec.ward_ids)


class AlbaWard(models.Model):
    """Ward - Third level of location hierarchy"""
    _name = "alba.ward"
    _description = "Ward"
    _order = "sub_county_id, name"
    
    name = fields.Char(string="Ward Name", required=True, translate=True)
    code = fields.Char(string="Ward Code", required=True, size=10)
    sub_county_id = fields.Many2one(
        "alba.sub.county",
        string="Sub-County",
        required=True,
        ondelete="restrict",
        index=True,
    )
    county_id = fields.Many2one(
        "alba.county",
        string="County",
        related="sub_county_id.county_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(default=10)
    color = fields.Integer(string="Color Index", default=0)
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
