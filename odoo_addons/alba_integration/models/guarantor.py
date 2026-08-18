# -*- coding: utf-8 -*-
import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class LoanGuarantor(models.Model):
    _inherit = "alba.loan.guarantor"

    def write(self, vals):
        old_status = {}
        if "status" in vals:
            for rec in self:
                old_status[rec.id] = rec.status

        res = super().write(vals)

        if "status" in vals:
            for rec in self:
                if old_status.get(rec.id) != rec.status:
                    try:
                        rec._fire_guarantor_webhook()
                    except Exception as e:
                        _logger.error("Failed to fire guarantor webhook: %s", e)
        return res

    def _fire_guarantor_webhook(self):
        company = self.loan_application_id.company_id
        api_key = self.env["alba.api.key"].sudo().search(
            [("is_active", "=", True), ("company_id", "=", company.id)], limit=1
        )
        if not api_key:
            api_key = self.env["alba.api.key"].sudo().search(
                [("is_active", "=", True), ("company_id", "=", False)], limit=1
            )
        if not api_key:
            _logger.warning("No active API key found to fire guarantor webhook")
            return

        payload = {
            "odoo_loan_guarantor_id": self.id,
            "django_loan_guarantor_id": self.django_loan_guarantor_id or 0,
            "odoo_guarantor_id": self.guarantor_id.id,
            "odoo_application_id": self.loan_application_id.id if self.loan_application_id else 0,
            "django_application_id": self.loan_application_id.django_application_id or 0,
            "new_status": self.status or "",
            "rejection_reason": self.rejection_reason or "",
            "confirmed_method": self.confirmed_method or "",
            "confirmed_date": fields.Datetime.to_string(self.confirmed_date) if self.confirmed_date else "",
        }
        _logger.info(
            "Firing guarantor.status_changed webhook for loan_guarantor_id=%d, status=%s",
            self.id,
            self.status,
        )
        api_key.send_webhook_with_retry("guarantor.status_changed", payload)
