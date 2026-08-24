"""
Dry-run impact report for the flat-30-day-month accrual fix
(odoo_addons/alba_investors/models/accrual_backfill.py:compute_accrual_interest,
threshold reverted from `months >= 2` back to `months >= 1`).

READ-ONLY. Does not write anything to the database and does not commit.
Walks every active, monthly-compounding investment's posted+paid accruals
oldest-first, recomputes opening_balance/interest_amount from first
principles using the exact same formula action_backfill_missing_accruals
uses (see investment.py:1442-1506), and diffs against the stored values.

Run from the Odoo shell on the target server:

    cd /opt/odoo/Alba && sudo -u odoo /usr/bin/odoo shell -c /etc/odoo/odoo.conf \
        -d <db> --no-http < scratch/flat_month_dry_run.py

Two categories of accrual are deliberately NOT auto-diffed and are instead
flagged for manual review, because correcting them safely requires human
judgement this script can't automate:
  - Accruals touched by more than one payout (interest_payout_id trail is
    not preserved once "posted" state's cumulative_amount_paid rolls up
    across payouts, so action_reverse()'s cumulative reset-to-0 caveat may
    silently over/under-credit the investor).
  - "posted" accruals with an in-progress partial payout
    (interest_payout_id set AND interest_amount_deferred > 0) — the
    payable/deferred split was computed against the OLD interest_amount and
    doesn't cleanly re-derive under a new one.
"""
from odoo.addons.alba_investors.models.accrual_backfill import (
    compute_accrual_interest,
    split_period_by_topups,
)

results = []          # one row per clean (auto-correctable) accrual needing a change
flagged = []          # investments with at least one accrual needing manual review
unaffected_count = 0

investments = env["alba.investment"].search([
    ("state", "=", "active"),
    ("compounding_frequency", "=", "monthly"),
])

for inv in investments:
    accruals = inv.accrual_ids.filtered(
        lambda a: a.state in ("posted", "paid")
    ).sorted(key=lambda a: (a.period_start, a.id))
    if not accruals:
        continue

    topups = inv.topup_ids.filtered(lambda t: t.state == "posted").sorted("date")

    # Detect payout fan-in: an accrual touched by >1 distinct payout across
    # its lifetime can't be reliably identified from stored fields alone
    # (only the LAST interest_payout_id is kept), so treat any 'paid' or
    # partially-deferred 'posted' accrual as flagged rather than guessing.
    inv_flagged = False
    flagged_accrual_ids = set()
    for acc in accruals:
        is_partial_open = (
            acc.state == "posted"
            and acc.interest_payout_id
            and acc.interest_amount_deferred > 0
        )
        payout_count = env["alba.interest.payout"].search_count(
            [("accrual_ids", "in", [acc.id])]
        )
        is_multi_payout = payout_count > 1

        if is_partial_open or is_multi_payout:
            reasons = []
            if is_partial_open:
                reasons.append(
                    "posted with an in-progress partial payout "
                    "(interest_amount_deferred=%.2f)" % acc.interest_amount_deferred
                )
            if is_multi_payout:
                reasons.append("touched by %d separate payouts" % payout_count)
            flagged.append({
                "investment": inv.investment_number,
                "accrual_id": acc.id,
                "period": "%s to %s" % (acc.period_start, acc.period_end),
                "reason": "; ".join(reasons),
            })
            inv_flagged = True
            flagged_accrual_ids.add(acc.id)

    # Walk the chain from first principles, oldest first, mirroring
    # action_backfill_missing_accruals exactly (investment.py:1442-1506).
    # Flagged accruals are skipped for diffing, and downstream periods'
    # opening balances keep using their OLD stored interest_amount (not
    # recomputed) rather than guess at a corrected value for them.
    for acc in accruals:
        topups_prior = topups.filtered(lambda t: t.date < acc.period_start)
        base_before_period = inv.principal_amount + sum(topups_prior.mapped("amount"))

        prior_unpaid_accruals = accruals.filtered(
            lambda a: a.state == "posted" and a.period_end < acc.period_start
        )
        prior_unpaid_sum = sum(
            (a.interest_amount_deferred
             if (a.interest_payout_id and a.interest_amount_deferred > 0)
             else a.interest_amount)
            for a in prior_unpaid_accruals
        )
        new_opening = round(base_before_period + prior_unpaid_sum, 2)

        if acc.id in flagged_accrual_ids:
            continue

        in_period_topups = [
            {"date": t.date, "amount": t.amount}
            for t in topups.filtered(lambda t: acc.period_start <= t.date <= acc.period_end)
        ]
        new_interest = split_period_by_topups(
            opening_balance=new_opening,
            annual_rate=inv.interest_rate,
            period_start=acc.period_start,
            period_end=acc.period_end,
            topups=in_period_topups,
            interest_fn=compute_accrual_interest,
        )

        delta = round(new_interest - acc.interest_amount, 2)
        opening_delta = round(new_opening - acc.opening_balance, 2)

        if abs(delta) < 0.01 and abs(opening_delta) < 0.01:
            unaffected_count += 1
            continue

        results.append({
            "investment": inv.investment_number,
            "accrual_id": acc.id,
            "state": acc.state,
            "period": "%s to %s" % (acc.period_start, acc.period_end),
            "old_opening": acc.opening_balance,
            "new_opening": new_opening,
            "old_interest": acc.interest_amount,
            "new_interest": new_interest,
            "delta": delta,
            "direction": "UNDERPAID (owed to investor)" if delta > 0 else "OVERPAID (owed back)",
        })

    if inv_flagged:
        flagged.append({
            "investment": inv.investment_number,
            "accrual_id": None,
            "period": None,
            "reason": "has one or more flagged accruals above — do not auto-correct this investment",
        })

