# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class LoanApplication(models.Model):
    _inherit = "alba.loan.application"

    def write(self, vals):
        old_state = {}
        if "state" in vals:
            for rec in self:
                old_state[rec.id] = rec.state

        res = super().write(vals)

        if "state" in vals:
            for rec in self:
                if old_state.get(rec.id) != rec.state and rec.state == "disbursed":
                    try:
                        rec._fire_loan_disbursed_webhook()
                    except Exception as e:
                        _logger.error("Failed to fire loan.disbursed webhook: %s", e)
        return res

    def _fire_loan_disbursed_webhook(self):
        api_key = self.env["alba.api.key"].sudo().search(
            [("is_active", "=", True), ("company_id", "=", self.company_id.id)], limit=1
        )
        if not api_key:
            api_key = self.env["alba.api.key"].sudo().search(
                [("is_active", "=", True), ("company_id", "=", False)], limit=1
            )
        if not api_key:
            _logger.warning("No active API key found to fire loan.disbursed webhook")
            return

        loan = getattr(self, "loan_id", None)
        payload = {
            "odoo_application_id": self.id,
            "application_number": self.application_number or "",
            "django_application_id": self.django_application_id or "",
            "loan_number": loan.loan_number if loan else "",
            "odoo_loan_id": loan.id if loan else 0,
            "disbursed_amount": float(self.approved_amount or self.requested_amount or 0),
        }
        _logger.info(
            "Firing loan.disbursed webhook for application_id=%d, django_application_id=%s",
            self.id,
            self.django_application_id,
        )
        api_key.send_webhook_with_retry("loan.disbursed", payload)
