"""
Scan every monthly-compounding investment's accruals for the topup-split
flat-month bug: split_period_by_topups() breaks a period into sub-periods
around each top-up date and calls compute_accrual_interest() on each
sub-period independently. That function's +-3-day flat-month tolerance
has no way to tell a genuine whole accrual cycle apart from an arbitrary
FRAGMENT of one produced by a top-up split -- so whenever a sub-period's
day count happens to land in the 27-33 day window (or 58-62 for a
two-month fragment), it gets charged a full flat month on that fragment
alone, inflating the period's total interest beyond what even the
post-topup balance for the whole period would give.

READ-ONLY. Reports every affected accrual; does not write anything.

Run from the Odoo shell:

    cd /opt/odoo/Alba && sudo -u odoo /usr/bin/odoo shell -c /etc/odoo/odoo.conf \
        -d Alba --no-http < scratch/find_topup_flatmonth_bug.py
"""
from odoo.addons.alba_investors.models.accrual_backfill import compute_accrual_interest

Accrual = env["alba.interest.accrual"]
Topup = env["alba.investment.topup"]

flagged = []
total_periods_with_topup = 0

investments = env["alba.investment"].search([
    ("state", "=", "active"),
    ("compounding_frequency", "=", "monthly"),
])

for inv in investments:
    accruals = Accrual.search([
        ("investment_id", "=", inv.id),
        ("state", "in", ("posted", "paid")),
    ], order="period_start")

    for acc in accruals:
        topups = Topup.search([
            ("investment_id", "=", inv.id),
            ("state", "=", "posted"),
            ("date", ">=", acc.period_start),
            ("date", "<=", acc.period_end),
        ], order="date")
        if not topups:
            continue
        total_periods_with_topup += 1

        sorted_dates = topups.mapped("date")
        current_start = acc.period_start
        subs = []
        for t_date in sorted_dates:
            subs.append((current_start, t_date))
            current_start = t_date + __import__("datetime").timedelta(days=1)
        if current_start <= acc.period_end:
            subs.append((current_start, acc.period_end))

        for sub_start, sub_end in subs:
            days = (sub_end - sub_start).days + 1
            months = round(days / 30.0)
            is_flattened = months >= 1 and abs(days - months * 30) <= 3
            is_whole_period = (sub_start == acc.period_start and sub_end == acc.period_end)
            if is_flattened and not is_whole_period:
                flagged.append({
                    "investment": inv.investment_number,
                    "accrual_id": acc.id,
                    "period": "%s to %s" % (acc.period_start, acc.period_end),
                    "sub_period": "%s to %s (%d days)" % (sub_start, sub_end, days),
                    "months_charged": months,
                })

print("TOPUP_FLATMONTH_BUG_SCAN_START")
print("Periods with at least one top-up: %d" % total_periods_with_topup)
print("Sub-periods incorrectly flattened to a full month: %d" % len(flagged))
print("")
for f in flagged:
    print("%s | acc#%d | period %s | sub-period %s | charged as %d flat month(s)" % (
        f["investment"], f["accrual_id"], f["period"], f["sub_period"], f["months_charged"]
    ))
print("TOPUP_FLATMONTH_BUG_SCAN_END")
