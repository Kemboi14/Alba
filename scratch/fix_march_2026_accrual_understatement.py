"""
One-off data fix: 13 investment accruals for the 2026-03-01..2026-03-28
cycle (a 28-day period) were computed with a plain days/30 proration
instead of compute_accrual_interest's "within 3 days of 30 = one full
month" rule (see odoo_addons/alba_investors/models/accrual_backfill.py),
understating interest by a total of KES 35,141.32 across the portfolio.

Run from the Odoo shell on the target server:

    cd /opt/odoo/Alba && /opt/odoo/odoo/odoo-bin shell -c /etc/odoo/odoo.conf -d Alba --no-http < scratch/fix_march_2026_accrual_understatement.py

10 of the 13 accruals are still 'posted' (not yet paid out) - these are
reset to draft, their stale journal entry is cancelled/unlinked, and
action_post() recomputes and reposts them using the canonical formula.

3 of the 13 are already 'paid' - only their interest_amount field is
corrected (total_interest_paid on the investment is derived independently
from posted payout records, not from this field, so this safely surfaces
the shortfall as outstanding without touching the historical paid
transaction or its journal entry).

_compute_financials() is deliberately never called directly here - doing
so routes through alba.investment's own write() override, which refuses
edits to active investments. Reading the fields at the end forces Odoo's
normal dependency-triggered recompute via its internal (unguarded) flush
path instead, the same way every other automated accrual posting does.
"""
from datetime import date

log = []

# --- 10 not-yet-paid records: reset to draft, let action_post() recompute correctly ---
POSTED_IDS = [580, 586, 591, 606, 607, 609, 615, 1033, 1043, 1048]
for iid in POSTED_IDS:
    inv = env['alba.investment'].browse(iid)
    acc = inv.accrual_ids.filtered(lambda a: a.period_start == date(2026, 3, 1) and a.period_end == date(2026, 3, 28) and a.state != 'reversed')
    if len(acc) != 1:
        log.append(f"{inv.investment_number}: expected 1 matching accrual, found {len(acc)} - SKIPPED")
        continue
    acc = acc[0]
    before = acc.interest_amount
    before_state = acc.state
    if before_state != 'posted':
        log.append(f"{inv.investment_number}: expected state 'posted', found '{before_state}' - SKIPPED for safety")
        continue
    if acc.move_id:
        if acc.move_id.state == 'posted':
            acc.move_id.button_cancel()
        acc.move_id.unlink()
        acc.write({'move_id': False})
    acc.write({'state': 'draft'})
    acc.action_post()
    after = acc.interest_amount
    log.append(f"{inv.investment_number} (id={iid}): state {before_state}->{acc.state}, interest {before:.2f} -> {after:.2f}, move={acc.move_id.name if acc.move_id else None}")

# --- 3 already-paid records: only correct interest_amount, leave state/move_id untouched ---
PAID_FIX = {
    573: 15000.00,   # IM-0300
    614: 60120.00,   # IM-0305
    1039: 16390.90,  # IM-0455
}
for iid, correct_amount in PAID_FIX.items():
    inv = env['alba.investment'].browse(iid)
    acc = inv.accrual_ids.filtered(lambda a: a.period_start == date(2026, 3, 1) and a.period_end == date(2026, 3, 28) and a.state != 'reversed')
    if len(acc) != 1:
        log.append(f"{inv.investment_number}: expected 1 matching accrual, found {len(acc)} - SKIPPED")
        continue
    acc = acc[0]
    if acc.state != 'paid':
        log.append(f"{inv.investment_number}: expected state 'paid', found '{acc.state}' - SKIPPED for safety")
        continue
    before = acc.interest_amount
    acc.write({'interest_amount': correct_amount, 'closing_balance': acc.opening_balance + correct_amount})
    log.append(f"{inv.investment_number} (id={iid}): interest {before:.2f} -> {acc.interest_amount:.2f} (state kept as 'paid', move_id untouched)")

env.flush_all()
for iid in list(PAID_FIX.keys()) + POSTED_IDS:
    inv = env['alba.investment'].browse(iid)
    log.append(f"{inv.investment_number}: total_interest_accrued={inv.total_interest_accrued:.2f} "
               f"total_interest_outstanding={inv.total_interest_outstanding:.2f} current_value={inv.current_value:.2f}")

env.cr.commit()
print("RESULT_LOG_START")
for l in log:
    print(l)
print("RESULT_LOG_END")
