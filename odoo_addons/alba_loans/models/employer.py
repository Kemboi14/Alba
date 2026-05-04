# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

class AlbaEmployer(models.Model):
    _name = "alba.employer"
    _description = "Alba Capital Employer Master"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name asc"

    name = fields.Char(string="Employer / Business Name", required=True, tracking=True)
    industry = fields.Selection([
        ("government", "Government / Civil Service"),
        ("education", "Education"),
        ("healthcare", "Healthcare"),
        ("manufacturing", "Manufacturing"),
        ("retail", "Retail / Wholesale"),
        ("finance", "Finance / Insurance"),
        ("tech", "Technology"),
        ("hospitality", "Hospitality / Tourism"),
        ("transport", "Transport / Logistics"),
        ("agriculture", "Agriculture"),
        ("other", "Other"),
    ], string="Industry", tracking=True)
    
    phone = fields.Char(string="Phone Number", tracking=True)
    email = fields.Char(string="Email Address")
    website = fields.Char(string="Website")
    
    # Address
    address = fields.Text(string="Physical Address")
    county = fields.Char(string="County")
    sub_county = fields.Char(string="Sub-County")
    
    # Contacts
    hr_contact_name = fields.Char(string="HR Contact Name")
    hr_contact_phone = fields.Char(string="HR Contact Phone")
    hr_contact_email = fields.Char(string="HR Contact Email")
    
    # Integration
    is_approved = fields.Boolean(string="Approved Employer", default=True, help="Set to False to flag high-risk employers")
    
    # Links
    customer_ids = fields.One2many("alba.customer", "employer_id", string="Employee Borrowers")
    guarantor_ids = fields.One2many("alba.guarantor", "employer_id", string="Employee Guarantors")
    
    employee_count = fields.Integer(string="Employees", compute="_compute_employee_count")

    @api.depends("customer_ids", "guarantor_ids")
    def _compute_employee_count(self):
        for rec in self:
            rec.employee_count = len(rec.customer_ids) + len(rec.guarantor_ids)

    def name_get(self):
        return [(rec.id, rec.name) for rec in self]
