# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

class AlbaLoanApplicationSmsHook(models.Model):
    _inherit = "alba.loan.application"

    def _sms_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param("alba_sms.enabled", default="0") == "1"

    def write(self, vals):
        res = super(AlbaLoanApplicationSmsHook, self).write(vals)
        if 'state' in vals:
            for rec in self:
                try:
                    rec._send_status_change_notification(vals['state'])
                except Exception as e:
                    _logger.error("Failed to send status change notification: %s", str(e))
        return res

    def _send_status_change_notification(self, new_state):
        """Logic to send SMS/Email based on the new state."""
        self.ensure_one()
        
        # 1. Resolve Template
        template_code = f"application_{new_state}"
        template = self.env["alba.sms.template"].sudo().search([("code", "=", template_code)], limit=1)
        
        if not template:
            _logger.debug("No SMS template found for code: %s", template_code)
            return

        # 2. Resolve Phone
        customer = self.customer_id
        phone = customer.mpesa_number or customer.partner_id.mobile or customer.partner_id.phone
        
        if not phone or not self._sms_enabled():
            return

        # 3. Resolve Provider
        provider = self.env["alba.sms.provider"].sudo().search([("is_active", "=", True)], limit=1)
        if not provider:
            return

        # 4. Render and Send
        ctx = {
            "customer_name": customer.display_name,
            "application_number": self.application_number,
            "loan_product": self.loan_product_id.name,
            "amount": str(self.requested_amount),
            "state": new_state.replace('_', ' ').capitalize(),
            "company_name": self.env.company.name,
        }
        
        message = template.render(ctx)
        
        provider.send_sms(
            phone,
            message,
            res_model="alba.loan.application",
            res_id=self.id,
            template_id=template.id,
        )
        
        # Log to chatter that SMS was sent
        self.message_post(body=_("<b>Automated SMS Sent</b>: %s") % message)
