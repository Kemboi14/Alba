# -*- coding: utf-8 -*-
"""
Migration 19.0.1.8.4
====================
Fix interest rates that were mistakenly stored as decimal fractions
(e.g. 0.15) instead of whole-number percentages (e.g. 15).

Affected tables
---------------
- alba_loan_product       — product template (interest_rate)
- alba_loan               — disbursed loans  (interest_rate, copied from product)
- alba_loan_refinance     — refinance records (new_interest_rate)
- alba_loan_consolidation — consolidation records (new_interest_rate)
- alba_loan_restructure   — restructure records (new_interest_rate)

The WHERE clause `column > 0 AND column < 1` is conservative:
it only touches values that are unambiguously wrong (strictly between 0 and 1).
It is idempotent — corrected values (>= 1) will never be touched again.

Run as post-migrate so ORM and DB constraints are already in place.
"""
import logging

_logger = logging.getLogger(__name__)

# (table_name, column_name)
_TABLES = [
    ("alba_loan_product",       "interest_rate"),
    ("alba_loan",               "interest_rate"),
    ("alba_loan_refinance",     "new_interest_rate"),
    ("alba_loan_consolidation", "new_interest_rate"),
    ("alba_loan_restructure",   "new_interest_rate"),
]


def _fix_table(cr, table, column):
    cr.execute(f"""
        UPDATE {table}
           SET {column} = {column} * 100
         WHERE {column} > 0
           AND {column} < 1
    """)
    return cr.rowcount


def migrate(cr, version):
    for table, column in _TABLES:
        # Skip gracefully if table doesn't exist yet (fresh install path)
        cr.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = %s
        """, (table,))
        if not cr.fetchone():
            continue

        count = _fix_table(cr, table, column)
        if count:
            _logger.info(
                "Migration 19.0.1.8.4: corrected %d row(s) in %s.%s "
                "(fractional -> percentage).",
                count, table, column,
            )
