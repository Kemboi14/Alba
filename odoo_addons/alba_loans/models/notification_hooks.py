# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

class AlbaLoanApplicationNotificationHook(models.Model):
    _inherit = "alba.loan.application"

    def action_submit(self):
        res = super(AlbaLoanApplicationNotificationHook, self).action_submit()
        self._send_application_email("alba_loans.email_template_application_submitted")
        return res

    def action_approve(self):
        res = super(AlbaLoanApplicationNotificationHook, self).action_approve()
        self._send_application_email("alba_loans.email_template_application_approved")
        return res

    def action_reject(self):
        res = super(AlbaLoanApplicationNotificationHook, self).action_reject()
        self._send_application_email("alba_loans.email_template_application_rejected")
        return res

    def action_employer_verification(self):
        res = super(AlbaLoanApplicationNotificationHook, self).action_employer_verification()
        self._send_application_email("alba_loans.email_template_employer_verification")
        return res

    def write(self, vals):
        res = super(AlbaLoanApplicationNotificationHook, self).write(vals)
        if 'state' in vals and vals['state'] == 'disbursed':
            self._send_application_email("alba_loans.email_template_loan_disbursed")
        return res

    def _send_application_email(self, template_xmlid):
        """Helper to send email to the customer or employer."""
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            _logger.warning("Email template %s not found.", template_xmlid)
            return

        for rec in self:
            # Check if target email exists before sending
            email_to = False
            if "employer_verification" in template_xmlid:
                email_to = rec.customer_id.employer_id.email
            else:
                email_to = rec.customer_id.email

            if not email_to:
                _logger.warning("No email address found for notification on %s", rec.application_number)
                continue

            template.send_mail(rec.id, force_send=False)
            _logger.info("Automated email (%s) queued for %s", template_xmlid, rec.application_number)


class AlbaLoanGuarantorNotificationHook(models.Model):
    _inherit = "alba.loan.guarantor"

    def action_send_confirmation(self):
        res = super(AlbaLoanGuarantorNotificationHook, self).action_send_confirmation()
        template = self.env.ref("alba_loans.email_template_guarantor_confirmation", raise_if_not_found=False)
        if not template:
            _logger.warning("Email template 'alba_loans.email_template_guarantor_confirmation' not found.")
            return res

        for rec in self:
            if rec.guarantor_id.email:
                template.send_mail(rec.id, force_send=False)
                _logger.info("Automated guarantor confirmation email queued for %s", rec.guarantor_id.name)
            else:
                _logger.warning("Guarantor %s has no email address.", rec.guarantor_id.name)
        return res
