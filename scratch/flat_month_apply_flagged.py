"""
Apply the flat 30-day-month correction to the investments that
scratch/flat_month_apply.py deliberately skipped (multi-payout history,
or a 'posted' accrual with an in-progress partial payout).

Approved by the accountant to proceed on these 19 investments.

Mechanics — deliberately simpler than the main apply script: for EVERY
accrual on these investments (regardless of state, and regardless of
whether it was individually flagged), correct opening_balance /
interest_amount / closing_balance IN PLACE via a plain write(). This
NEVER touches state, move_id, interest_payout_id, interest_amount_deferred,
interest_amount_payable_now, or cumulative_amount_paid, and never calls
action_reverse()/action_post()/payout.action_reverse() — i.e. it never
rewrites or recreates any journal entry or payment. This is exactly the
same pattern already used for the 126 straightforward 'paid' accruals in
the main run, generalized to also cover the multi-payout/partial-payment
cases where reversing a specific payout's share can't be reliably
determined from stored data (payout.accrual_ids carries no per-accrual
amount). The trade-off, already accepted for the simple 'paid' case and
now extended here: any already-posted journal entry keeps its original
(pre-fix) amount for whatever portion of an accrual's interest was
already disbursed — this script only corrects the stated accrual record
and the investment's downstream computed totals, not history that
already moved real cash.

Run from the Odoo shell on the target server:

    cd /opt/odoo/Alba && sudo -u odoo /usr/bin/odoo shell -c /etc/odoo/odoo.conf \
        -d Alba --no-http < scratch/flat_month_apply_flagged.py

COMMITS at the end.
"""
from odoo.addons.alba_investors.models.accrual_backfill import (
    compute_accrual_interest,
    split_period_by_topups,
)

log = []
corrected = 0
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

    # Only process investments that WOULD have been flagged (i.e. were
    # skipped by the main apply run) — same detection as before.
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
    if not inv_has_flag:
        continue  # already handled by the main apply run

    try:
        with env.cr.savepoint():
            for acc_id in accrual_ids_ordered.ids:
                acc = Accrual.browse(acc_id)

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
                    continue

                old_interest = acc.interest_amount
                old_opening = acc.opening_balance
                acc.write({
                    "opening_balance": new_opening,
                    "interest_amount": new_interest,
                    "closing_balance": round(new_opening + new_interest, 2),
                })
                corrected += 1
                log.append(
                    "%s acc#%d %s (in-place): opening %.2f->%.2f interest %.2f->%.2f (delta %+.2f)"
                    % (inv.investment_number, acc.id, acc.state, old_opening, new_opening,
                       old_interest, new_interest, delta)
                )
    except Exception as exc:
        errors.append("%s: %s" % (inv.investment_number, exc))
        log.append("%s: ERROR - %s" % (inv.investment_number, exc))
        continue

env.flush_all()
env.cr.commit()

print("FLAT_MONTH_FLAGGED_APPLY_START")
print("Accruals corrected (in-place): %d" % corrected)
print("Errors: %d" % len(errors))
print("")
for l in log:
    print(l)
if errors:
    print("--- ERRORS ---")
    for e in errors:
        print(e)
print("FLAT_MONTH_FLAGGED_APPLY_END")
