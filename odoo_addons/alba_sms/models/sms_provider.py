# -*- coding: utf-8 -*-
"""
alba.sms.provider — SMS gateway adapter.

Supports Africa's Talking, Twilio, Vonage/Nexmo and any generic HTTP-based
provider.  Credentials are stored here and exposed only to SMS admins.
Phone normalisation is a copy of the logic from alba_loans/models/mpesa_config.py
(normalise Kenyan numbers to 254XXXXXXXXX).
"""

import json
import logging
import time

import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AlbaSmsProvider(models.Model):
    _name = "alba.sms.provider"
    _description = "SMS Provider / Gateway"
    _order = "name"

    # ------------------------------------------------------------------ #
    #  Basic identification                                                #
    # ------------------------------------------------------------------ #

    name = fields.Char(
        string="Provider Name",
        required=True,
    )
    provider_type = fields.Selection(
        selection=[
            ("africa_talking", "Africa's Talking"),
            ("twilio", "Twilio"),
            ("vonage", "Vonage / Nexmo"),
            ("onfon", "OnfonMedia"),
            ("generic_http", "Generic HTTP"),
        ],
        string="Provider Type",
        required=True,
        default="africa_talking",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    is_active = fields.Boolean(
        string="Active",
        default=True,
    )

    # ------------------------------------------------------------------ #
    #  Connection / credentials                                            #
    # ------------------------------------------------------------------ #

    api_url = fields.Char(
        string="API Endpoint URL",
        required=True,
        help="Full URL of the SMS gateway endpoint.",
    )
    api_key = fields.Char(
        string="API Key",
        groups="alba_sms.group_sms_admin",
        help="API key, token, or Account SID depending on the provider.",
    )
    api_secret = fields.Char(
        string="API Secret",
        groups="alba_sms.group_sms_admin",
        help="API secret or Auth Token depending on the provider.",
    )
    username = fields.Char(
        string="Username",
        help="Username (required for Africa's Talking).",
    )
    sender_id = fields.Char(
        string="Sender ID / Short Code",
        required=True,
        help="The originating phone number or short-code used as sender.",
    )

    # ------------------------------------------------------------------ #
    #  Generic HTTP auth / parameter mapping                               #
    # ------------------------------------------------------------------ #

    auth_type = fields.Selection(
        selection=[
            ("header", "API Key in Header"),
            ("query_param", "API Key as Query Param"),
            ("basic_auth", "HTTP Basic Auth"),
        ],
        string="Auth Type",
        default="header",
        help="How credentials are transmitted for Generic HTTP providers.",
    )
    auth_header_name = fields.Char(
        string="Auth Header / Param Name",
        default="apiKey",
        help=(
            "Header name when auth_type='header', or query-param name "
            "when auth_type='query_param'."
        ),
    )
    phone_param_name = fields.Char(
        string="Phone Parameter Name",
        default="to",
        help="Query / body parameter that carries the destination number.",
    )
    message_param_name = fields.Char(
        string="Message Parameter Name",
        default="message",
        help="Query / body parameter that carries the SMS text.",
    )
    extra_params = fields.Text(
        string="Extra Params (JSON)",
        help=(
            "Provider-specific extra key/value pairs serialised as a JSON "
            'object, e.g. {"channel": "sms", "type": "plain"}.'
        ),
    )

    # ------------------------------------------------------------------ #
    #  Operational settings                                                #
    # ------------------------------------------------------------------ #

    timeout_s = fields.Integer(
        string="Request Timeout (s)",
        default=30,
        help="HTTP request timeout in seconds.",
    )

    # ------------------------------------------------------------------ #
    #  Computed / relational                                               #
    # ------------------------------------------------------------------ #

    log_count = fields.Integer(
        string="Log Entries",
        compute="_compute_log_count",
    )

    # ------------------------------------------------------------------ #
    #  SQL constraints                                                     #
    # ------------------------------------------------------------------ #

    _unique_name_per_company = models.Constraint(
        "UNIQUE(name, company_id)",
        "A provider with this name already exists for the selected company.",
    )

    # ------------------------------------------------------------------ #
    #  Compute helpers                                                     #
    # ------------------------------------------------------------------ #

    @api.depends()
    def _compute_log_count(self):
        """Count alba.sms.log records linked to each provider."""
        SmsLog = self.env["alba.sms.log"].sudo()
        for rec in self:
            rec.log_count = SmsLog.search_count([("provider_id", "=", rec.id)])

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def send_sms(
        self,
        phone,
        message,
        res_model="",
        res_id=0,
        template_id=False,
        batch_line_id=False,
    ):
        """Send a single SMS through this provider.

        Args:
            phone (str): Destination phone number (will be normalised).
            message (str): SMS body text.
            res_model (str): Optional originating model name for the log.
            res_id (int): Optional originating record ID for the log.
            template_id (int|False): Optional alba.sms.template ID.
            batch_line_id (int|False): Optional alba.sms.batch.line ID.

        Returns:
            tuple[bool, str, str]: (success, provider_msg_id, error_msg)
                - success: True when the gateway accepted the message.
                - provider_msg_id: Message ID returned by the gateway, or "".
                - error_msg: Human-readable error string, or None on success.
        """
        self.ensure_one()

        # ---- normalise phone -------------------------------------------
        try:
            phone = self._normalise_phone(phone)
        except UserError as exc:
            error_msg = str(exc.args[0]) if exc.args else str(exc)
            self._write_log(
                phone=phone,
                message=message,
                status="failed",
                provider_msg_id="",
                error_msg=error_msg,
                res_model=res_model,
                res_id=res_id,
                template_id=template_id,
                batch_line_id=batch_line_id,
            )
            return False, "", error_msg

        # ---- build request ---------------------------------------------
        payload, headers = self._build_request(phone, message)

        # For Twilio, requests Basic Auth tuple is needed
        auth = None
        if self.provider_type == "twilio":
            auth = (self.api_key or "", self.api_secret or "")

        # ---- fire request ----------------------------------------------
        t_start = time.monotonic()
        try:
            response = requests.post(
                self.api_url,
                data=payload if self.provider_type in ("twilio",) else None,
                json=payload if self.provider_type not in ("twilio",) else None,
                headers=headers,
                auth=auth,
                timeout=self.timeout_s,
            )
            elapsed = time.monotonic() - t_start
            _logger.debug(
                "alba.sms.provider [%s] response %s in %.2fs: %s",
                self.name,
                response.status_code,
                elapsed,
                response.text[:500],
            )
            response.raise_for_status()

            try:
                resp_json = response.json()
            except ValueError:
                resp_json = {}

            provider_msg_id = self._extract_message_id(resp_json)
            self._write_log(
                phone=phone,
                message=message,
                status="sent",
                provider_msg_id=provider_msg_id,
                error_msg="",
                res_model=res_model,
                res_id=res_id,
                template_id=template_id,
                batch_line_id=batch_line_id,
            )
            return True, provider_msg_id, None

        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            _logger.exception(
                "alba.sms.provider [%s] failed to send SMS to %s",
                self.name,
                phone,
            )
            self._write_log(
                phone=phone,
                message=message,
                status="failed",
                provider_msg_id="",
                error_msg=error_msg,
                res_model=res_model,
                res_id=res_id,
                template_id=template_id,
                batch_line_id=batch_line_id,
            )
            return False, "", error_msg

    # ------------------------------------------------------------------ #
    #  Request builder                                                     #
    # ------------------------------------------------------------------ #

    def _build_request(self, phone, message):
        """Build the HTTP payload and headers for this provider.

        Args:
            phone (str): Already-normalised destination number.
            message (str): SMS body text.

        Returns:
            tuple[dict, dict]: (payload, headers)
        """
        self.ensure_one()

        # Parse optional extras
        extra = {}
        if self.extra_params:
            try:
                extra = json.loads(self.extra_params)
                if not isinstance(extra, dict):
                    extra = {}
            except (json.JSONDecodeError, TypeError):
                _logger.warning(
                    "alba.sms.provider [%s]: extra_params is not valid JSON; ignoring.",
                    self.name,
                )
                extra = {}

        if self.provider_type == "africa_talking":
            payload = {
                "username": self.username or "",
                "to": phone,
                "message": message,
                "from": self.sender_id or "",
                **extra,
            }
            headers = {
                "apiKey": self.api_key or "",
                "Accept": "application/json",
            }

        elif self.provider_type == "onfon":
            # OnfonMedia BulkSMS API
            # Accesskey sent as header (= username field)
            # ApiKey + ClientId sent in JSON body
            payload = {
                "SenderId": self.sender_id or "",
                "MessageParameters": [
                    {
                        "Number": phone,
                        "Text": message,
                    }
                ],
                "ApiKey": self.api_key or "",
                "ClientId": self.username or "",
            }
            headers = {
                "AccessKey": self.username or "",
                "Content-Type": "application/json",
            }

        elif self.provider_type == "twilio":
            # Twilio uses form-encoded POST; auth is Basic Auth (SID:Token).
            payload = {
                "To": phone,
                "From": self.sender_id or "",
                "Body": message,
                **extra,
            }
            # The auth tuple is handled by the caller (send_sms).
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
            }

        elif self.provider_type == "vonage":
            payload = {
                "api_key": self.api_key or "",
                "api_secret": self.api_secret or "",
                "to": phone,
                "from": self.sender_id or "",
                "text": message,
                **extra,
            }
            headers = {
                "Content-Type": "application/json",
            }

        else:
            # Generic HTTP — fully configurable
            payload = {
                self.phone_param_name or "to": phone,
                self.message_param_name or "message": message,
                **extra,
            }

            if self.auth_type == "header":
                headers = {
                    self.auth_header_name or "apiKey": self.api_key or "",
                }
            elif self.auth_type == "query_param":
                payload[self.auth_header_name or "apiKey"] = self.api_key or ""
                headers = {}
            else:
                # basic_auth — caller must pass the auth tuple separately
                headers = {}

        return payload, headers

    # ------------------------------------------------------------------ #
    #  Response parsing helper                                             #
    # ------------------------------------------------------------------ #

    def _extract_message_id(self, response_json):
        """Extract the provider's message ID from a parsed JSON response.

        Tries a variety of common key names used by different gateways.

        Args:
            response_json (dict): Parsed JSON body of the gateway response.

        Returns:
            str: Best-effort message ID, or "" if none can be found.
        """
        if not isinstance(response_json, dict):
            return ""

        # Africa's Talking nested structure
        at_recipients = response_json.get("SMSMessageData", {}).get("Recipients", [{}])
        if at_recipients and isinstance(at_recipients, list):
            at_id = at_recipients[0].get("messageId", "")
            if at_id:
                return str(at_id)

        # OnfonMedia: {"ErrorCode":"0","Data":{"MessageId":"xxx",...}}
        onfon_data = response_json.get("Data", {})
        if isinstance(onfon_data, dict):
            onfon_id = onfon_data.get("MessageId", "")
            if onfon_id:
                return str(onfon_id)

        # Common flat keys (tried in order of preference)
        for key in ("messageId", "message_id", "MessageSid", "sid", "SMSMessageSid"):
            value = response_json.get(key)
            if value:
                return str(value)

        # Last-resort fallback
        return str(response_json.get("id", ""))

    # ------------------------------------------------------------------ #
    #  Phone normalisation                                                 #
    # ------------------------------------------------------------------ #

    def _normalise_phone(self, raw):
        """Normalise a Kenyan phone number to the 254XXXXXXXXX format.

        Accepted input formats:
          • ``0712345678``    → ``254712345678``
          • ``+254712345678`` → ``254712345678``
          • ``254712345678``  → ``254712345678``  (no-op)
          • ``712345678``     → ``254712345678``

        Args:
            raw (str): Raw phone number (spaces and hyphens are stripped).

        Returns:
            str: Normalised 12-digit number, or "" if raw is empty/falsy.

        Raises:
            UserError: When the result does not look like a valid Kenyan number.
        """
        if not raw:
            # Let the caller decide what to do with an empty destination.
            return ""

        phone = raw.strip().replace(" ", "").replace("-", "")

        if phone.startswith("+"):
            phone = phone[1:]

        if phone.startswith("0") and len(phone) == 10:
            # 0XXXXXXXXX → 254XXXXXXXXX
            phone = "254" + phone[1:]
        elif len(phone) == 9 and not phone.startswith("254"):
            # 9-digit local → 254XXXXXXXXX
            phone = "254" + phone

        if not phone.isdigit() or len(phone) != 12 or not phone.startswith("254"):
            raise UserError(
                _(
                    "Invalid phone number '%(raw)s'. "
                    "Please use the format 0712345678 or 254712345678."
                )
                % {"raw": raw}
            )
        return phone

    # ------------------------------------------------------------------ #
    #  Action helpers                                                      #
    # ------------------------------------------------------------------ #

    def action_test_connection(self):
        """Validate provider configuration and return a display notification.

        Checks that the minimum required fields (api_url, api_key, sender_id)
        are populated.  Does *not* send a live SMS so that no costs are
        incurred during a simple connectivity check.

        Returns:
            dict: An ``ir.actions.client`` notification action.
        """
        self.ensure_one()

        missing = []
        if not self.api_url:
            missing.append(_("API Endpoint URL"))
        if not self.api_key:
            missing.append(_("API Key"))
        if not self.sender_id:
            missing.append(_("Sender ID / Short Code"))

        if missing:
            message = _(
                "Provider '%(name)s' is missing required field(s): %(fields)s."
            ) % {
                "name": self.name,
                "fields": ", ".join(missing),
            }
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Configuration Incomplete"),
                    "message": message,
                    "type": "warning",
                    "sticky": False,
                },
            }

        # Optional: try a lightweight GET/HEAD to check reachability
        try:
            probe = requests.head(self.api_url, timeout=self.timeout_s)
            reachable = True
            status_code = probe.status_code
        except Exception as exc:  # noqa: BLE001
            reachable = False
            status_code = None
            _logger.info(
                "alba.sms.provider [%s] connectivity probe failed: %s",
                self.name,
                exc,
            )

        if reachable:
            message = _(
                "Provider '%(name)s' configuration looks good "
                "(endpoint returned HTTP %(code)s)."
            ) % {"name": self.name, "code": status_code}
            notif_type = "success"
            title = _("Connection OK")
        else:
            message = _(
                "Provider '%(name)s' configuration is set but the endpoint "
                "could not be reached.  Check the API URL and network access."
            ) % {"name": self.name}
            notif_type = "warning"
            title = _("Endpoint Unreachable")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": notif_type,
                "sticky": False,
            },
        }

    def action_view_logs(self):
        """Open a filtered list view of SMS logs for this provider.

        Returns:
            dict: An ``ir.actions.act_window`` action.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("SMS Logs — %s") % self.name,
            "res_model": "alba.sms.log",
            "view_mode": "list,form",
            "domain": [("provider_id", "=", self.id)],
            "context": {
                "default_provider_id": self.id,
                "search_default_provider_id": self.id,
            },
        }

    # ------------------------------------------------------------------ #
    #  Internal log writer                                                 #
    # ------------------------------------------------------------------ #

    def _write_log(
        self,
        phone,
        message,
        status,
        provider_msg_id="",
        error_msg="",
        res_model="",
        res_id=0,
        template_id=False,
        batch_line_id=False,
    ):
        """Create an alba.sms.log record (always via sudo so that portal /
        low-privilege users sending scheduled messages can still write logs).

        Args:
            phone (str): Destination number.
            message (str): SMS body.
            status (str): "sent" or "failed".
            provider_msg_id (str): ID returned by the gateway.
            error_msg (str): Error description (empty on success).
            res_model (str): Source model for traceability.
            res_id (int): Source record ID.
            template_id (int|False): alba.sms.template ID.
            batch_line_id (int|False): alba.sms.batch.line ID.
        """
        vals = {
            "provider_id": self.id,
            "phone_number": phone,
            "message": message,
            "status": status,
            "provider_msg_id": provider_msg_id or "",
            "error_message": error_msg or "",
            "res_model": res_model or "",
            "res_id": res_id or 0,
        }
        if template_id:
            vals["template_id"] = template_id
        if batch_line_id:
            vals["batch_line_id"] = batch_line_id

        try:
            self.env["alba.sms.log"].sudo().create(vals)
        except Exception as exc:  # noqa: BLE001
            # Logging failure must never crash the send operation.
            _logger.error("alba.sms.provider: failed to write SMS log: %s", exc)
