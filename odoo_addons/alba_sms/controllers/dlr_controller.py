# -*- coding: utf-8 -*-
"""
dlr_controller.py — Public webhook endpoint for SMS Delivery Receipts (DLR).

Providers call this endpoint when a message status changes to "delivered"
or "failed".  The controller looks up the log entry by provider_msg_id and
updates its status.

Endpoint: POST /alba/sms/dlr
           POST /alba/sms/dlr/<string:provider_name>

Expected POST body (JSON or form):
  {
    "messageId": "...",   (or "id", "MessageSid", "message_id")
    "status":    "delivered" | "failed" | "success",
    "error":     "optional error description"
  }

No authentication is required for DLR callbacks — providers don't support
HMAC signing consistently.  The controller only updates existing log
records; it cannot create new ones.
"""

import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AlbaSmsDlrController(http.Controller):
    @http.route(
        ["/alba/sms/dlr", "/alba/sms/dlr/<string:provider_name>"],
        auth="public",
        methods=["POST"],
        csrf=False,
        type="http",
    )
    def dlr_webhook(self, provider_name=None, **kwargs):
        try:
            # ── Parse body ────────────────────────────────────────────────
            try:
                data = json.loads(request.httprequest.data)
            except Exception:
                data = kwargs

            # ── Extract message_id ────────────────────────────────────────
            message_id = (
                data.get("messageId")
                or data.get("message_id")
                or data.get("MessageSid")
                or data.get("id")
                or data.get("SMSMessageSid")
            )

            # ── Extract and normalise status ──────────────────────────────
            raw_status = data.get("status") or data.get("Status")
            if raw_status in (
                "delivered",
                "success",
                "DeliveredToTerminal",
                "DeliveredToNetwork",
            ):
                status = "delivered"
            elif raw_status in ("failed", "error", "DeliveryFailed"):
                status = "failed"
            else:
                status = None  # unknown / intermediate — ignore

            # ── Extract optional error description ────────────────────────
            error = (
                data.get("error")
                or data.get("errorMessage")
                or data.get("ErrorMessage")
            )

            # ── Update log record ─────────────────────────────────────────
            if message_id and status:
                SmsLog = request.env["alba.sms.log"].sudo()
                log_record = SmsLog.search(
                    [("provider_msg_id", "=", message_id)], limit=1
                )
                if log_record:
                    if status == "delivered":
                        log_record.mark_delivered()
                    else:
                        log_record.mark_failed(error=error)
                    _logger.info(
                        "Alba SMS DLR [provider=%s]: message_id=%s → status=%s",
                        provider_name or "unknown",
                        message_id,
                        status,
                    )
                else:
                    _logger.info(
                        "Alba SMS DLR [provider=%s]: no log record found for message_id=%s",
                        provider_name or "unknown",
                        message_id,
                    )

        except Exception:
            # Always return 200 so providers do not keep retrying.
            _logger.exception(
                "Alba SMS DLR: unexpected error processing delivery receipt "
                "(provider=%s)",
                provider_name or "unknown",
            )

        return request.make_response(
            json.dumps({"ok": True}),
            headers=[("Content-Type", "application/json")],
        )
