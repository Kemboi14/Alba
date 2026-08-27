"""
Reconcile IM-0274's April and May 2026 interest payouts against their
regenerated accrual records.

Top-ups posted 2026-03-30 (KES 500,000) and 2026-07-08 (KES 650,000)
triggered accrual regeneration (almost certainly via this week's
topup-split flat-month fix) that deleted and recreated the April and May
accrual records under new ids, severing their link to the two payouts
that had already been sent:

    IPAY/2026/0239  2026-04-28  KES 75,000  (payment 1279)
    IPAY/2026/0262  2026-05-28  KES 75,000  (payment 1310)

Unlike IM-0300, the amounts don't match the regenerated accrual figures
exactly:
    April accrual is now KES 74,000 -- KES 75,000 was actually paid, so
        the accrual is fully covered (investor overpaid by 1,000). Marked
        paid at the real cash amount.
    May accrual is now KES 77,220 -- only KES 75,000 was actually paid,
        so a genuine KES 2,220 remains owed for that period. Linked to
        the payout but left 'posted' with that shortfall recorded as
        interest_amount_deferred, so the next payout run picks it up
        correctly instead of re-charging the whole period.

June (2026-05-29 to 2026-06-28) and July (2026-06-29 to 2026-07-28)
accruals have no payout at all yet and are left untouched.

Run from the Odoo shell on the target server:

    cd /opt/odoo/Alba && sudo -u odoo /usr/bin/odoo shell -c /etc/odoo/odoo.conf \
        -d Alba --no-http < scratch/fix_im0274_match_payouts.py

COMMITS at the end.
"""
inv = env["alba.investment"].search([("investment_number", "=", "IM-0274")], limit=1)
assert inv, "IM-0274 not found"


def get_accrual(period_start, period_end):
    acc = inv.accrual_ids.filtered(
        lambda a: a.period_start.strftime("%Y-%m-%d") == period_start
        and a.period_end.strftime("%Y-%m-%d") == period_end
        and a.state == "posted"
    )
    assert len(acc) == 1, "expected exactly 1 posted accrual for %s-%s, found %d" % (
        period_start, period_end, len(acc)
    )
    return acc[0]


def get_payout(name):
    payout = env["alba.interest.payout"].search([("name", "=", name)], limit=1)
    assert payout, "payout %s not found" % name
    assert payout.investment_id.id == inv.id, "%s does not belong to IM-0274" % name
    return payout


results = []

# April: fully covered (paid 75,000 >= accrued 74,000) -> mark paid.
april_acc = get_accrual("2026-03-29", "2026-04-28")
april_payout = get_payout("IPAY/2026/0239")
assert not april_acc.interest_payout_id, "April accrual already linked"
paid_now = april_payout.gross_interest
april_acc.write({
    "state": "paid",
    "interest_payout_id": april_payout.id,
    "interest_amount_payable_now": 0.0,
    "interest_amount_deferred": 0.0,
    "cumulative_amount_paid": (april_acc.cumulative_amount_paid or 0.0) + paid_now,
})
april_payout.write({"accrual_ids": [(4, april_acc.id)]})
results.append(("April", april_acc.id, april_acc.interest_amount, paid_now, april_acc.state))

# May: only partially covered (paid 75,000 < accrued 77,220) -> stays
# posted, with the genuine 2,220 shortfall carried as deferred.
may_acc = get_accrual("2026-04-29", "2026-05-28")
may_payout = get_payout("IPAY/2026/0262")
assert not may_acc.interest_payout_id, "May accrual already linked"
paid_now = may_payout.gross_interest
shortfall = round(may_acc.interest_amount - paid_now, 2)
assert shortfall > 0, "expected a genuine shortfall on the May accrual"
may_acc.write({
    "interest_payout_id": may_payout.id,
    "interest_amount_payable_now": paid_now,
    "interest_amount_deferred": shortfall,
    "cumulative_amount_paid": (may_acc.cumulative_amount_paid or 0.0) + paid_now,
})
may_payout.write({"accrual_ids": [(4, may_acc.id)]})
results.append(("May", may_acc.id, may_acc.interest_amount, paid_now, may_acc.state))

inv.write({
    "notes": (
        "April/May payouts matched to accruals (IPAY 239/262). April was "
        "fully covered (overpaid by 1,000). May has a genuine 2,220 "
        "shortfall carried as deferred on the accrual -- next payout run "
        "will pick it up. June/July accrued but not yet paid out."
    )
})

env.flush_all()
env.cr.commit()

print("MATCH_IM0274_PAYOUTS_RESULT")
for label, acc_id, interest_amount, paid_now, state in results:
    print("%s accrual #%d | accrued %.2f | paid %.2f | delta %.2f | state=%s" % (
        label, acc_id, interest_amount, paid_now, paid_now - interest_amount, state
    ))
inv_after = env["alba.investment"].browse(inv.id)
print("investment total_interest_accrued: %.2f" % inv_after.total_interest_accrued)
print("investment total_interest_paid: %.2f" % inv_after.total_interest_paid)
print("investment total_interest_outstanding: %.2f" % inv_after.total_interest_outstanding)
