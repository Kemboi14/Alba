# -*- coding: utf-8 -*-
"""
Post-migration script for version 19.0.1.9.0

Backfills the new `res.partner.alba_customer_number` (a unique, bank-style
Alba Capital Customer Number, shared across a person's loan and investor
records) for every partner that already has an `alba.customer` and/or
`alba.investor` record but was created before this field existed.

Safe to re-run: `_assign_alba_customer_number` is a no-op for any partner
that already has a number.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    customers = env["alba.customer"].search([("partner_id.alba_customer_number", "=", False)])
    assigned = 0
    for customer in customers:
        if customer.partner_id:
            customer.partner_id._assign_alba_customer_number("1")
            assigned += 1
    _logger.info(
        "Backfilled Alba Capital Customer Number for %d existing loan customer(s).",
        assigned,
    )

    if "alba.investor" in env.registry.models:
        investors = env["alba.investor"].search(
            [("partner_id.alba_customer_number", "=", False)]
        )
        investor_assigned = 0
        for investor in investors:
            if investor.partner_id:
                investor.partner_id._assign_alba_customer_number("2")
                investor_assigned += 1
        _logger.info(
            "Backfilled Alba Capital Customer Number for %d existing investor(s) "
            "with no prior loan customer record.",
            investor_assigned,
        )
