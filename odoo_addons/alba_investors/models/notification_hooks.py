# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

class AlbaInvestmentNotificationHook(models.Model):
    _inherit = "alba.investment"

    def write(self, vals):
        res = super(AlbaInvestmentNotificationHook, self).write(vals)
        if 'state' in vals and vals['state'] == 'active':
            for rec in self:
                rec._send_investment_email("alba_investors.email_template_investment_active")
        return res

    def action_accrue_monthly_interest(self):
        accrual = super(AlbaInvestmentNotificationHook, self).action_accrue_monthly_interest()
        if accrual:
            template = self.env.ref("alba_investors.email_template_interest_accrued", raise_if_not_found=False)
            if template and self.investor_id.email:
                template.send_mail(accrual.id, force_send=False)
                _logger.info("Automated interest accrual email queued for %s", self.investment_number)
        return accrual

    def _send_investment_email(self, template_xmlid):
        """Helper to send email to the investor."""
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            _logger.warning("Email template %s not found.", template_xmlid)
            return

        for rec in self:
            if rec.investor_id.email:
                template.send_mail(rec.id, force_send=False)
                _logger.info("Automated email (%s) queued for %s", template_xmlid, rec.investment_number)
            else:
                _logger.warning("Investor %s has no email address.", rec.investor_id.display_name)
