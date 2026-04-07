# -*- coding: utf-8 -*-
"""
collection_hooks.py — Finally wires the existing sms_template field on
alba.loan.collection.stage to actually send SMS.

The field `sms_template` (Text) already exists on alba.loan.collection.stage
with default content populated.  This module overrides action_send_collection_reminder()
on alba.loan to call the SMS provider when that field is set.
"""

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class AlbaLoanCollectionSmsHook(models.Model):
    _inherit = "alba.loan"

    # ------------------------------------------------------------------
    # Override
    # ------------------------------------------------------------------

    def action_send_collection_reminder(self):
        """Override to also fire an SMS through the active alba.sms.provider
        when the collection stage has an ``sms_template`` configured.

        The super() call still runs the e-mail / activity logic defined in
        alba_loans.  The SMS send is *additive* — it runs regardless of
        whether ``auto_send_reminder`` is True, as long as:

        1. The ``alba_sms.enabled`` system parameter is not "0".
        2. ``self.collection_stage_id`` exists and carries a non-empty
           ``sms_template`` text.
        3. At least one :class:`alba.sms.provider` is marked active.
        4. A phone number can be resolved for the borrower.
        """
        result = super().action_send_collection_reminder()

        # ── 1. Global SMS kill-switch ──────────────────────────────────────
        enabled = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("alba_sms.enabled", default="1")
        )
        if enabled == "0":
            return result

        # ── 2. Stage must have a non-empty SMS template ────────────────────
        if not self.collection_stage_id:
            return result
        raw_template = (self.collection_stage_id.sms_template or "").strip()
        if not raw_template:
            return result

        # ── 3. Active provider ─────────────────────────────────────────────
        provider = (
            self.env["alba.sms.provider"]
            .sudo()
            .search([("is_active", "=", True)], limit=1)
        )
        if not provider:
            _logger.info(
                "alba_sms collection_hooks: no active SMS provider found — "
                "skipping collection SMS for loan %s",
                self.loan_number,
            )
            return result

        # ── 4. Resolve phone ───────────────────────────────────────────────
        customer = self.customer_id
        phone = (
            customer.mpesa_number
            or customer.partner_id.mobile
            or customer.partner_id.phone
        )
        if not phone:
            _logger.warning(
                "alba_sms collection_hooks: no phone number found for "
                "customer '%s' — skipping collection SMS for loan %s",
                customer.display_name,
                self.loan_number,
            )
            return result

        # ── 5. Render template ─────────────────────────────────────────────
        context_dict = {
            "amount": str(self.outstanding_balance),
            "days": str(self.days_in_arrears),
            "customer_name": customer.display_name,
            "loan_number": self.loan_number,
            "company_name": self.env.company.name,
        }
        try:
            message = raw_template.format_map(context_dict)
        except KeyError as exc:
            _logger.warning(
                "alba_sms collection_hooks: unknown placeholder %s in "
                "collection stage SMS template for loan %s — using raw template",
                exc,
                self.loan_number,
            )
            message = raw_template

        # ── 6. Send ────────────────────────────────────────────────────────
        provider.send_sms(
            phone,
            message,
            res_model="alba.loan",
            res_id=self.id,
        )

        # ── 7. Log the collection activity ─────────────────────────────────
        log = self.action_log_collection_activity(
            "sms",
            _("SMS reminder sent via %s") % provider.name,
            "successful",
        )

        # ── 8. Mark the log entry as notified ──────────────────────────────
        # action_log_collection_activity() returns the newly created log
        # record; fall back to searching the most-recent entry if the return
        # value is falsy for any reason.
        if not log:
            log = self.env["alba.loan.collection.log"].search(
                [("loan_id", "=", self.id)],
                order="create_date desc",
                limit=1,
            )
        if log:
            log.write(
                {
                    "customer_notified": True,
                    "notification_sent": fields.Datetime.now(),
                }
            )

        return result
