# -*- coding: utf-8 -*-
"""
Loan Document Model
===================
Stores documents and files related to loan applications and loans.
"""

import base64
from odoo import api, fields, models, _, exceptions


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
    topup_id = fields.Many2one(
        'alba.loan.topup',
        string='Top-Up',
        ondelete='cascade',
        index=True,
    )
    partial_payoff_id = fields.Many2one(
        'alba.loan.partial.payoff',
        string='Partial Payoff',
        ondelete='cascade',
        index=True,
    )
    consolidation_id = fields.Many2one(
        'alba.loan.consolidation',
        string='Consolidation',
        ondelete='cascade',
        index=True,
    )
    refinance_id = fields.Many2one(
        'alba.loan.refinance',
        string='Refinance',
        ondelete='cascade',
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
        ondelete='cascade',
    )
    datas = fields.Binary(
        string='File',
        compute='_compute_datas',
        inverse='_inverse_datas',
        store=False,
    )
    upload_filename = fields.Char(
        string='Filename',
        compute='_compute_datas',
        inverse='_inverse_datas',
        store=False,
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

    @api.constrains('datas')
    def _check_datas_size(self):
        max_bytes = 50 * 1024 * 1024
        for rec in self:
            if rec.datas and len(base64.b64decode(rec.datas)) > max_bytes:
                raise exceptions.ValidationError(_("Document file size cannot exceed 50 MB."))

    @api.depends('attachment_id', 'attachment_id.datas', 'attachment_id.name')
    def _compute_datas(self):
        for doc in self:
            attachment = doc.attachment_id
            doc.datas = attachment.datas if attachment else False
            doc.upload_filename = attachment.name if attachment else False

    def _inverse_datas(self):
        Attachment = self.env['ir.attachment']
        for doc in self:
            if not doc.datas:
                continue
            filename = doc.upload_filename or doc.name or _('Document')
            if doc.attachment_id:
                doc.attachment_id.write({
                    'name': filename,
                    'datas': doc.datas,
                })
            else:
                doc.attachment_id = Attachment.create({
                    'name': filename,
                    'datas': doc.datas,
                    'res_model': doc._name,
                    'res_id': doc.id,
                    'type': 'binary',
                })

    def _prepare_attachment_vals(self, vals):
        """Create ir.attachment from inline upload fields before record create."""
        datas = vals.pop('datas', None)
        filename = vals.pop('upload_filename', None) or vals.get('name') or _('Document')
        if datas and not vals.get('attachment_id'):
            vals['attachment_id'] = self.env['ir.attachment'].create({
                'name': filename,
                'datas': datas,
                'type': 'binary',
            }).id
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if not vals.get('partner_id') and vals.get('customer_id'):
                customer = self.env['alba.customer'].browse(vals['customer_id'])
                if customer.partner_id:
                    vals['partner_id'] = customer.partner_id.id
            prepared.append(self._prepare_attachment_vals(vals))
        records = super().create(prepared)
        for record, vals in zip(records, prepared):
            if record.attachment_id and not record.attachment_id.res_id:
                record.attachment_id.write({
                    'res_model': record._name,
                    'res_id': record.id,
                })
        return records

    def write(self, vals):
        vals = dict(vals)
        if 'datas' in vals or 'upload_filename' in vals:
            for doc in self:
                if 'datas' in vals:
                    doc.datas = vals['datas']
                if 'upload_filename' in vals:
                    doc.upload_filename = vals['upload_filename']
            vals = {
                k: v for k, v in vals.items()
                if k not in ('datas', 'upload_filename')
            }
        return super().write(vals)

    def action_preview(self):
        self.ensure_one()
        if not self.datas:
            raise exceptions.UserError(_("Please upload a file before previewing this document."))
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s/%s/datas/%s?download=false"
            % (self._name, self.id, self.upload_filename or self.name or "document"),
            "target": "new",
        }

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

    def action_reject_document(self):
        """Button helper for list views."""
        self.action_reject()

    def action_reset_to_draft(self):
        """Reset document to draft state."""
        self.write({
            'state': 'draft',
            'verified_by': False,
            'verified_date': False,
            'rejection_reason': False,
        })
