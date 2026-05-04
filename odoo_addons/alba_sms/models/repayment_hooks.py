# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

class AlbaLoanRepaymentSmsHook(models.Model):
    _inherit = "alba.loan.repayment"

    def _sms_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param("alba_sms.enabled", default="1") == "1"

    def write(self, vals):
        res = super(AlbaLoanRepaymentSmsHook, self).write(vals)
        if 'state' in vals and vals['state'] == 'posted':
            for rec in self:
                try:
                    rec._send_repayment_confirmation_sms()
                except Exception as e:
                    _logger.error("Failed to send repayment confirmation SMS: %s", str(e))
        return res

    def _send_repayment_confirmation_sms(self):
        """Send SMS when a repayment is posted."""
        self.ensure_one()
        if not self._sms_enabled():
            return

        # 1. Resolve Template
        template = self.env["alba.sms.template"].sudo().search([("code", "=", "payment_confirmation")], limit=1)
        if not template:
            return

        # 2. Resolve Phone
        customer = self.loan_id.customer_id
        phone = customer.mpesa_number or customer.partner_id.mobile or customer.partner_id.phone
        if not phone:
            return

        # 3. Resolve Provider
        provider = self.env["alba.sms.provider"].sudo().search([("is_active", "=", True)], limit=1)
        if not provider:
            return

        # 4. Render and Send
        ctx = {
            "customer_name": customer.display_name,
            "loan_number": self.loan_id.loan_number,
            "amount": "%.2f" % self.amount_paid,
            "outstanding_balance": "%.2f" % self.loan_id.outstanding_balance,
            "company_name": self.env.company.name,
        }
        
        message = template.render(ctx)
        
        provider.send_sms(
            phone,
            message,
            res_model="alba.loan.repayment",
            res_id=self.id,
            template_id=template.id,
        )
        
        self.message_post(body=_("<b>Automated SMS Sent</b>: %s") % message)
