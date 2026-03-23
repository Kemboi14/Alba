# -*- coding: utf-8 -*-
"""
core.services — Alba Capital portal service layer.

This package contains stateless service modules that encapsulate all
external integrations and shared business logic for the Django portal:

    odoo_sync   — Bidirectional sync with Odoo via the Alba REST API.
    mpesa       — Safaricom Daraja API helpers (STK Push, C2B, B2C).
    webhooks    — Inbound webhook receiver and HMAC verification.

Usage example::

    from core.services.odoo_sync import OdooSyncService
    service = OdooSyncService()
    result = service.create_customer(user)
"""

from .mpesa import MpesaService
from .odoo_sync import OdooSyncService

__all__ = [
    "OdooSyncService",
    "MpesaService",
]
