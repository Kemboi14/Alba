# -*- coding: utf-8 -*-
"""
Notification Hooks — Alba Loans

PURPOSE:
  This file was previously duplicating every email already sent by
  loan_application.py (action_submit, action_approve, action_reject,
  action_employer_verification, write→disbursed), causing customers to
  receive TWO copies of every email.

  Those duplicate hooks have been removed.  The canonical send_mail()
  calls live in loan_application.py itself (PHASE 5 Omnichannel sections).

  The ONLY hook kept here is AlbaLoanGuarantorNotificationHook, which
  sends the guarantor email through a different model (alba.loan.guarantor)
  and therefore does NOT duplicate anything in loan_application.py.
"""
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class AlbaLoanGuarantorNotificationHook(models.Model):
    """Send guarantor confirmation email automatically when action_send_confirmation() is called."""

    _inherit = "alba.loan.guarantor"

    def action_send_confirmation(self):
        res = super().action_send_confirmation()
        template = self.env.ref(
            "alba_loans.email_template_guarantor_confirmation",
            raise_if_not_found=False,
        )
        if not template:
            _logger.warning(
                "Email template 'alba_loans.email_template_guarantor_confirmation' not found."
            )
            return res

        for rec in self:
            if rec.guarantor_id.email:
                template.send_mail(rec.id, force_send=False)
                _logger.info(
                    "Automated guarantor confirmation email queued for %s",
                    rec.guarantor_id.name,
                )
            else:
                _logger.warning(
                    "Guarantor %s has no email address — confirmation email skipped.",
                    rec.guarantor_id.name,
                )
        return res
