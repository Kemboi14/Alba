# -*- coding: utf-8 -*-
import json
import logging
import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AlbaKYCProvider(models.Model):
    """
    Automated Identity Verification API Provider Configuration.
    Supports pluggable backends (e.g., Sandbox, Smile Identity, Metamap).
    """
    _name = "alba.kyc.provider"
    _description = "Alba KYC / Identity Provider"
    _inherit = ["mail.thread"]
    _order = "sequence asc, id desc"

    name = fields.Char(string="Provider Name", required=True, tracking=True)
    provider_type = fields.Selection([
        ('sandbox', 'Sandbox / Mock (Testing)'),
        ('smile_identity', 'Smile Identity'),
        ('metamap', 'Metamap'),
        ('iprs', 'Kenya IPRS (Direct)'),
    ], string="Provider Backend", required=True, default='sandbox', tracking=True)
    
    is_active = fields.Boolean(string="Active Provider", default=False, tracking=True, 
                               help="Only one provider should be active at a time.")
    sequence = fields.Integer(default=10)
    
    api_key = fields.Char(string="API Key", groups="alba_loans.group_director")
    api_secret = fields.Char(string="API Secret", groups="alba_loans.group_director")
    api_base_url = fields.Char(string="API Base URL", help="e.g., https://api.smileidentity.com/v1")
    
    @api.constrains('is_active')
    def _check_single_active(self):
        for rec in self:
            if rec.is_active:
                others = self.search([('id', '!=', rec.id), ('is_active', '=', True)])
                if others:
                    others.write({'is_active': False})

    def action_test_connection(self):
        self.ensure_one()
        if self.provider_type == 'sandbox':
            self.message_post(body=_("Sandbox connection test successful!"))
            return True
        else:
            raise UserError(_("Connection testing for %s is not yet implemented.") % self.provider_type)

    def verify_identity(self, id_number, first_name=None, last_name=None, document_image=None):
        """
        Verify the given identity using the active backend.
        Returns a dictionary:
        {
            'status': 'verified' | 'rejected' | 'manual_review',
            'confidence_score': 0-100,
            'provider_reference': 'txn_12345',
            'notes': 'Matched against IPRS successfully.'
        }
        """
        self.ensure_one()
        
        if self.provider_type == 'sandbox':
            return self._verify_sandbox(id_number, first_name, last_name)
        else:
            # Placeholder for real API implementations
            return {
                'status': 'manual_review',
                'confidence_score': 0,
                'provider_reference': '',
                'notes': _("Provider backend %s not fully implemented. Please verify manually.") % self.provider_type
            }

    def _verify_sandbox(self, id_number, first_name, last_name):
        """
        Sandbox logic:
        - If ID starts with '99', simulate a Fraud / Rejected response.
        - If ID starts with '88', simulate a 'Needs Manual Review' response.
        - Otherwise, simulate a successful verification.
        """
        if not id_number:
            return {'status': 'rejected', 'confidence_score': 0, 'notes': 'ID Number is missing.'}
            
        id_str = str(id_number).strip()
        
        if id_str.startswith('99'):
            return {
                'status': 'rejected',
                'confidence_score': 12,
                'provider_reference': f'SANDBOX-REJ-{id_str}',
                'notes': 'Sandbox: ID number flagged on fraud watchlist.'
            }
        elif id_str.startswith('88'):
            return {
                'status': 'manual_review',
                'confidence_score': 65,
                'provider_reference': f'SANDBOX-REV-{id_str}',
                'notes': 'Sandbox: Document blurry or name mismatch. Manual review required.'
            }
        else:
            return {
                'status': 'verified',
                'confidence_score': 98,
                'provider_reference': f'SANDBOX-VER-{id_str}',
                'notes': f'Sandbox: ID {id_str} verified successfully against national registry.'
            }
