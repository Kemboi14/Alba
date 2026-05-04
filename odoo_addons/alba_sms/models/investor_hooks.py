# -*- coding: utf-8 -*-
"""
investor_hooks.py — SMS hooks for investor-related events.

Hooks into alba.interest.accrual.action_post() to fire an "investor_interest"
SMS to the investor whenever monthly interest is credited to their account.

Zero changes to alba_investors core — purely additive via _inherit.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AlbaInterestAccrualSmsHook(models.Model):
    _inherit = "alba.interest.accrual"

    # ------------------------------------------------------------------
    # Override
    # ------------------------------------------------------------------

    def action_post(self):
        """Post accruals and fire an interest-credited SMS for each one.

        The super() call handles all accounting journal-entry logic.  The SMS
        is sent after super() completes so a gateway failure can never roll
        back a posted accrual.

        Per-record guards (all must pass for SMS to be sent):

        1. System parameter ``alba_sms.enabled`` is not ``"0"``.
        2. An active template with code ``"investor_interest"`` exists.
        3. At least one :class:`alba.sms.provider` with ``is_active=True``.
        4. A phone number can be resolved for the investor
           (``mpesa_number`` → ``partner.mobile`` → ``partner.phone``).
        """
        result = super().action_post()

        for rec in self:
            # Only act on records that are now posted.
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

                # ── 2. Fetch active template ───────────────────────────────
                template = (
                    rec.env["alba.sms.template"].sudo().get_by_code("investor_interest")
                )
                if not template:
                    _logger.info(
                        "alba_sms investor_hooks: no active template with "
                        "code 'investor_interest' — skipping SMS for "
                        "accrual %s",
                        rec.id,
                    )
                    continue

                # 🚀 PHASE 5: Omnichannel (Email - Interest Accrued)
                email_template = rec.env.ref("alba_investors.email_template_interest_accrued", raise_if_not_found=False)
                if email_template and investor.email:
                    email_template.send_mail(rec.id, force_send=False)
                    rec.message_post(body=_("📧 Automated interest email sent to %s") % investor.email)

                # ── 3. Active provider ─────────────────────────────────────

                provider = (
                    rec.env["alba.sms.provider"]
                    .sudo()
                    .search([("is_active", "=", True)], limit=1)
                )
                if not provider:
                    _logger.info(
                        "alba_sms investor_hooks: no active SMS provider "
                        "found — skipping interest SMS for accrual %s",
                        rec.id,
                    )
                    continue

                # ── 4. Resolve phone ───────────────────────────────────────
                investor = rec.investor_id
                phone = (
                    investor.mpesa_number
                    or investor.partner_id.mobile
                    or investor.partner_id.phone
                    or ""
                )
                if not phone:
                    _logger.warning(
                        "alba_sms investor_hooks: no phone number for "
                        "investor '%s' (id=%s) — skipping SMS for accrual %s",
                        investor.partner_id.name,
                        investor.id,
                        rec.id,
                    )
                    continue

                # ── 5. Build render context ────────────────────────────────
                investor_name = investor.partner_id.name or ""
                investment_number = (
                    rec.investment_id.investment_number if rec.investment_id else ""
                )
                context_dict = {
                    # investor-specific
                    "investor_name": investor_name,
                    "investment_number": investment_number,
                    "interest_amount": "%.2f" % rec.interest_amount,
                    # shared aliases used by other templates
                    "customer_name": investor_name,
                    "amount": "%.2f" % rec.interest_amount,
                    "company_name": rec.env.company.name,
                    # loan-centric placeholders filled with safe empty values
                    # so the template engine never raises KeyError
                    "loan_number": "",
                    "outstanding_balance": "0.00",
                    "due_date": "",
                    "days_overdue": "0",
                    "maturity_date": "",
                }

                # ── 6. Render message ──────────────────────────────────────
                # template.render() uses {placeholder} substitution and
                # returns the raw content string on KeyError (never raises).
                message = template.render(context_dict)

                # ── 7. Send via provider ───────────────────────────────────
                # provider.send_sms() writes an alba.sms.log entry and
                # returns (success, msg_id, error_msg) — we just log the
                # result; a failure here must not affect the posted accrual.
                success, msg_id, error_msg = provider.send_sms(
                    phone,
                    message,
                    res_model="alba.interest.accrual",
                    res_id=rec.id,
                    template_id=template.id,
                )

                if success:
                    _logger.info(
                        "alba_sms investor_hooks: interest SMS sent to "
                        "investor '%s' (phone=%s, msg_id=%s, accrual=%s)",
                        investor_name,
                        phone,
                        msg_id,
                        rec.id,
                    )
                else:
                    _logger.warning(
                        "alba_sms investor_hooks: SMS send failed for "
                        "investor '%s' (accrual=%s): %s",
                        investor_name,
                        rec.id,
                        error_msg,
                    )

            except Exception:
                # Catch-all: a bug in the SMS layer must never roll back
                # the interest accrual posting or break upstream callers.
                _logger.exception(
                    "alba_sms investor_hooks: unexpected error while sending "
                    "interest SMS for accrual %s — accrual is still posted",
                    rec.id,
                )

        return result

class AlbaInvestmentStatementSmsHook(models.Model):
    _inherit = "alba.investment.statement"

    def action_send(self):
        res = super(AlbaInvestmentStatementSmsHook, self).action_send()
        for rec in self:
            try:
                rec._send_statement_sms()
            except Exception as e:
                _logger.error("Failed to send statement SMS: %s", str(e))
        return res

    def _send_statement_sms(self):
        """Send SMS when a statement is sent."""
        self.ensure_one()
        enabled = self.env["ir.config_parameter"].sudo().get_param("alba_sms.enabled", default="1")
        if enabled == "0":
            return

        # 1. Resolve Template
        template = self.env["alba.sms.template"].sudo().get_by_code("investor_statement")
        if not template:
            return

        # 2. Resolve Phone
        investor = self.investor_id
        phone = investor.mpesa_number or investor.partner_id.mobile or investor.partner_id.phone
        if not phone:
            return

        # 3. Resolve Provider
        provider = self.env["alba.sms.provider"].sudo().search([("is_active", "=", True)], limit=1)
        if not provider:
            return

        # 4. Render and Send
        ctx = {
            "investor_name": investor.partner_id.name,
            "period": "%s to %s" % (self.period_start, self.period_end),
            "amount": "%.2f" % self.closing_balance,
            "currency": self.currency_id.name,
            "company_name": self.env.company.name,
        }
        
        message = template.render(ctx)
        
        provider.send_sms(
            phone,
            message,
            res_model="alba.investment.statement",
            res_id=self.id,
            template_id=template.id,
        )
        
        self.message_post(body=_("<b>Automated SMS Sent</b>: %s") % message)
