# -*- coding: utf-8 -*-
"""
core.services.mpesa
====================
Django-side Safaricom Daraja API helper for the Alba Capital portal.

This module provides the MpesaService class which the Django portal uses to:
  • Initiate STK Push payment prompts (Lipa Na M-Pesa Online)
  • Query the status of a pending STK Push
  • Verify inbound M-Pesa callback payloads
  • Normalise and validate Kenyan phone numbers
  • Format amounts for the Daraja API (whole shillings)

The heavy Daraja work (C2B registration, B2C payouts, token caching) is
handled entirely inside Odoo (alba_loans module).  The Django portal only
ever initiates STK Pushes and reads back results — it does NOT store Daraja
credentials.  All real API calls flow through Odoo's REST endpoints.

Configuration (.env / Django settings)
---------------------------------------
  ODOO_URL               Base URL of the Odoo instance.
  ODOO_API_KEY           X-Alba-API-Key header value.
  ODOO_TIMEOUT           HTTP timeout in seconds (default: 30).
  MPESA_STK_ENDPOINT     Odoo endpoint to trigger STK push
                         (default: /alba/api/v1/mpesa/stk-push).
  MPESA_STK_QUERY_ENDPOINT  Odoo endpoint to query STK status
                         (default: /alba/api/v1/mpesa/stk-status).

Standalone Daraja mode (optional)
----------------------------------
If MPESA_CONSUMER_KEY and MPESA_CONSUMER_SECRET are set in settings AND
MPESA_STANDALONE=True, MpesaService will call the Daraja API directly
(without going through Odoo).  This is useful for development / testing
when an Odoo instance is not available.

In production it is strongly recommended to route all Daraja calls
through Odoo so that the transaction audit log (alba.mpesa.transaction)
is maintained in one place.

Error handling
--------------
  MpesaError                 Base exception for all M-Pesa errors.
  MpesaAuthError             Daraja OAuth failure.
  MpesaValidationError       Invalid phone / amount.
  MpesaAPIError              Daraja returned a non-success response.
  MpesaTimeoutError          HTTP request timed out.
  MpesaConnectionError       Could not reach Daraja / Odoo.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import datetime, timedelta

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MpesaError(Exception):
    """Base exception for all M-Pesa errors."""

    def __init__(self, message: str, code: str = "", detail: str = ""):
        super().__init__(message)
        self.code = code
        self.detail = detail or message


class MpesaAuthError(MpesaError):
    """Daraja OAuth token acquisition failed."""

    pass


class MpesaValidationError(MpesaError):
    """Invalid input (phone number, amount, etc.)."""

    pass


class MpesaAPIError(MpesaError):
    """Daraja API returned a non-success response."""

    def __init__(self, message: str, response_code: str = "", response_desc: str = ""):
        super().__init__(message, code=response_code, detail=response_desc)
        self.response_code = response_code
        self.response_desc = response_desc


class MpesaTimeoutError(MpesaError):
    """HTTP request to Daraja / Odoo timed out."""

    pass


class MpesaConnectionError(MpesaError):
    """Could not reach the Daraja API or Odoo M-Pesa proxy."""

    pass


# ---------------------------------------------------------------------------
# Phone / amount utilities (module-level, no class needed)
# ---------------------------------------------------------------------------


def normalise_phone(raw: str) -> str:
    """
    Normalise a Kenyan phone number to the 254XXXXXXXXX format required
    by the Safaricom Daraja API.

    Accepted input formats
    ----------------------
    ``0712345678``    → ``254712345678``
    ``+254712345678`` → ``254712345678``
    ``254712345678``  → ``254712345678``  (no-op)
    ``712345678``     → ``254712345678``

    Args:
        raw: Phone number string.  Spaces and hyphens are stripped.

    Returns:
        str: Normalised 12-digit phone number starting with ``254``.

    Raises:
        MpesaValidationError: When the result does not match a valid
                              Kenyan number pattern.

    Examples::

        normalise_phone("0712345678")    # → "254712345678"
        normalise_phone("+254712345678") # → "254712345678"
        normalise_phone("254722000000")  # → "254722000000"
    """
    if not raw or not isinstance(raw, str):
        raise MpesaValidationError("Phone number must not be empty.")

    phone = (
        raw.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    )

    # Strip leading +
    if phone.startswith("+"):
        phone = phone[1:]

    # 0XXXXXXXXX → 254XXXXXXXXX
    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]
    # 9-digit without country code → 254XXXXXXXXX
    elif len(phone) == 9 and not phone.startswith("254"):
        phone = "254" + phone

    # Validate: 12 digits, starts with 2547 or 2541 (Safaricom / Airtel)
    if not phone.isdigit() or len(phone) != 12 or not phone.startswith("254"):
        raise MpesaValidationError(
            f"Invalid Kenyan phone number: '{raw}'.  "
            "Use format 0712345678 or 254712345678."
        )

    return phone


def to_whole_shillings(amount) -> int:
    """
    Convert *amount* to a whole-number integer as required by Daraja.

    Daraja rejects fractional shillings, so this function rounds UP to
    the nearest whole shilling.

    Args:
        amount: Monetary value (int, float, or Decimal).

    Returns:
        int: Amount rounded up to the nearest whole shilling.

    Raises:
        MpesaValidationError: When amount is zero or negative.

    Examples::

        to_whole_shillings(100)     # → 100
        to_whole_shillings(99.50)   # → 100
        to_whole_shillings(0.01)    # → 1
    """
    import math

    try:
        value = math.ceil(float(amount))
    except (TypeError, ValueError) as exc:
        raise MpesaValidationError(f"Invalid amount '{amount}': {exc}") from exc

    if value <= 0:
        raise MpesaValidationError(
            f"Payment amount must be greater than zero.  Got: {amount}"
        )
    return value


def format_phone_display(phone_254: str) -> str:
    """
    Format a 254XXXXXXXXX phone number into a human-readable display
    string: ``+254 7XX XXX XXX``.

    Args:
        phone_254: Normalised 254XXXXXXXXX phone string.

    Returns:
        str: Formatted display string, or the original if formatting fails.
    """
    try:
        p = normalise_phone(phone_254)
        return f"+{p[0:3]} {p[3:6]} {p[6:9]} {p[9:12]}"
    except MpesaValidationError:
        return phone_254


# ---------------------------------------------------------------------------
# Standalone Daraja token cache  (module-level, shared across instances)
# ---------------------------------------------------------------------------

_daraja_token_cache: dict = {}
# Structure: { (consumer_key, environment): {"token": str, "expiry": datetime} }


def _get_daraja_token(consumer_key: str, consumer_secret: str, sandbox: bool) -> str:
    """
    Obtain a Daraja OAuth2 bearer token, using an in-process cache to
    avoid redundant token fetches (tokens are valid for 3 600 seconds;
    we cache for 55 minutes).

    Args:
        consumer_key:    Daraja consumer key.
        consumer_secret: Daraja consumer secret.
        sandbox:         True to use the sandbox endpoint.

    Returns:
        str: Bearer token string.

    Raises:
        MpesaAuthError: When the token request fails.
    """
    cache_key = (consumer_key, "sandbox" if sandbox else "production")
    now = datetime.utcnow()
    cached = _daraja_token_cache.get(cache_key)
    if cached and now < cached["expiry"]:
        return cached["token"]

    base = (
        "https://sandbox.safaricom.co.ke" if sandbox else "https://api.safaricom.co.ke"
    )
    url = f"{base}/oauth/v1/generate?grant_type=client_credentials"
    credentials = base64.b64encode(
        f"{consumer_key}:{consumer_secret}".encode()
    ).decode()

    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Basic {credentials}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout as exc:
        raise MpesaTimeoutError("Daraja token request timed out.") from exc
    except requests.exceptions.ConnectionError as exc:
        raise MpesaConnectionError(f"Cannot reach Daraja: {exc}") from exc
    except requests.exceptions.HTTPError as exc:
        body = ""
        try:
            body = exc.response.text[:400]
        except Exception:
            pass
        raise MpesaAuthError(
            f"Daraja token request failed (HTTP {exc.response.status_code}): {body}"
        ) from exc

    token = data.get("access_token", "").strip()
    if not token:
        raise MpesaAuthError(
            f"Daraja did not return an access_token.  Response: {data}"
        )

    _daraja_token_cache[cache_key] = {
        "token": token,
        "expiry": now + timedelta(minutes=55),
    }
    return token


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------


class MpesaService:
    """
    Django portal M-Pesa service.

    Two operating modes:

    1. **Proxy mode** (default, recommended for production):
       All Daraja API calls are proxied through Odoo via the Alba REST API.
       Odoo manages credentials, token caching, transaction logging, and
       webhook handling.  Django only needs to know the Odoo URL and API key.

    2. **Standalone mode** (set ``MPESA_STANDALONE=True`` in settings):
       Django calls the Daraja API directly.  Requires MPESA_CONSUMER_KEY,
       MPESA_CONSUMER_SECRET, MPESA_SHORTCODE, MPESA_PASSKEY, and
       MPESA_CALLBACK_BASE_URL to be set.  Useful for local development
       when Odoo is not available.

    Usage::

        service = MpesaService()

        # Initiate STK Push
        result = service.stk_push(
            phone_number="0712345678",
            amount=1500.00,
            account_reference="ALB-0001234",
            transaction_desc="Loan Repayment",
        )
        checkout_id = result["checkout_request_id"]

        # Query status
        status = service.query_stk_status(checkout_id)
        if status["result_code"] == "0":
            # Payment confirmed
            pass
    """

    def __init__(self):
        self._standalone = bool(getattr(settings, "MPESA_STANDALONE", False))
        self._timeout = int(getattr(settings, "ODOO_TIMEOUT", 30))

        if self._standalone:
            self._consumer_key = getattr(settings, "MPESA_CONSUMER_KEY", "") or ""
            self._consumer_secret = getattr(settings, "MPESA_CONSUMER_SECRET", "") or ""
            self._shortcode = str(getattr(settings, "MPESA_SHORTCODE", "") or "")
            self._till_number = str(getattr(settings, "MPESA_TILL_NUMBER", "") or "")
            self._passkey = getattr(settings, "MPESA_PASSKEY", "") or ""
            self._callback_base = (
                getattr(settings, "MPESA_CALLBACK_BASE_URL", "") or ""
            ).rstrip("/")
            self._account_type = getattr(settings, "MPESA_ACCOUNT_TYPE", "paybill")
            self._sandbox = bool(getattr(settings, "MPESA_SANDBOX", True))
            self._base_url = (
                "https://sandbox.safaricom.co.ke"
                if self._sandbox
                else "https://api.safaricom.co.ke"
            )
        else:
            # Proxy mode — use Odoo REST endpoints
            self._odoo_url = (getattr(settings, "ODOO_URL", "") or "").rstrip("/")
            self._odoo_api_key = getattr(settings, "ODOO_API_KEY", "") or ""
            self._stk_endpoint = getattr(
                settings,
                "MPESA_STK_ENDPOINT",
                "/alba/api/v1/mpesa/stk-push",
            )
            self._stk_query_endpoint = getattr(
                settings,
                "MPESA_STK_QUERY_ENDPOINT",
                "/alba/api/v1/mpesa/stk-status",
            )

        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "AlbaDjangoPortal/1.0"})

    # =========================================================================
    # Public API
    # =========================================================================

    def stk_push(
        self,
        phone_number: str,
        amount: float,
        account_reference: str,
        transaction_desc: str = "Loan Repayment",
        odoo_loan_id: int = 0,
    ) -> dict:
        """
        Initiate an M-Pesa STK Push (Lipa Na M-Pesa Online) payment prompt.

        The customer will receive an on-screen payment popup on their phone
        and must enter their M-Pesa PIN to complete the payment.

        Args:
            phone_number:      Customer's Safaricom number.  Accepted formats:
                               ``0712345678``, ``+254712345678``,
                               ``254712345678``.
            amount:            Amount in KES.  Fractional shillings are rounded
                               up automatically.
            account_reference: Reference shown on the customer's handset and
                               used to match the payment to a loan.  Max 12
                               characters.  Typically the loan number.
            transaction_desc:  Short description shown in the prompt.  Max 13
                               characters.  Defaults to "Loan Repayment".
            odoo_loan_id:      Optional Odoo loan ID for proxy-mode requests.

        Returns:
            dict: Contains at minimum:
                ``checkout_request_id`` (str),
                ``merchant_request_id`` (str),
                ``response_code`` ("0" = accepted),
                ``customer_message`` (str),
                ``mode`` ("proxy" | "standalone").

        Raises:
            MpesaValidationError:  Invalid phone number or amount.
            MpesaAPIError:         Daraja rejected the request.
            MpesaAuthError:        OAuth token failure (standalone mode).
            MpesaTimeoutError:     Request timed out.
            MpesaConnectionError:  Cannot reach Daraja / Odoo.
        """
        # Normalise and validate inputs
        phone = normalise_phone(phone_number)
        int_amount = to_whole_shillings(amount)
        ref = (account_reference or "")[:12].strip()
        desc = (transaction_desc or "Loan Repayment")[:13].strip()

        if not ref:
            raise MpesaValidationError("account_reference must not be empty.")

        logger.info(
            "STK Push initiated: phone=%s amount=%d ref=%s desc=%s mode=%s",
            phone,
            int_amount,
            ref,
            desc,
            "standalone" if self._standalone else "proxy",
        )

        if self._standalone:
            return self._stk_push_standalone(phone, int_amount, ref, desc)
        else:
            return self._stk_push_via_odoo(phone, int_amount, ref, desc, odoo_loan_id)

    def query_stk_status(self, checkout_request_id: str) -> dict:
        """
        Query the processing status of a previously initiated STK Push.

        Args:
            checkout_request_id: The ``checkout_request_id`` value returned
                                 by :meth:`stk_push`.

        Returns:
            dict: Contains at minimum:
                ``checkout_request_id`` (str),
                ``result_code`` (str — "0" = success),
                ``result_desc`` (str),
                ``status`` ("completed" | "pending" | "failed" | "cancelled").

        Raises:
            MpesaValidationError:  Missing checkout_request_id.
            MpesaAPIError:         Daraja query failed.
            MpesaTimeoutError:     Request timed out.
            MpesaConnectionError:  Cannot reach Daraja / Odoo.
        """
        if not checkout_request_id:
            raise MpesaValidationError("checkout_request_id must not be empty.")

        logger.info(
            "STK status query: checkout_id=%s mode=%s",
            checkout_request_id,
            "standalone" if self._standalone else "proxy",
        )

        if self._standalone:
            return self._query_stk_standalone(checkout_request_id)
        else:
            return self._query_stk_via_odoo(checkout_request_id)

    def is_available(self) -> bool:
        """
        Return ``True`` when the M-Pesa service is reachable and configured.
        Never raises — swallows all exceptions.

        In proxy mode, checks that Odoo is reachable via the health endpoint.
        In standalone mode, checks that the required settings are present.
        """
        try:
            if self._standalone:
                return bool(
                    self._consumer_key
                    and self._consumer_secret
                    and self._shortcode
                    and self._passkey
                    and self._callback_base
                )
            else:
                if not self._odoo_url or not self._odoo_api_key:
                    return False
                resp = self._session.get(
                    f"{self._odoo_url}/alba/api/v1/health",
                    headers={"X-Alba-API-Key": self._odoo_api_key},
                    timeout=5,
                )
                return resp.status_code == 200
        except Exception:
            return False

    # =========================================================================
    # Proxy mode helpers
    # =========================================================================

    def _stk_push_via_odoo(
        self,
        phone: str,
        amount: int,
        ref: str,
        desc: str,
        odoo_loan_id: int,
    ) -> dict:
        """
        Send an STK Push request to Odoo, which proxies it to Daraja and
        creates an alba.mpesa.transaction record for the audit log.
        """
        if not self._odoo_url:
            raise MpesaConnectionError(
                "ODOO_URL is not configured.  Cannot proxy STK Push."
            )
        if not self._odoo_api_key:
            raise MpesaConnectionError(
                "ODOO_API_KEY is not configured.  Cannot proxy STK Push."
            )

        payload = {
            "phone_number": phone,
            "amount": amount,
            "account_reference": ref,
            "transaction_desc": desc,
        }
        if odoo_loan_id:
            payload["odoo_loan_id"] = odoo_loan_id

        url = self._odoo_url + self._stk_endpoint
        try:
            resp = self._session.post(
                url,
                json=payload,
                headers={
                    "X-Alba-API-Key": self._odoo_api_key,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise MpesaTimeoutError(
                f"STK Push proxy request timed out after {self._timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise MpesaConnectionError(
                f"Cannot reach Odoo at {self._odoo_url}: {exc}"
            ) from exc

        body = _safe_json(resp)
        if resp.status_code not in (200, 201):
            error = body.get("error") or body.get("detail") or resp.text[:300]
            raise MpesaAPIError(
                f"Odoo STK Push proxy returned HTTP {resp.status_code}: {error}",
                response_code=str(resp.status_code),
                response_desc=str(error),
            )

        result = body
        result.setdefault("mode", "proxy")
        logger.info(
            "STK Push proxied through Odoo: checkout_id=%s",
            result.get("checkout_request_id", "(unknown)"),
        )
        return result

    def _query_stk_via_odoo(self, checkout_request_id: str) -> dict:
        """Query STK status via Odoo proxy."""
        if not self._odoo_url or not self._odoo_api_key:
            raise MpesaConnectionError("ODOO_URL or ODOO_API_KEY is not configured.")

        url = self._odoo_url + self._stk_query_endpoint
        try:
            resp = self._session.post(
                url,
                json={"checkout_request_id": checkout_request_id},
                headers={
                    "X-Alba-API-Key": self._odoo_api_key,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise MpesaTimeoutError(
                f"STK status query timed out after {self._timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise MpesaConnectionError(f"Cannot reach Odoo: {exc}") from exc

        body = _safe_json(resp)
        if resp.status_code not in (200, 201):
            error = body.get("error") or body.get("detail") or resp.text[:300]
            raise MpesaAPIError(
                f"Odoo STK status proxy returned HTTP {resp.status_code}: {error}",
                response_code=str(resp.status_code),
                response_desc=str(error),
            )

        result = body
        result.setdefault("mode", "proxy")
        return result

    # =========================================================================
    # Standalone mode helpers
    # =========================================================================

    def _stk_push_standalone(
        self,
        phone: str,
        amount: int,
        ref: str,
        desc: str,
    ) -> dict:
        """
        Call the Daraja STK Push API directly (standalone mode).

        The Django portal sends the request itself and the result is
        returned to the caller.  No Odoo transaction log is created.
        """
        if not self._consumer_key or not self._consumer_secret:
            raise MpesaConnectionError(
                "MPESA_CONSUMER_KEY and MPESA_CONSUMER_SECRET must be set "
                "in settings when using standalone mode."
            )
        if not self._shortcode:
            raise MpesaValidationError("MPESA_SHORTCODE must be set in settings.")
        if not self._passkey:
            raise MpesaValidationError("MPESA_PASSKEY must be set in settings.")
        if not self._callback_base:
            raise MpesaValidationError(
                "MPESA_CALLBACK_BASE_URL must be set in settings."
            )

        token = _get_daraja_token(
            self._consumer_key,
            self._consumer_secret,
            self._sandbox,
        )

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        raw_password = f"{self._shortcode}{self._passkey}{timestamp}"
        password = base64.b64encode(raw_password.encode()).decode()

        stk_callback_url = f"{self._callback_base}/alba/mpesa/stk/callback"

        # Use till number for Buy Goods, shortcode for Paybill
        if self._account_type == "till" and self._till_number:
            party_b = self._till_number
            transaction_type = "CustomerBuyGoodsOnline"
        else:
            party_b = self._shortcode
            transaction_type = "CustomerPayBillOnline"

        payload = {
            "BusinessShortCode": self._shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": transaction_type,
            "Amount": amount,
            "PartyA": phone,
            "PartyB": party_b,
            "PhoneNumber": phone,
            "CallBackURL": stk_callback_url,
            "AccountReference": ref,
            "TransactionDesc": desc,
        }

        url = f"{self._base_url}/mpesa/stkpush/v1/processrequest"
        try:
            resp = self._session.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise MpesaTimeoutError(
                f"Daraja STK Push timed out after {self._timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise MpesaConnectionError(f"Cannot reach Daraja API: {exc}") from exc
        except requests.exceptions.HTTPError as exc:
            body = ""
            try:
                body = exc.response.text[:400]
            except Exception:
                pass
            raise MpesaAPIError(
                f"Daraja STK Push failed (HTTP {exc.response.status_code}): {body}",
                response_code=str(exc.response.status_code),
                response_desc=body,
            ) from exc

        data = resp.json()
        response_code = str(data.get("ResponseCode", "-1"))

        if response_code != "0":
            raise MpesaAPIError(
                f"Daraja rejected STK Push: {data.get('ResponseDescription', '')}",
                response_code=response_code,
                response_desc=data.get("ResponseDescription", ""),
            )

        logger.info(
            "Standalone STK Push sent: checkout_id=%s merchant_id=%s",
            data.get("CheckoutRequestID"),
            data.get("MerchantRequestID"),
        )

        return {
            "checkout_request_id": data.get("CheckoutRequestID", ""),
            "merchant_request_id": data.get("MerchantRequestID", ""),
            "response_code": response_code,
            "customer_message": data.get(
                "CustomerMessage", "Request accepted for processing."
            ),
            "mode": "standalone",
        }

    def _query_stk_standalone(self, checkout_request_id: str) -> dict:
        """Query STK Push status directly from Daraja (standalone mode)."""
        token = _get_daraja_token(
            self._consumer_key,
            self._consumer_secret,
            self._sandbox,
        )

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        raw_password = f"{self._shortcode}{self._passkey}{timestamp}"
        password = base64.b64encode(raw_password.encode()).decode()

        payload = {
            "BusinessShortCode": self._shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }

        url = f"{self._base_url}/mpesa/stkpushquery/v1/query"
        try:
            resp = self._session.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise MpesaTimeoutError(
                f"Daraja STK status query timed out after {self._timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise MpesaConnectionError(f"Cannot reach Daraja API: {exc}") from exc
        except requests.exceptions.HTTPError as exc:
            body = ""
            try:
                body = exc.response.text[:400]
            except Exception:
                pass
            raise MpesaAPIError(
                f"Daraja STK query failed (HTTP {exc.response.status_code}): {body}",
                response_code=str(exc.response.status_code),
                response_desc=body,
            ) from exc

        data = resp.json()
        result_code = str(data.get("ResultCode", "-1"))

        # Map Daraja result codes to a status string
        if result_code == "0":
            status = "completed"
        elif result_code in ("1032", "1037"):
            status = "cancelled"
        elif result_code == "1":
            status = "pending"
        else:
            status = "failed"

        return {
            "checkout_request_id": checkout_request_id,
            "result_code": result_code,
            "result_desc": data.get("ResultDesc", ""),
            "status": status,
            "mode": "standalone",
        }


# ---------------------------------------------------------------------------
# Inbound callback verification (used by Django webhook views)
# ---------------------------------------------------------------------------


def verify_mpesa_callback(raw_body: bytes, ip_address: str = "") -> bool:
    """
    Perform basic validation of an inbound Safaricom callback request.

    Safaricom does not sign callbacks with a shared secret, so validation
    is limited to:
      1. Ensuring the body is valid JSON.
      2. Optionally checking the source IP against Safaricom's published
         IP ranges (when MPESA_ALLOWED_IPS is set in settings).

    Args:
        raw_body:   Raw bytes of the POST request body.
        ip_address: Remote IP address of the request.

    Returns:
        bool: ``True`` when the callback passes all checks.
    """
    # 1. Must be parseable JSON
    try:
        json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        logger.warning("M-Pesa callback body is not valid JSON.")
        return False

    # 2. Optional IP allowlist
    allowed_ips_setting = getattr(settings, "MPESA_ALLOWED_IPS", None)
    if allowed_ips_setting and ip_address:
        # Can be a list or comma-separated string
        if isinstance(allowed_ips_setting, str):
            allowed_ips = {ip.strip() for ip in allowed_ips_setting.split(",")}
        else:
            allowed_ips = set(allowed_ips_setting)

        if allowed_ips and ip_address not in allowed_ips:
            logger.warning(
                "M-Pesa callback from non-whitelisted IP %s — rejecting.",
                ip_address,
            )
            return False

    return True


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _safe_json(response: requests.Response) -> dict:
    """
    Safely parse an HTTP response body as JSON.

    Returns an empty dict when the body is empty or not valid JSON.
    """
    try:
        return response.json()
    except (ValueError, TypeError):
        return {}
