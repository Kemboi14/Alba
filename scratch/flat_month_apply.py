"""
Apply the flat 30-day-month accrual correction across every affected
active, monthly-compounding investment. NOT a dry run — this writes and
commits.

Mechanics:
  - 'posted' (not yet paid) accruals: full reverse -> reset-to-draft ->
    recompute -> repost cycle (action_reverse / action_reset_to_draft /
    action_post on alba.interest.accrual). No real cash has moved for
    these, so a clean repost with a fresh journal entry is safe and
    preserves a full audit trail (original entry + reversal + new entry).
  - 'paid' accruals: interest_amount/closing_balance corrected IN PLACE;
    state/move_id/interest_payout_id are left untouched. This mirrors the
    established pattern from the prior March-2026 remediation
    (scratch/fix_march_2026_accrual_understatement.py, git history) for
    the same reason: total_interest_paid is derived from posted payout
    records' gross_interest, not from this field, so correcting it here
    never touches a historical payment or its journal entry — whether the
    correction is an under- or over-payment. total_interest_outstanding
    recomputes automatically afterward: an underpayment shows as
    still-outstanding (collectible via the normal payout wizard later); an
    overpayment floors at 0 (outstanding never goes negative), since there
    is no receivable/clawback account in this codebase to record money
    owed back by an investor.
  - Any accrual flagged by the dry run (touched by more than one payout,
    or a 'posted' accrual with an in-progress partial payout) causes its
    ENTIRE investment to be skipped, left for manual review — same safety
    gate as scratch/flat_month_dry_run.py.
  - Each investment is processed in its own DB savepoint so a failure on
    one does not roll back corrections already applied to others.
  - The opening-balance / prior-unpaid-interest recomputation is queried
    fresh from the DB via env.search() at every step (not from an
    in-memory snapshot), exactly mirroring
    action_backfill_missing_accruals (investment.py:1442-1506), so each
    period always sees the just-corrected value of the period before it.

Run from the Odoo shell on the target server:

    cd /opt/odoo/Alba && sudo -u odoo /usr/bin/odoo shell -c /etc/odoo/odoo.conf \
        -d <db> --no-http < scratch/flat_month_apply.py

COMMITS at the end.
"""
from odoo.addons.alba_investors.models.accrual_backfill import (
    compute_accrual_interest,
    split_period_by_topups,
)

REASON = "Flat 30-day month remediation - 2026-08-24"

log = []
corrected_posted = 0
corrected_paid = 0
skipped_flagged = 0
errors = []

Accrual = env["alba.interest.accrual"]
Topup = env["alba.investment.topup"]
Payout = env["alba.interest.payout"]

investments = env["alba.investment"].search([
    ("state", "=", "active"),
    ("compounding_frequency", "=", "monthly"),
])

for inv in investments:
    accrual_ids_ordered = Accrual.search(
        [("investment_id", "=", inv.id), ("state", "in", ("posted", "paid"))],
        order="period_start, id",
    )
    if not accrual_ids_ordered:
        continue

    # ---- Safety gate: skip the whole investment if any of its accruals
    # is multi-payout or has an in-progress partial payout. ----
    inv_has_flag = False
    for acc in accrual_ids_ordered:
        is_partial_open = (
            acc.state == "posted" and acc.interest_payout_id
            and acc.interest_amount_deferred > 0
        )
        payout_count = Payout.search_count([("accrual_ids", "in", [acc.id])])
        if is_partial_open or payout_count > 1:
            inv_has_flag = True
            break
    if inv_has_flag:
        skipped_flagged += 1
        log.append("%s: SKIPPED (flagged for manual review)" % inv.investment_number)
        continue

    try:
        with env.cr.savepoint():
            for acc_id in accrual_ids_ordered.ids:
                acc = Accrual.browse(acc_id)  # fresh read each iteration

                topups_prior = Topup.search([
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("date", "<", acc.period_start),
                ])
                base_before_period = inv.principal_amount + sum(topups_prior.mapped("amount"))

                prior_unpaid_accruals = Accrual.search([
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("period_end", "<", acc.period_start),
                ])
                prior_unpaid_sum = sum(
                    (a.interest_amount_deferred
                     if (a.interest_payout_id and a.interest_amount_deferred > 0)
                     else a.interest_amount)
                    for a in prior_unpaid_accruals
                )
                new_opening = round(base_before_period + prior_unpaid_sum, 2)

                in_period_topups = Topup.search([
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("date", ">=", acc.period_start),
                    ("date", "<=", acc.period_end),
                ])
                new_interest = split_period_by_topups(
                    opening_balance=new_opening,
                    annual_rate=inv.interest_rate,
                    period_start=acc.period_start,
                    period_end=acc.period_end,
                    topups=[{"date": t.date, "amount": t.amount} for t in in_period_topups],
                    interest_fn=compute_accrual_interest,
                )

                delta = round(new_interest - acc.interest_amount, 2)
                opening_delta = round(new_opening - acc.opening_balance, 2)
                if abs(delta) < 0.01 and abs(opening_delta) < 0.01:
                    continue  # nothing to change on this period

                old_interest = acc.interest_amount
                old_opening = acc.opening_balance

                if acc.state == "posted":
                    acc.write({"reversal_reason": REASON})
                    acc.action_reverse()
                    acc.action_reset_to_draft()
                    acc.write({
                        "opening_balance": new_opening,
                        "interest_amount": new_interest,
                        "closing_balance": round(new_opening + new_interest, 2),
                    })
                    acc.action_post()
                    corrected_posted += 1
                    log.append(
                        "%s acc#%d POSTED: opening %.2f->%.2f interest %.2f->%.2f (delta %+.2f)"
                        % (inv.investment_number, acc.id, old_opening, new_opening,
                           old_interest, new_interest, delta)
                    )
                else:  # 'paid' — correct in place, never touch state/move_id/payout link
                    acc.write({
                        "opening_balance": new_opening,
                        "interest_amount": new_interest,
                        "closing_balance": round(new_opening + new_interest, 2),
                    })
                    corrected_paid += 1
                    log.append(
                        "%s acc#%d PAID (in-place): opening %.2f->%.2f interest %.2f->%.2f (delta %+.2f)"
                        % (inv.investment_number, acc.id, old_opening, new_opening,
                           old_interest, new_interest, delta)
                    )
    except Exception as exc:
        errors.append("%s: %s" % (inv.investment_number, exc))
        log.append("%s: ERROR - %s" % (inv.investment_number, exc))
        continue

env.flush_all()
env.cr.commit()

print("FLAT_MONTH_APPLY_START")
print("Investments scanned: %d" % len(investments))
print("Investments skipped (flagged for manual review): %d" % skipped_flagged)
print("Accruals corrected (posted, reversed+reposted): %d" % corrected_posted)
print("Accruals corrected (paid, in-place): %d" % corrected_paid)
print("Errors: %d" % len(errors))
print("")
for l in log:
    print(l)
if errors:
    print("--- ERRORS ---")
    for e in errors:
        print(e)
print("FLAT_MONTH_APPLY_END")
