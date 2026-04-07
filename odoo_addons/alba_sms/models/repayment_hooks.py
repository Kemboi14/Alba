# -*- coding: utf-8 -*-
"""
repayment_hooks.py — Sends payment confirmation SMS after a repayment is posted.

Overrides action_post() on alba.loan.repayment so that every successfully
posted repayment triggers a "payment_confirmation" SMS to the borrower via
the active alba.sms.provider.

The SMS send is wrapped in a broad try/except so that a gateway outage or
misconfiguration can never roll back an accounting posting.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AlbaLoanRepaymentSmsHook(models.Model):
    _inherit = "alba.loan.repayment"

    # ------------------------------------------------------------------
    # Override
    # ------------------------------------------------------------------

    def action_post(self):
        """Post repayments and, for each successfully posted record, fire a
        payment-confirmation SMS through the active :class:`alba.sms.provider`.

        The super() call handles all accounting logic.  SMS is sent
        *after* the loop so accounting is never blocked by gateway issues.

        Guards (all must pass for SMS to be sent per record):

        1. Record reaches state ``"posted"`` after the super() call.
        2. System parameter ``alba_sms.enabled`` is not ``"0"``.
        3. An active template with code ``"payment_confirmation"`` exists.
        4. At least one :class:`alba.sms.provider` is marked active.
        5. A phone number can be resolved for the borrower.
        """
        result = super().action_post()

        for rec in self:
            # Only process records that are now in the posted state.
            if rec.state != "posted":
                continue

            try:
                # ── 1. Global SMS kill-switch ──────────────────────────────
                enabled = (
                    rec.env["ir.config_parameter"]
                    .sudo()
                    .get_param("alba_sms.enabled", default="1")
                )
                if enabled == "0":
                    continue

                # ── 2. Fetch active payment-confirmation template ───────────
                template = (
                    rec.env["alba.sms.template"]
                    .sudo()
                    .get_by_code("payment_confirmation")
                )
                if not template:
                    _logger.info(
                        "alba_sms repayment_hooks: no active template with "
                        "code 'payment_confirmation' — skipping SMS for "
                        "repayment %s on loan %s",
                        rec.payment_reference or rec.id,
                        rec.loan_id.loan_number if rec.loan_id else "?",
                    )
                    continue

                # ── 3. Active provider ─────────────────────────────────────
                provider = (
                    rec.env["alba.sms.provider"]
                    .sudo()
                    .search([("is_active", "=", True)], limit=1)
                )
                if not provider:
                    _logger.info(
                        "alba_sms repayment_hooks: no active SMS provider "
                        "found — skipping confirmation SMS for repayment %s "
                        "on loan %s",
                        rec.payment_reference or rec.id,
                        rec.loan_id.loan_number if rec.loan_id else "?",
                    )
                    continue

                # ── 4. Resolve phone ───────────────────────────────────────
                customer = rec.loan_id.customer_id
                phone = (
                    customer.mpesa_number
                    or customer.partner_id.mobile
                    or customer.partner_id.phone
                )
                if not phone:
                    _logger.warning(
                        "alba_sms repayment_hooks: no phone number found for "
                        "customer '%s' — skipping confirmation SMS for "
                        "repayment %s on loan %s",
                        customer.display_name,
                        rec.payment_reference or rec.id,
                        rec.loan_id.loan_number,
                    )
                    continue

                # ── 5. Build render context ────────────────────────────────
                context_dict = {
                    "customer_name": customer.display_name,
                    "loan_number": rec.loan_id.loan_number,
                    "amount": "%.2f" % rec.amount_paid,
                    "outstanding_balance": "%.2f" % rec.loan_id.outstanding_balance,
                    "company_name": rec.env.company.name,
                    "due_date": "",
                    "days_overdue": "0",
                    "maturity_date": str(rec.loan_id.maturity_date or ""),
                    "interest_amount": "%.2f" % rec.interest_component,
                }

                # ── 6. Render and send ─────────────────────────────────────
                message = template.render(context_dict)
                provider.send_sms(
                    phone,
                    message,
                    res_model="alba.loan.repayment",
                    res_id=rec.id,
                )

                _logger.info(
                    "alba_sms repayment_hooks: payment confirmation SMS sent "
                    "via '%s' for repayment %s on loan %s to %s",
                    provider.name,
                    rec.payment_reference or rec.id,
                    rec.loan_id.loan_number,
                    phone,
                )

            except Exception:  # noqa: BLE001
                # SMS failure must NEVER roll back a posted repayment.
                _logger.exception(
                    "alba_sms repayment_hooks: unexpected error while sending "
                    "payment confirmation SMS for repayment %s on loan %s — "
                    "repayment is still posted",
                    rec.payment_reference or rec.id,
                    rec.loan_id.loan_number if rec.loan_id else "?",
                )

        return result
