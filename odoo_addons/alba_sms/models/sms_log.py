# -*- coding: utf-8 -*-
"""
alba.sms.log — Append-only audit trail for every outbound SMS.

Mirrors the structure and conventions of alba.webhook.log from the
alba_integration module.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AlbaSmsLog(models.Model):
    _name = "alba.sms.log"
    _description = "Alba SMS Log"
    _rec_name = "display_name"
    _order = "create_date desc, id desc"
    _log_access = True

    # -------------------------------------------------------------------------
    # Core fields
    # -------------------------------------------------------------------------

    display_name = fields.Char(
        string="Display Name",
        compute="_compute_display_name",
        store=True,
    )
    provider_id = fields.Many2one(
        comodel_name="alba.sms.provider",
        string="Provider",
        ondelete="set null",
        index=True,
    )
    template_id = fields.Many2one(
        comodel_name="alba.sms.template",
        string="Template",
        ondelete="set null",
    )
    batch_id = fields.Many2one(
        comodel_name="alba.sms.batch",
        string="Batch",
        ondelete="set null",
        index=True,
    )
    batch_line_id = fields.Many2one(
        comodel_name="alba.sms.batch.line",
        string="Batch Line",
        ondelete="set null",
    )
    phone_number = fields.Char(
        string="Phone Number",
        required=True,
        index=True,
    )
    message = fields.Text(
        string="Message",
    )
    status = fields.Selection(
        selection=[
            ("queued", "Queued"),
            ("sent", "Sent"),
            ("delivered", "Delivered"),
            ("failed", "Failed"),
        ],
        string="Status",
        required=True,
        default="queued",
        index=True,
    )
    provider_msg_id = fields.Char(
        string="Provider Message ID",
        help="External message identifier returned by the SMS provider, "
        "used to match inbound delivery receipts.",
    )
    error_message = fields.Text(
        string="Error Message",
    )
    sent_at = fields.Datetime(
        string="Sent At",
    )
    res_model = fields.Char(
        string="Source Model",
        help="Technical name of the source document model (e.g. alba.loan).",
    )
    res_id = fields.Integer(
        string="Source Record ID",
        help="ID of the source document record.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
    )

    # -------------------------------------------------------------------------
    # Computed / UI-only fields
    # -------------------------------------------------------------------------

    status_badge = fields.Char(
        string="Status Badge",
        compute="_compute_status_badge",
        store=False,
    )
    message_preview = fields.Char(
        string="Message Preview",
        compute="_compute_message_preview",
        store=False,
    )

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------

    _BADGE_MAP = {
        "queued": "badge bg-secondary",
        "sent": "badge bg-primary",
        "delivered": "badge bg-success",
        "failed": "badge bg-danger",
    }

    @api.depends("status", "phone_number", "create_date")
    def _compute_display_name(self):
        for rec in self:
            status_label = (rec.status or "queued").upper()
            phone = rec.phone_number or ""
            if rec.create_date:
                date_str = rec.create_date.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = "—"
            rec.display_name = f"[{status_label}] {phone} @ {date_str}"

    @api.depends("status")
    def _compute_status_badge(self):
        for rec in self:
            rec.status_badge = self._BADGE_MAP.get(
                rec.status or "queued", "badge bg-secondary"
            )

    @api.depends("message")
    def _compute_message_preview(self):
        for rec in self:
            body = rec.message or ""
            if len(body) > 80:
                rec.message_preview = body[:80] + "…"
            else:
                rec.message_preview = body

    # -------------------------------------------------------------------------
    # Action methods
    # -------------------------------------------------------------------------

    def mark_delivered(self, provider_msg_id=None):
        """Mark log entries as delivered.

        Args:
            provider_msg_id (str | None): When provided, also stores the
                external provider message ID for delivery-receipt correlation.
        """
        vals = {"status": "delivered"}
        if provider_msg_id:
            vals["provider_msg_id"] = provider_msg_id
        self.write(vals)

    def mark_failed(self, error):
        """Mark log entries as failed and record the error detail.

        Args:
            error (str): Human-readable error description returned by the
                provider or raised internally.
        """
        self.write(
            {
                "status": "failed",
                "error_message": error,
            }
        )
