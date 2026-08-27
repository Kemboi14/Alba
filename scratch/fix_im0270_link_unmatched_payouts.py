"""
Link IM-0270's first 5 monthly payouts (IPAY/2026/0202, 0204, 0208, 0210,
0212 -- flat KES 3,000/month, Jan-May 2026) to their matching accrual
records. These payouts were never linked to an accrual (not even via the
accrual_ids join table), so the accrual chain kept compounding on
"unpaid" interest even though 3,000/month was genuinely paid out.

LINK ONLY, per instruction -- does not recompute the compounding chain.
Each accrual is marked paid at the flat amount actually disbursed
(mirroring the payout wizard's own field-writing convention for a
fully-consumed accrual: payable_now/deferred zeroed, cumulative_amount_paid
holds the running total). interest_amount on each accrual is left
untouched, so total_interest_accrued/outstanding on the investment keep
reflecting the already-compounded (inflated) balance -- recomputing that
chain is a separate, larger fix and out of scope here.

Run from the Odoo shell on the target server:

    cd /opt/odoo/Alba && sudo -u odoo /usr/bin/odoo shell -c /etc/odoo/odoo.conf \
        -d Alba --no-http < scratch/fix_im0270_link_unmatched_payouts.py

COMMITS at the end.
"""
inv = env["alba.investment"].search([("investment_number", "=", "IM-0270")], limit=1)
assert inv, "IM-0270 not found"

pairs = [
    ("2025-12-29", "2026-01-28", "IPAY/2026/0202"),
    ("2026-01-29", "2026-02-28", "IPAY/2026/0204"),
    ("2026-03-01", "2026-03-28", "IPAY/2026/0208"),
    ("2026-03-29", "2026-04-28", "IPAY/2026/0210"),
    ("2026-04-29", "2026-05-28", "IPAY/2026/0212"),
]

results = []
for period_start, period_end, payout_name in pairs:
    acc = inv.accrual_ids.filtered(
        lambda a, ps=period_start, pe=period_end: a.period_start.strftime("%Y-%m-%d") == ps
        and a.period_end.strftime("%Y-%m-%d") == pe
        and a.state == "posted"
    )
    assert len(acc) == 1, "expected exactly 1 posted accrual for %s-%s, found %d" % (
        period_start, period_end, len(acc)
    )
    acc = acc[0]

    payout = env["alba.interest.payout"].search([("name", "=", payout_name)], limit=1)
    assert payout, "payout %s not found" % payout_name
    assert payout.investment_id.id == inv.id, "%s does not belong to IM-0270" % payout_name
    assert not acc.interest_payout_id, "accrual %d already linked to a payout" % acc.id

    paid_now = payout.gross_interest

    acc.write({
        "state": "paid",
        "interest_payout_id": payout.id,
        "interest_amount_payable_now": 0.0,
        "interest_amount_deferred": 0.0,
        "cumulative_amount_paid": (acc.cumulative_amount_paid or 0.0) + paid_now,
    })
    payout.write({"accrual_ids": [(4, acc.id)]})
    results.append((acc.id, payout.name, acc.interest_amount, paid_now))

inv.write({
    "notes": (
        "Payouts linked to accruals (IPAY 202/204/208/210/212). "
        "Interest was compounding on these months because the payouts were "
        "never linked -- that compounding was NOT recomputed, so accrued/"
        "outstanding totals still reflect the inflated chain. Follow-up "
        "needed if the compounding itself should be corrected."
    )
})

env.flush_all()
env.cr.commit()

print("LINK_IM0270_PAYOUTS_RESULT")
for acc_id, payout_name, interest_amount, paid_now in results:
    print("accrual #%d <-> %s | accrued %.2f | paid %.2f | shortfall %.2f" % (
        acc_id, payout_name, interest_amount, paid_now, interest_amount - paid_now
    ))
inv_after = env["alba.investment"].browse(inv.id)
print("investment total_interest_accrued: %.2f" % inv_after.total_interest_accrued)
print("investment total_interest_paid: %.2f" % inv_after.total_interest_paid)
print("investment total_interest_outstanding: %.2f" % inv_after.total_interest_outstanding)
