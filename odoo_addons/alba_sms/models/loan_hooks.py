# -*- coding: utf-8 -*-
"""
loan_hooks.py — Extends alba.loan to fire SMS notifications.

All hooks call super() first then add SMS.  Zero changes to alba_loans core.
"""

import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# ir.config_parameter key to toggle SMS on/off globally
_PARAM_SMS_ENABLED = "alba_sms.enabled"


class AlbaLoanSmsHook(models.Model):
    _inherit = "alba.loan"

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _sms_enabled(self):
        """Return True when SMS sending is globally enabled.

        Reads the ``alba_sms.enabled`` system parameter.  Any value other
        than the string ``"1"`` (or the parameter being absent entirely)
        is treated as disabled so that a fresh install is safe by default.
        """
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(_PARAM_SMS_ENABLED, default="0")
        )
        return value == "1"

    # ------------------------------------------------------------------
    # Cron override — overdue alerts
    # ------------------------------------------------------------------

    @api.model
    def cron_send_overdue_alerts(self):
        """Extend the parent overdue-alert cron to also send SMS.

        The parent chatter logic runs unconditionally via ``super()``.
        The SMS block is wrapped in a broad ``try/except`` so any failure
        (bad phone number, gateway timeout, misconfigured template, …)
        cannot prevent the parent job from being marked as completed.
        """
        # 1. Always run the parent job first.
        super().cron_send_overdue_alerts()

        # 2. Guard: feature flag.
        if not self._sms_enabled():
            _logger.debug(
                "cron_send_overdue_alerts SMS: skipped — %s is not '1'.",
                _PARAM_SMS_ENABLED,
            )
            return

        try:
            self._send_overdue_sms()
        except Exception:  # noqa: BLE001
            _logger.exception(
                "cron_send_overdue_alerts SMS: unexpected error in SMS block — "
                "parent cron completed successfully."
            )

    @api.model
    def _send_overdue_sms(self):
        """Inner implementation for overdue SMS so the guard wrapper stays clean."""

        # 3. Resolve active provider.
        provider = (
            self.env["alba.sms.provider"]
            .sudo()
            .search([("is_active", "=", True)], limit=1)
        )
        if not provider:
            _logger.warning(
                "cron_send_overdue_alerts SMS: no active alba.sms.provider found — "
                "skipping SMS notifications."
            )
            return

        # 4. Resolve template.
        template = (
            self.env["alba.sms.template"].sudo().get_by_code("loan_overdue_reminder")
        )
        if not template:
            _logger.warning(
                "cron_send_overdue_alerts SMS: template 'loan_overdue_reminder' "
                "not found or inactive — skipping SMS notifications."
            )
            return

        today = fields.Date.today()
        alert_days = [1, 3, 7, 14, 30]
        sent_count = 0

        for days_overdue in alert_days:
            target_date = today - timedelta(days=days_overdue)
            overdue_schedules = self.env["alba.repayment.schedule"].search(
                [
                    ("due_date", "=", target_date),
                    ("balance_due", ">", 0),
                    ("loan_id.state", "in", ("active", "npl")),
                ]
            )

            for schedule in overdue_schedules:
                loan = schedule.loan_id

                # 5. Resolve phone number.
                customer = loan.customer_id
                phone = (
                    customer.mpesa_number
                    or customer.partner_id.mobile
                    or customer.partner_id.phone
                )
                if not phone:
                    _logger.debug(
                        "cron_send_overdue_alerts SMS: loan %s — no phone for "
                        "customer %s, skipping.",
                        loan.name,
                        customer.display_name,
                    )
                    continue

                # 6. Build render context.
                ctx = {
                    "customer_name": customer.display_name,
                    "loan_number": loan.name,
                    "amount": "%.2f" % schedule.balance_due,
                    "days_overdue": str(days_overdue),
                    "outstanding_balance": "%.2f" % loan.outstanding_balance,
                    "due_date": str(schedule.due_date),
                    "company_name": self.env.company.name,
                    "maturity_date": str(loan.maturity_date or ""),
                    "interest_amount": "0.00",
                }

                # 7. Render message.
                message = template.render(ctx)

                # 8. Send.
                success, msg_id, error = provider.send_sms(
                    phone,
                    message,
                    res_model="alba.loan",
                    res_id=loan.id,
                    template_id=template.id,
                )
                _logger.debug(
                    "cron_send_overdue_alerts SMS: loan %s | phone %s | "
                    "days_overdue %d | success=%s | msg_id=%s | error=%s",
                    loan.name,
                    phone,
                    days_overdue,
                    success,
                    msg_id,
                    error,
                )
                if success:
                    sent_count += 1

        _logger.info(
            "cron_send_overdue_alerts SMS: %d SMS message(s) dispatched.", sent_count
        )

    # ------------------------------------------------------------------
    # Cron override — maturity reminders
    # ------------------------------------------------------------------

    @api.model
    def cron_send_maturity_reminders(self):
        """Extend the parent maturity-reminder cron to also send SMS.

        The parent chatter logic runs unconditionally via ``super()``.
        The SMS block is wrapped in a broad ``try/except`` so any failure
        cannot prevent the parent job from being marked as completed.
        """
        # 1. Always run the parent job first.
        super().cron_send_maturity_reminders()

        # 2. Guard: feature flag.
        if not self._sms_enabled():
            _logger.debug(
                "cron_send_maturity_reminders SMS: skipped — %s is not '1'.",
                _PARAM_SMS_ENABLED,
            )
            return

        try:
            self._send_maturity_sms()
        except Exception:  # noqa: BLE001
            _logger.exception(
                "cron_send_maturity_reminders SMS: unexpected error in SMS block — "
                "parent cron completed successfully."
            )

    @api.model
    def _send_maturity_sms(self):
        """Inner implementation for maturity SMS so the guard wrapper stays clean."""

        # 3. Resolve active provider.
        provider = (
            self.env["alba.sms.provider"]
            .sudo()
            .search([("is_active", "=", True)], limit=1)
        )
        if not provider:
            _logger.warning(
                "cron_send_maturity_reminders SMS: no active alba.sms.provider "
                "found — skipping SMS notifications."
            )
            return

        # 4. Resolve template.
        template = self.env["alba.sms.template"].sudo().get_by_code("maturity_reminder")
        if not template:
            _logger.warning(
                "cron_send_maturity_reminders SMS: template 'maturity_reminder' "
                "not found or inactive — skipping SMS notifications."
            )
            return

        today = fields.Date.today()
        window_end = today + timedelta(days=30)

        maturing = self.search(
            [
                ("state", "=", "active"),
                ("maturity_date", ">=", today),
                ("maturity_date", "<=", window_end),
                ("outstanding_balance", ">", 0),
            ]
        )

        sent_count = 0

        for loan in maturing:
            # 5. Resolve phone number.
            customer = loan.customer_id
            phone = (
                customer.mpesa_number
                or customer.partner_id.mobile
                or customer.partner_id.phone
            )
            if not phone:
                _logger.debug(
                    "cron_send_maturity_reminders SMS: loan %s — no phone for "
                    "customer %s, skipping.",
                    loan.name,
                    customer.display_name,
                )
                continue

            # 6. Build render context.
            days_left = (loan.maturity_date - today).days
            ctx = {
                "customer_name": customer.display_name,
                "loan_number": loan.name,
                "amount": "%.2f" % loan.outstanding_balance,
                "days_left": str(days_left),
                "outstanding_balance": "%.2f" % loan.outstanding_balance,
                "maturity_date": str(loan.maturity_date or ""),
                "due_date": str(loan.maturity_date or ""),
                "company_name": self.env.company.name,
                "interest_amount": "0.00",
            }

            # 7. Render message.
            message = template.render(ctx)

            # 8. Send.
            success, msg_id, error = provider.send_sms(
                phone,
                message,
                res_model="alba.loan",
                res_id=loan.id,
                template_id=template.id,
            )
            _logger.debug(
                "cron_send_maturity_reminders SMS: loan %s | phone %s | "
                "days_left %d | success=%s | msg_id=%s | error=%s",
                loan.name,
                phone,
                days_left,
                success,
                msg_id,
                error,
            )
            if success:
                sent_count += 1

        _logger.info(
            "cron_send_maturity_reminders SMS: %d SMS message(s) dispatched.",
            sent_count,
        )
