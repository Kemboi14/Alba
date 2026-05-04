# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class ResPartner(models.Model):
    _inherit = "res.partner"

    # ── Identity ──────────────────────────────────────────────────────────────
    id_number = fields.Char(string="ID / Passport Number", tracking=True, index=True)
    id_type = fields.Selection(
        selection=[
            ("national_id", "National ID"),
            ("passport", "Passport"),
            ("alien_id", "Alien ID / Foreign Certificate"),
        ],
        string="ID Type",
        default="national_id",
        tracking=True,
    )
    date_of_birth = fields.Date(string="Date of Birth")
    gender = fields.Selection(
        selection=[
            ("male", "Male"),
            ("female", "Female"),
            ("other", "Other / Prefer not to say"),
        ],
        string="Gender",
        tracking=True,
    )

    # ── Employment (Centralized) ──────────────────────────────────────────────
    employer_id = fields.Many2one(
        "alba.employer",
        string="Employer",
        tracking=True,
    )
    job_title = fields.Char(string="Job Title")
    monthly_income = fields.Monetary(
        string="Monthly Net Income",
        currency_field="currency_id",
    )

    # ── Alba Links ────────────────────────────────────────────────────────────
    is_alba_customer = fields.Boolean(string="Is Alba Customer", compute="_compute_alba_links", store=True)
    is_alba_guarantor = fields.Boolean(string="Is Alba Guarantor", compute="_compute_alba_links", store=True)
    is_alba_investor = fields.Boolean(string="Is Alba Investor", compute="_compute_alba_links", store=True)

    def _compute_alba_links(self):
        for rec in self:
            # Initialize defaults
            rec.is_alba_customer = False
            rec.is_alba_guarantor = False
            rec.is_alba_investor = False
            
            # Check if models are fully loaded in registry before searching
            # This handles cross-module dependencies during updates
            registry = self.env.registry
            
            if 'alba.customer' in registry.models and 'partner_id' in registry.models['alba.customer']._fields:
                rec.is_alba_customer = bool(self.env['alba.customer'].search([('partner_id', '=', rec.id)], limit=1))
            
            if 'alba.guarantor' in registry.models and 'partner_id' in registry.models['alba.guarantor']._fields:
                rec.is_alba_guarantor = bool(self.env['alba.guarantor'].search([('partner_id', '=', rec.id)], limit=1))
            
            if 'alba.investor' in registry.models and 'partner_id' in registry.models['alba.investor']._fields:
                rec.is_alba_investor = bool(self.env['alba.investor'].search([('partner_id', '=', rec.id)], limit=1))
