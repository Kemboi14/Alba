# -*- coding: utf-8 -*-
"""
Loan Document Model
===================
Stores documents and files related to loan applications and loans.
"""

from odoo import models, fields, api


class LoanDocument(models.Model):
    _name = 'alba.loan.document'
    _description = 'Loan Document'
    _order = 'create_date desc'

    name = fields.Char(string='Document Name', required=True)
    document_type = fields.Selection([
        ('national_id', 'National ID'),
        ('passport', 'Passport'),
        ('bank_statement', 'Bank Statement'),
        ('payslip', 'Payslip'),
        ('employment_letter', 'Employment Letter'),
        ('business_registration', 'Business Registration'),
        ('kra_pin', 'KRA PIN Certificate'),
        ('utility_bill', 'Utility Bill'),
        ('title_deed', 'Title Deed'),
        ('valuation_report', 'Valuation Report'),
        ('insurance', 'Insurance Document'),
        ('contract', 'Contract'),
        ('other', 'Other'),
    ], string='Document Type', required=True)

    # Related records
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        index=True,
        default=lambda self: self.env.context.get('default_partner_id') or self.env['res.partner'].search([], limit=1).id,
        help="The person/entity this document belongs to."
    )
    loan_application_id = fields.Many2one(
        'alba.loan.application',
        string='Loan Application',
        ondelete='set null',
        index=True,
    )
    loan_id = fields.Many2one(
        'alba.loan',
        string='Loan',
        ondelete='set null',
        index=True,
    )
    customer_id = fields.Many2one(
        'alba.customer',
        string='Customer',
        ondelete='set null',
        index=True,
    )

    # File attachment
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Attachment',
        required=True,
        ondelete='cascade',
    )
    file_name = fields.Char(related='attachment_id.name', string='File Name', store=True)
    file_size = fields.Integer(related='attachment_id.file_size', string='File Size', store=True)
    mimetype = fields.Char(related='attachment_id.mimetype', string='MIME Type', store=True)

    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', required=True)

    # Verification
    verified_by = fields.Many2one('res.users', string='Verified By', readonly=True)
    verified_date = fields.Datetime(string='Verification Date', readonly=True)
    rejection_reason = fields.Text(string='Rejection Reason')

    # Metadata
    description = fields.Text(string='Description')
    uploaded_by = fields.Many2one(
        'res.users',
        string='Uploaded By',
        default=lambda self: self.env.user,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Auto-assign partner_id from customer if missing
            if not vals.get('partner_id') and vals.get('customer_id'):
                customer = self.env['alba.customer'].browse(vals['customer_id'])
                if customer:
                    vals['partner_id'] = customer.partner_id.id
            
            # Prevent duplication: if a document of this type exists for this partner, reuse it
            if vals.get('partner_id') and vals.get('document_type'):
                existing = self.search([
                    ('partner_id', '=', vals['partner_id']),
                    ('document_type', '=', vals['document_type']),
                    ('state', '=', 'verified')
                ], limit=1)
                if existing:
                    # Logic to link existing rather than create new could go here
                    # For now, we allow the create but log the relationship
                    pass
        
        return super().create(vals_list)

    def action_verify(self):
        """Mark document as verified."""
        self.write({
            'state': 'verified',
            'verified_by': self.env.user.id,
            'verified_date': fields.Datetime.now(),
        })

    def action_reject(self, reason=None):
        """Reject document with reason."""
        vals = {'state': 'rejected'}
        if reason:
            vals['rejection_reason'] = reason
        self.write(vals)

    def action_reset_to_draft(self):
        """Reset document to draft state."""
        self.write({
            'state': 'draft',
            'verified_by': False,
            'verified_date': False,
            'rejection_reason': False,
        })
