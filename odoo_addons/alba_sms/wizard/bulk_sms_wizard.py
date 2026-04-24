# -*- coding: utf-8 -*-
"""
bulk_sms_wizard.py — Manual bulk SMS launcher.

Can be launched from:
  * Any alba.loan list view (via action button)
  * Any alba.investor list view
  * Any alba.customer list view

Staff select a template, provider, and optionally edit the message
per-recipient.  Preview is shown before send.

Usage (server action bound to, e.g., alba.loan):
    context key ``active_ids`` supplies the selected record IDs and
    ``active_model`` supplies the model name.  Alternatively, set
    ``res_model`` and ``res_ids`` (JSON) directly on the wizard record.
"""

import json
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AlbaSmsWizard(models.TransientModel):
    _name = "alba.sms.wizard"
    _description = "Send Bulk SMS Wizard"

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    template_id = fields.Many2one(
        "alba.sms.template",
        string="Template",
        domain="[('is_active','=',True)]",
    )
    provider_id = fields.Many2one(
        "alba.sms.provider",
        string="Provider",
        required=True,
        domain="[('is_active','=',True)]",
    )
    custom_message = fields.Text(
        string="Custom Message (leave blank to use template)",
        help=(
            "If provided this text is sent instead of the selected template. "
            "Standard {placeholder} substitution still applies."
        ),
    )
    res_model = fields.Char(
        string="Source Model",
        help="Technical name of the model whose records are being targeted.",
    )
    res_ids = fields.Text(
        string="Record IDs (JSON)",
        help="JSON-encoded list of integer record IDs, e.g. [1, 2, 3].",
    )
    preview_line_ids = fields.One2many(
        "alba.sms.wizard.line",
        "wizard_id",
        string="Preview",
    )

    # ------------------------------------------------------------------
    # Private helpers — phone resolution
    # ------------------------------------------------------------------

    def _resolve_phone(self, record):
        """Return the best available phone number for *record*.

        Preference order mirrors :meth:`AlbaSmsBatch._resolve_phone`:
        ``mpesa_number`` → partner ``mobile`` → partner ``phone``.

        :param record: a single Odoo record (alba.loan, alba.investor,
                       or alba.customer).
        :returns: phone string, or ``False`` when none is found.
        :rtype: str | bool
        """
        model = record._name
        phone = False

        if model == "alba.loan":
            customer = record.customer_id
            if customer:
                phone = (
                    getattr(customer, "mpesa_number", False)
                    or (customer.partner_id and customer.partner_id.mobile)
                    or (customer.partner_id and customer.partner_id.phone)
                )
        elif model == "alba.investor":
            phone = (
                getattr(record, "mpesa_number", False)
                or (record.partner_id and record.partner_id.mobile)
                or (record.partner_id and record.partner_id.phone)
            )
        elif model == "alba.customer":
            phone = getattr(record, "mpesa_number", False) or (
                record.partner_id and record.partner_id.mobile
            )
        elif model == "alba.loan.application":
            customer = record.customer_id
            if customer:
                phone = (
                    getattr(customer, "mpesa_number", False)
                    or (customer.partner_id and customer.partner_id.mobile)
                    or (customer.partner_id and customer.partner_id.phone)
                )

        return phone or False

    # ------------------------------------------------------------------
    # Private helpers — message context / rendering
    # ------------------------------------------------------------------

    def _build_context(self, record):
        """Return a placeholder substitution dict for *record*.

        Mirrors :meth:`AlbaSmsBatch._build_sms_context` so the same
        template tokens work across batch campaigns and ad-hoc sends.

        :param record: a single Odoo record.
        :returns: dict of placeholder → value.
        :rtype: dict
        """
        ctx = {
            "company_name": self.env.company.name,
        }
        model = record._name

        if model == "alba.loan":
            ctx.update(
                {
                    "loan_number": getattr(record, "name", "") or "",
                    "customer_name": (
                        record.customer_id.partner_id.name
                        if record.customer_id and record.customer_id.partner_id
                        else ""
                    ),
                    "amount": getattr(record, "outstanding_balance", 0.0),
                    "days_overdue": getattr(record, "days_in_arrears", 0),
                    "outstanding_balance": getattr(record, "outstanding_balance", 0.0),
                    "maturity_date": getattr(record, "maturity_date", False) or "",
                    "due_date": "",
                }
            )

        elif model == "alba.customer":
            ctx.update(
                {
                    "customer_name": (
                        record.partner_id.name
                        if record.partner_id
                        else getattr(record, "name", "")
                    ),
                }
            )

        elif model == "alba.investor":
            ctx.update(
                {
                    "investor_name": (
                        record.partner_id.name
                        if record.partner_id
                        else getattr(record, "name", "")
                    ),
                    "investment_number": getattr(record, "name", "") or "",
                    "interest_amount": getattr(record, "interest_amount", 0.0),
                }
            )

        elif model == "alba.loan.application":
            ctx.update(
                {
                    "loan_number": getattr(record, "application_number", "") or "",
                    "customer_name": (
                        record.customer_id.partner_id.name
                        if record.customer_id and record.customer_id.partner_id
                        else ""
                    ),
                    "amount": getattr(record, "approved_amount", 0.0)
                    or getattr(record, "requested_amount", 0.0),
                }
            )

        return ctx

    def _render_message_for(self, record):
        """Render the outbound message body for a single *record*.

        If :attr:`custom_message` is set it is used as the template body;
        otherwise :attr:`template_id`'s content is used.  In either case
        ``{placeholder}`` substitution is performed using
        :meth:`_build_context`.

        :param record: a single Odoo record.
        :returns: rendered message string.
        :rtype: str
        """
        self.ensure_one()
        ctx = self._build_context(record)

        if self.custom_message:
            body = self.custom_message
            try:
                return body.format_map(ctx)
            except (KeyError, ValueError) as exc:
                _logger.warning(
                    "alba.sms.wizard: custom_message placeholder error for "
                    "%s(%s): %s — returning raw body",
                    record._name,
                    record.id,
                    exc,
                )
                return body

        if self.template_id:
            # Delegate to the template's own render() so warning/fallback
            # logic lives in one place.
            return self.template_id.render(ctx)

        return ""

    def _get_recipient_name(self, record):
        """Return a human-readable label for *record* for the preview grid.

        :param record: a single Odoo record.
        :returns: display label string.
        :rtype: str
        """
        model = record._name

        if model == "alba.loan":
            customer = record.customer_id
            customer_name = ""
            if customer:
                customer_name = (
                    customer.partner_id.name
                    if customer.partner_id
                    else getattr(customer, "name", "")
                )
            loan_name = getattr(record, "name", "") or ""
            if loan_name:
                return f"{customer_name} ({loan_name})" if customer_name else loan_name
            return customer_name

        if model in ("alba.investor", "alba.customer"):
            return (
                record.partner_id.name
                if record.partner_id
                else getattr(record, "name", str(record.id))
            )

        return getattr(record, "name", str(record.id))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_preview(self):
        """Resolve phones and render messages; populate :attr:`preview_line_ids`.

        Reads the target model and record IDs from :attr:`res_model` /
        :attr:`res_ids`, falling back to ``active_model`` / ``active_ids``
        in the wizard context (set automatically when launched from a list
        view via a server action).

        Clears any previously generated preview lines before re-building
        them so the method is idempotent.

        :returns: act_window action that re-opens this wizard form so the
                  caller can inspect the preview before clicking *Send*.
        :rtype: dict
        :raises UserError: when no source model, no IDs, or no message
                           source (template or custom text) is available.
        """
        self.ensure_one()

        # ── Determine source model ────────────────────────────────────────
        res_model = self.res_model or self.env.context.get("active_model") or ""
        if not res_model:
            raise UserError(
                _(
                    "No source model is set. "
                    "Launch this wizard from a list view (e.g. Loans, Investors)."
                )
            )

        # ── Determine record IDs ──────────────────────────────────────────
        if self.res_ids:
            try:
                record_ids = json.loads(self.res_ids)
            except (json.JSONDecodeError, TypeError) as exc:
                raise UserError(
                    _("Invalid JSON in Record IDs field: %s") % exc
                ) from exc
        else:
            record_ids = self.env.context.get("active_ids") or []

        if not record_ids:
            raise UserError(
                _(
                    "No records are selected. "
                    "Please select one or more records from the list view."
                )
            )

        # ── Validate message source ───────────────────────────────────────
        if not self.template_id and not self.custom_message:
            raise UserError(
                _(
                    "Please select a template or enter a custom message before previewing."
                )
            )

        # ── Clear existing lines ──────────────────────────────────────────
        self.preview_line_ids.unlink()

        # ── Build preview lines ───────────────────────────────────────────
        records = self.env[res_model].browse(record_ids)
        line_vals = []

        for record in records:
            phone = self._resolve_phone(record)
            message = self._render_message_for(record)
            recipient = self._get_recipient_name(record)

            line_vals.append(
                {
                    "wizard_id": self.id,
                    "recipient_name": recipient,
                    "phone_number": phone or "",
                    "message": message,
                    "res_id": record.id,
                    # Only pre-tick "send" when a valid phone was found
                    "send": bool(phone),
                }
            )

        if line_vals:
            self.env["alba.sms.wizard.line"].create(line_vals)

        # ── Re-open this wizard so the preview tab is visible ─────────────
        return {
            "type": "ir.actions.act_window",
            "res_model": "alba.sms.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_send(self):
        """Send SMS to every checked preview line that has a phone number.

        Iterates :attr:`preview_line_ids`, skipping lines where
        :attr:`~AlbaSmsWizardLine.send` is ``False`` or
        :attr:`~AlbaSmsWizardLine.phone_number` is empty.

        Each dispatch is delegated to :meth:`AlbaSmsProvider.send_sms` which
        handles phone normalisation, HTTP dispatch, and audit logging.

        :returns: client notification action that closes the wizard dialog
                  after reporting how many messages were sent / failed.
        :rtype: dict
        :raises UserError: when no provider is selected or no lines are
                           eligible for sending.
        """
        self.ensure_one()

        if not self.provider_id:
            raise UserError(_("Please select an SMS provider before sending."))

        lines_to_send = self.preview_line_ids.filtered(
            lambda line: line.send and line.phone_number
        )

        if not lines_to_send:
            raise UserError(
                _(
                    "No lines are checked for sending, or none of the selected "
                    "records have a resolvable phone number."
                )
            )

        sent = 0
        failed = 0
        template_id = self.template_id.id if self.template_id else False

        for line in lines_to_send:
            success, _msg_id, _err = self.provider_id.send_sms(
                line.phone_number,
                line.message,
                res_model=self.res_model or "",
                res_id=line.res_id or 0,
                template_id=template_id,
            )
            if success:
                sent += 1
            else:
                failed += 1

        # ── Build notification ────────────────────────────────────────────
        if failed == 0:
            notif_type = "success"
            title = _("SMS Sent")
            message = _("%d message(s) dispatched successfully.") % sent
        elif sent == 0:
            notif_type = "danger"
            title = _("SMS Failed")
            message = _("All %d message(s) failed to send.") % failed
        else:
            notif_type = "warning"
            title = _("SMS Partially Sent")
            message = _("%d sent, %d failed.") % (sent, failed)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "sticky": failed > 0,
                "type": notif_type,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }


class AlbaSmsWizardLine(models.TransientModel):
    _name = "alba.sms.wizard.line"
    _description = "Bulk SMS Wizard Line"
    _rec_name = "recipient_name"
    _order = "id"

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    wizard_id = fields.Many2one(
        "alba.sms.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
        index=True,
    )
    # NOTE: Odoo reserves the computed field name ``display_name`` on every
    # model.  We use ``recipient_name`` (labelled "Recipient" in views) to
    # hold the human-readable label without conflicting with the ORM.
    recipient_name = fields.Char(
        string="Recipient",
    )
    phone_number = fields.Char(
        string="Phone Number",
    )
    message = fields.Text(
        string="Message",
    )
    res_id = fields.Integer(
        string="Record ID",
    )
    send = fields.Boolean(
        string="Send",
        default=True,
        help=(
            "Uncheck to exclude this recipient from the current dispatch. "
            "Lines without a phone number are unchecked automatically."
        ),
    )