# ── Report ───────────────────────────────────────────────────────────────
print("FLAT_MONTH_DRY_RUN_START")
print("Investments scanned (active, monthly compounding): %d" % len(investments))
print("Accruals unaffected by the fix: %d" % unaffected_count)
print("Accruals needing correction: %d" % len(results))
print("Investments/accruals flagged for manual review: %d" % len(flagged))
print("")

total_underpaid = sum(r["delta"] for r in results if r["delta"] > 0)
total_overpaid = sum(-r["delta"] for r in results if r["delta"] < 0)
paid_needing_correction = [r for r in results if r["state"] == "paid"]
paid_underpaid = sum(r["delta"] for r in paid_needing_correction if r["delta"] > 0)
paid_overpaid = sum(-r["delta"] for r in paid_needing_correction if r["delta"] < 0)

print("TOTAL underpaid across all affected accruals (owed to investors): %.2f" % total_underpaid)
print("TOTAL overpaid across all affected accruals (owed back):          %.2f" % total_overpaid)
print("")
print("Of which, already PAID accruals specifically:")
print("  PAID underpaid (top-up owed):  %.2f across %d accrual(s)" % (
    paid_underpaid, len([r for r in paid_needing_correction if r["delta"] > 0])))
print("  PAID overpaid (clawback owed): %.2f across %d accrual(s)" % (
    paid_overpaid, len([r for r in paid_needing_correction if r["delta"] < 0])))
print("")

print("--- Per-accrual detail ---")
for r in sorted(results, key=lambda r: (r["investment"], r["period"])):
    print("%s | acc#%d | %-6s | %s | opening %.2f -> %.2f | interest %.2f -> %.2f | delta %+.2f | %s" % (
        r["investment"], r["accrual_id"], r["state"], r["period"],
        r["old_opening"], r["new_opening"], r["old_interest"], r["new_interest"],
        r["delta"], r["direction"],
    ))

print("")
print("--- Flagged for manual review (NOT included in totals above) ---")
for f in flagged:
    print("%s | acc#%s | %s | %s" % (f["investment"], f["accrual_id"], f["period"], f["reason"]))

print("FLAT_MONTH_DRY_RUN_END")
