"""
Mark IM-0300's July 2026 accrual as paid using the EXISTING receipt —
payout IPAY/2026/0272 (2026-07-28, KES 20,500.00) — rather than creating
a new payment. That payout's link to the July accrual was severed when
the daily cron deleted and regenerated the accrual record (old id 43912
-> new id 44096) for an unrelated reason; the cash was already sent.

Adds the July accrual to payout 272's accrual_ids (keeping its existing
June link intact) and marks the accrual paid. No account.payment or
journal entry is created — this only corrects the record to match
reality.

Run from the Odoo shell on the target server:

    cd /opt/odoo/Alba && sudo -u odoo /usr/bin/odoo shell -c /etc/odoo/odoo.conf \
        -d Alba --no-http < scratch/mark_im0300_july_paid.py

COMMITS at the end.
"""
inv = env["alba.investment"].search([("investment_number", "=", "IM-0300")], limit=1)
assert inv, "IM-0300 not found"

acc = inv.accrual_ids.filtered(
    lambda a: a.period_start.strftime("%Y-%m-%d") == "2026-06-29"
    and a.period_end.strftime("%Y-%m-%d") == "2026-07-28"
    and a.state == "posted"
)
assert len(acc) == 1, "expected exactly 1 matching posted accrual, found %d" % len(acc)

payout = env["alba.interest.payout"].search([("name", "=", "IPAY/2026/0272")], limit=1)
assert payout, "payout IPAY/2026/0272 not found"
assert payout.investment_id.id == inv.id, "payout does not belong to IM-0300"

acc.write({
    "state": "paid",
    "interest_payout_id": payout.id,
    "interest_amount_payable_now": 0.0,
    "interest_amount_deferred": 0.0,
    "cumulative_amount_paid": acc.interest_amount,
})
payout.write({"accrual_ids": [(4, acc.id)]})

env.flush_all()
env.cr.commit()

acc_after = env["alba.interest.accrual"].browse(acc.id)
print("MARK_JULY_PAID_RESULT")
print("accrual state: %s" % acc_after.state)
print("interest_payout_id: %s" % acc_after.interest_payout_id.name)
print("cumulative_amount_paid: %.2f" % acc_after.cumulative_amount_paid)
print("investment total_interest_accrued: %.2f" % inv.total_interest_accrued)
print("investment total_interest_paid: %.2f" % inv.total_interest_paid)
print("investment total_interest_outstanding: %.2f" % inv.total_interest_outstanding)
print("investment current_value: %.2f" % inv.current_value)
