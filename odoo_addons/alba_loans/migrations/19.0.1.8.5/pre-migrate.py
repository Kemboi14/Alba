# -*- coding: utf-8 -*-
"""
Migration 19.0.1.8.5 — pre
===========================
Fix a broken ``ir.actions.server`` record (DB id 1288) whose ``code`` field
contains two errors introduced when it was created manually via the Odoo UI:

  1. **Invalid state values** — ``'active'`` and ``'npl'`` no longer exist on
     ``alba.loan``.  The state selection was expanded to the standard IFRS
     classification model (normal / watch / substandard / doubtful / loss /
     closed / written_off) in migration 19.0.1.8.2.

  2. **Wrong API** — ``.mapped('_compute_par')`` tries to traverse a field
     named ``_compute_par``, which does not exist.  ``_compute_par`` is a
     compute *method*; it must be called as ``._compute_par()``.

The corrected code uses:
  • valid state values: the full set of non-terminal active states
  • the correct call: ``._compute_par()``

This migration runs as pre-migrate so the fixed action is in place before any
cron or user action can trigger it during the upgrade.
"""
import logging

_logger = logging.getLogger(__name__)

# The bad code that must be replaced — match exactly so we don't clobber
# any server action whose code is legitimately different.
_BAD_PATTERN = "model.search([('state', 'in', ['active', 'npl'])]).mapped('_compute_par')"

# Corrected replacement code
_GOOD_CODE = """\
# Update PAR buckets for all active loans.
# Valid states: normal, watch, substandard, doubtful, loss
loans = env['alba.loan'].search([
    ('state', 'in', ['normal', 'watch', 'substandard', 'doubtful', 'loss'])
])
if loans:
    loans._compute_par()
"""


def migrate(cr, version):
    """Patch the broken ir.actions.server record whose code references invalid
    loan states ('active', 'npl') and misuses .mapped() on a compute method."""

    # 1. Find any server action whose code contains the broken snippet
    cr.execute(
        """
        SELECT id, name, code
          FROM ir_act_server
         WHERE code LIKE %s
        """,
        ("%mapped('_compute_par')%",),
    )
    rows = cr.fetchall()

    if not rows:
        _logger.info(
            "Migration 19.0.1.8.5: no broken ir.actions.server records found "
            "(already fixed or never existed). Skipping."
        )
        return

    for action_id, name, code in rows:
        if _BAD_PATTERN not in (code or ""):
            _logger.warning(
                "Migration 19.0.1.8.5: server action %s ('%s') contains "
                "mapped('_compute_par') but not the exact bad pattern — "
                "skipping to avoid unintended changes.",
                action_id, name,
            )
            continue

        cr.execute(
            "UPDATE ir_act_server SET code = %s WHERE id = %s",
            (_GOOD_CODE, action_id),
        )
        _logger.info(
            "Migration 19.0.1.8.5: fixed ir.actions.server id=%s ('%s') — "
            "replaced invalid states ('active', 'npl') and corrected "
            "mapped('_compute_par') → ._compute_par().",
            action_id, name,
        )
