# -*- coding: utf-8 -*-
"""
Migration 19.0.1.8.3
====================
Rename the `loan_id` column on `account_move` to `alba_loan_id`.

The Odoo Enterprise `account_loans` module also defines a `loan_id` field on
`account.move` (pointing to `account.loan`).  Our custom field (pointing to
`alba.loan`) caused a type collision during `_post()`.  Renaming our column
removes the conflict and lets both modules coexist.

Run before Odoo loads the new model definition so it finds the column
already named correctly and doesn't create a new empty one.
"""


def migrate(cr, version):
    # Check whether the old column still exists (safe to run multiple times)
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'account_move'
          AND column_name = 'loan_id'
    """)
    row = cr.fetchone()
    if row:
        # Only rename if there is not already an alba_loan_id column
        cr.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'account_move'
              AND column_name = 'alba_loan_id'
        """)
        if not cr.fetchone():
            cr.execute(
                "ALTER TABLE account_move RENAME COLUMN loan_id TO alba_loan_id"
            )
