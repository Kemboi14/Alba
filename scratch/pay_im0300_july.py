"""
Process the interest payout for IM-0300's July 2026 accrual (period
2026-06-29 to 2026-07-28, currently 'posted', interest KES 20,500.00)
through the normal alba.interest.payout.wizard flow — the same path the
UI "Pay" button uses. Creates a real outbound account.payment, posts it,
creates the alba.interest.payout record, and marks the accrual 'paid'.

Run from the Odoo shell on the target server:

    cd /opt/odoo/Alba && sudo -u odoo /usr/bin/odoo shell -c /etc/odoo/odoo.conf \
        -d Alba --no-http < scratch/pay_im0300_july.py

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

wiz = env["alba.interest.payout.wizard"].create({
    "investment_id": inv.id,
    "payout_mode": "select",
    "selected_accrual_ids": [(6, 0, acc.ids)],
    "journal_id": inv.payment_journal_id.id,
    "payout_date": acc.period_end,
    "memo": "Interest Payout — %s — Jul 2026" % inv.investment_number,
})
wiz._onchange_payout_mode()
wiz._compute_payout_amounts()

print("PRECHECK gross=%.2f wht=%.2f net=%.2f" % (wiz.gross_interest, wiz.wht_amount, wiz.net_interest_payable))

result = wiz.action_confirm_payout()

env.cr.commit()

acc_after = env["alba.interest.accrual"].browse(acc.id)
print("PAY_IM0300_JULY_RESULT")
print("accrual state: %s" % acc_after.state)
print("interest_payout_id: %s" % (acc_after.interest_payout_id.name if acc_after.interest_payout_id else None))
print("investment total_interest_paid: %.2f" % inv.total_interest_paid)
print("investment total_interest_outstanding: %.2f" % inv.total_interest_outstanding)
