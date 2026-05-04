# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

class AlbaLoanGuarantorSmsHook(models.Model):
    _inherit = "alba.loan.guarantor"

    def _sms_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param("alba_sms.enabled", default="1") == "1"

    def action_send_confirmation(self):
        res = super(AlbaLoanGuarantorSmsHook, self).action_send_confirmation()
        for rec in self:
            try:
                rec._send_guarantor_confirmation_sms()
            except Exception as e:
                _logger.error("Failed to send guarantor confirmation SMS: %s", str(e))
        return res

    def _send_guarantor_confirmation_sms(self):
        """Send SMS to guarantor for confirmation."""
        self.ensure_one()
        if not self._sms_enabled():
            return

        # 1. Resolve Template
        template = self.env["alba.sms.template"].sudo().search([("code", "=", "guarantor_confirmation_request")], limit=1)
        if not template:
            _logger.warning("SMS Template 'guarantor_confirmation_request' not found.")
            return

        # 2. Resolve Phone
        phone = self.guarantor_id.phone
        if not phone:
            _logger.warning("Guarantor %s has no phone number.", self.guarantor_id.name)
            return

        # 3. Resolve Provider
        provider = self.env["alba.sms.provider"].sudo().search([("is_active", "=", True)], limit=1)
        if not provider:
            _logger.warning("No active SMS provider found.")
            return

        # 4. Render and Send
        ctx = {
            "guarantor_name": self.guarantor_id.name,
            "customer_name": self.customer_id.display_name,
            "code": self.confirmation_code,
            "company_name": self.env.company.name,
        }
        
        message = template.render(ctx)
        
        provider.send_sms(
            phone,
            message,
            res_model="alba.loan.guarantor",
            res_id=self.id,
            template_id=template.id,
        )
        
        self.message_post(body=_("<b>Automated SMS Sent to Guarantor</b>: %s") % message)
