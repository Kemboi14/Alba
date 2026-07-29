# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

class LoanDocument(models.Model):
    _inherit = 'alba.loan.document'

    def write(self, vals):
        # Store old states to compare later
        old_states = {}
        if 'state' in vals:
            for doc in self:
                old_states[doc.id] = doc.state
        
        res = super(LoanDocument, self).write(vals)
        
        if 'state' in vals:
            for doc in self:
                if old_states.get(doc.id) != doc.state:
                    try:
                        doc._fire_document_webhook()
                    except Exception as e:
                        _logger.error("Failed to fire document webhook: %s", e)
        return res

    def _fire_document_webhook(self):
        api_key = self.env["alba.api.key"].sudo().search([("is_active", "=", True)], limit=1)
        if not api_key:
            _logger.warning("No active API key found to fire document webhook")
            return
        
        # Get Django document ID from sync log (Enhanced)
        sync_log = self.env['alba.sync.log'].sudo().search([
            ('odoo_model', '=', 'alba.loan.document'),
            ('odoo_record_id', '=', self.id),
            ('operation', '=', 'create')
        ], limit=1)
        django_document_id = sync_log.django_record_id if sync_log else 0
        
        payload = {
            "odoo_document_id": self.id,
            "new_state": self.state,
            "rejection_reason": self.rejection_reason or "",
            "django_application_id": self.loan_application_id.django_application_id or 0,
            "odoo_application_id": self.loan_application_id.id if self.loan_application_id else 0,
            "document_type": self.document_type or "",  # Enhanced with document type
            "document_name": self.name or "",  # Enhanced with document name
            "django_document_id": django_document_id,  # Enhanced with Django document ID
        }
        _logger.info("Firing document.status_changed webhook for doc_id=%d, state=%s, type=%s", self.id, self.state, self.document_type)
        api_key.send_webhook("document.status_changed", payload)
