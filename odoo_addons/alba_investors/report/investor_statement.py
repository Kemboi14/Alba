# -*- coding: utf-8 -*-
import logging
from datetime import date

from odoo import api, models

_logger = logging.getLogger(__name__)


class ReportInvestorStatement(models.AbstractModel):
    _name = "report.alba_investors.investor_statement_template"
    _description = "Investor Account Statement"
    _inherit = "alba.account.statement.report.mixin"

    @api.model
    def _get_report_values(self, docids, data=None):
        investors = self.env["alba.investor"].browse(docids)
        data = data or {}
        today = date.today()
        date_from = data.get("date_from") or date(today.year, 1, 1)
        date_to = data.get("date_to") or today

        payloads = []
        for investor in investors:
            payload = self._report_payload_from_investor(
                investor, date_from, date_to
            )
            payloads.append(payload)

        return {
            "doc_ids": docids,
            "doc_model": "alba.investor",
            "docs": investors,
            "statements": payloads,
            "date_from": date_from,
            "date_to": date_to,
        }

    @api.model
    def _report_payload_from_investor(self, investor, date_from, date_to):
        """
        Build the full statement payload for an investor across all their investments.

        Opening balance:
            For each investment that started ON or BEFORE date_from, we compute
            the balance at date_from using _compute_investment_opening_balance().
            This correctly includes principal, prior top-ups, prior accruals and
            deducts prior payouts — even for investments that started years ago.

        Ledger lines:
            All events (top-ups, accruals, payouts, withdrawals) within the period
            are collected chronologically and displayed as a running ledger.
        """
        if isinstance(date_from, str):
            date_from = date.fromisoformat(date_from)
        if isinstance(date_to, str):
            date_to = date.fromisoformat(date_to)

        investments = self.env["alba.investment"].search([
            ("investor_id", "=", investor.id),
            ("state", "!=", "draft"),
        ])

        # ── Compute opening balance (correct for ALL investments) ─────────────
        # For every investment active on or before date_from, compute its balance.
        # For investments that started WITHIN the period, they contribute 0 to
        # opening balance (their initial deposit appears in the period events).
        opening_balance = 0.0
        for inv in investments:
            if inv.start_date and inv.start_date < date_from:
                # Investment started before the period — compute its balance
                opening_balance += self._compute_investment_opening_balance(
                    inv, date_from
                )
            # If start_date >= date_from, opening balance contribution is 0
            # (the initial deposit will appear as a credit line in the period)

        # ── Collect all period events across all investments ──────────────────
        period_events = []
        for inv in investments:
            # Include initial deposit only if it falls within the period
            include_initial = bool(
                inv.start_date and date_from <= inv.start_date <= date_to
            )
            for event in self.collect_investment_statement_events(
                inv,
                period_start=date_from,
                period_end=date_to,
                include_initial_deposit=include_initial,
            ):
                period_events.append({
                    "date": event["date"],
                    "type": event["type"],
                    "type_label": event["type_label"],
                    "description": event["description"],
                    "amount": event["amount"],
                    "debit": event["debit"],
                    "credit": event["credit"],
                    "record": event["record"],
                    "accrual_state": event.get("accrual_state"),
                })

        # Sort all transactions chronologically
        period_events.sort(key=lambda x: (x["date"], x.get("type", "")))

        # ── Build ledger lines ────────────────────────────────────────────────
        currency = investor.currency_id or self.env.company.currency_id
        account_number = investor.investor_number or ""
        company = investor.company_id or self.env.company
        _logger.debug(
            "Investor %s company=%s logo=%s logo_web=%s",
            investor.investor_name, bool(company.logo), bool(company.logo_web),
        )
        partner = investor.partner_id

        lines = []
        balance = opening_balance

        lines.append({
            "date": self._format_stmt_date(date_from),
            "description": "Opening Balance",
            "type": "opening",
            "type_label": "Opening Balance",
            "debit": 0.0,
            "credit": 0.0,
            "balance": balance,
            "debit_fmt": "",
            "credit_fmt": "",
            "balance_fmt": self._format_amount(balance, currency),
            "accrual_state": None,
        })

        # ── Summary accumulators ──────────────────────────────────────────────
        deposits = 0.0
        principal_withdrawals = 0.0
        interest_accrued = 0.0

        for tx in period_events:
            balance += tx["amount"]

            is_debit = tx["amount"] < 0
            debit_amt = abs(tx["amount"]) if is_debit else 0.0
            credit_amt = tx["amount"] if not is_debit else 0.0

            if tx["type"] in ("deposit", "topup"):
                deposits += tx["amount"]
            elif tx["type"] == "withdrawal":
                principal_withdrawals += abs(tx["amount"])
            elif tx["type"] == "accrual":
                interest_accrued += tx["amount"]
            # "payout" debits the balance but is NOT a withdrawal — it's interest paid

            lines.append({
                "date": self._format_stmt_date(tx["date"]),
                "description": tx["description"],
                "type": tx["type"],
                "type_label": tx["type_label"],
                "debit": debit_amt,
                "credit": credit_amt,
                "balance": balance,
                "debit_fmt": self._format_amount(debit_amt, currency) if is_debit else "",
                "credit_fmt": self._format_amount(credit_amt, currency) if not is_debit else "",
                "balance_fmt": self._format_amount(balance, currency),
                "accrual_state": tx.get("accrual_state"),
            })

        total_debit = sum(line["debit"] for line in lines)
        total_credit = sum(line["credit"] for line in lines)

        # ── WHT / Net Interest — sourced ONLY from real payout records ─────────
        period_payouts = self.env["alba.interest.payout"].search([
            ("investor_id", "=", investor.id),
            ("state", "=", "posted"),
            ("payout_date", ">=", date_from),
            ("payout_date", "<=", date_to),
        ])
        total_gross_paid = sum(period_payouts.mapped("gross_interest"))
        total_wht_deducted = sum(period_payouts.mapped("wht_amount"))
        total_net_paid = sum(period_payouts.mapped("net_amount"))

        # Interest outstanding = posted accruals in the period NOT yet paid out
        period_accruals_in_range = self.env["alba.interest.accrual"].search([
            ("investor_id", "=", investor.id),
            ("state", "in", ["posted", "paid"]),
            ("accrual_date", ">=", date_from),
            ("accrual_date", "<=", date_to),
        ])
        interest_outstanding = sum(
            a.interest_amount for a in period_accruals_in_range
            if a.state == "posted"
        )

        wht_rate = investments[0].wht_rate if investments else 0.0

        # ── Accrual detail table ───────────────────────────────────────────────
        accrual_lines = []
        for a in period_accruals_in_range.sorted(key=lambda x: x.accrual_date):
            if a.state == "paid":
                status_label = "Paid Out"
                status_class = "paid"
            elif a.state == "posted":
                status_label = "Outstanding"
                status_class = "outstanding"
            else:
                status_label = a.state.capitalize()
                status_class = ""
            accrual_lines.append({
                "accrual_date": self._format_stmt_date(a.accrual_date),
                "period_start": self._format_stmt_date(a.period_start),
                "period_end": self._format_stmt_date(a.period_end),
                "opening_balance_fmt": self._format_amount(a.opening_balance, currency),
                "interest_amount_fmt": self._format_amount(a.interest_amount, currency),
                "closing_balance_fmt": self._format_amount(a.closing_balance, currency),
                "status": status_label,
                "status_class": status_class,
            })

        # ── Payout detail table ────────────────────────────────────────────────
        payout_lines = []
        for p in period_payouts.sorted(key=lambda x: x.payout_date):
            linked_accruals = p.accrual_ids.sorted(key=lambda a: a.period_start)
            if linked_accruals:
                accrual_range = "%s to %s" % (
                    self._format_stmt_date(linked_accruals[0].period_start),
                    self._format_stmt_date(linked_accruals[-1].period_end),
                )
            else:
                accrual_range = "\u2014"
            payment_ref = p.payment_id.name if p.payment_id else "\u2014"
            payout_lines.append({
                "payout_date": self._format_stmt_date(p.payout_date),
                "reference": p.name,
                "accrual_range": accrual_range,
                "gross_interest_fmt": self._format_amount(p.gross_interest, currency),
                "wht_deducted_fmt": self._format_amount(p.wht_amount, currency),
                "net_paid_fmt": self._format_amount(p.net_amount, currency),
                "payment_ref": payment_ref,
            })

        # ── Top-Up detail table ────────────────────────────────────────────────
        period_topups = self.env["alba.investment.topup"].search([
            ("investor_id", "=", investor.id),
            ("state", "=", "posted"),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ])
        topup_lines = []
        for t in period_topups.sorted(key=lambda x: x.date):
            topup_lines.append({
                "date": self._format_stmt_date(t.date),
                "reference": t.name,
                "amount_fmt": self._format_amount(t.amount, currency),
                "status": t.state.capitalize(),
            })

        # ── Withdrawal detail table ────────────────────────────────────────────
        withdrawal_lines = []
        for inv in investments:
            if getattr(inv, "withdrawal_payment_id", None):
                wd = inv.withdrawal_payment_id
                wd_date = wd.date
                if wd_date and date_from <= wd_date <= date_to:
                    gross_wd = (
                        inv.principal_amount
                        + inv.total_topup_amount
                        + inv.total_interest_outstanding
                    )
                    withdrawal_lines.append({
                        "date": self._format_stmt_date(wd_date),
                        "reference": wd.name or "\u2014",
                        "investment_number": inv.investment_number or "\u2014",
                        "principal_fmt": self._format_amount(inv.principal_amount, currency),
                        "topups_fmt": self._format_amount(inv.total_topup_amount, currency),
                        "interest_fmt": self._format_amount(inv.total_interest_outstanding, currency),
                        "gross_fmt": self._format_amount(gross_wd, currency),
                    })

        return {
            "doc": investor,
            "partner": partner,
            "customer_name": self._clean_string(partner.name if partner else ""),
            "customer_address": self._clean_string(self._partner_address(partner)),
            "account_number": self._clean_string(account_number),
            "barcode_number": self._clean_string(account_number),
            "product_name": self._clean_string(self._product_label(investor=investor)),
            "date_from": self._format_stmt_date(date_from),
            "date_to": self._format_stmt_date(date_to),
            "statement_date": self._format_stmt_date(date_to),
            "branch_name": self._clean_string(company.name),
            "res_company": company,
            "currency": currency,
            "lines": lines,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "total_debit_fmt": self._format_amount(total_debit, currency),
            "total_credit_fmt": self._format_amount(total_credit, currency),
            # ── Summary box keys ─────────────────────────────────────────────
            "opening_balance_fmt": self._format_amount(opening_balance, currency),
            "deposits_fmt": self._format_amount(deposits, currency),
            "withdrawals_fmt": self._format_amount(principal_withdrawals, currency),
            "interest_accrued_fmt": self._format_amount(interest_accrued, currency),
            # From actual payout records — no flat-rate estimates
            "total_gross_paid_fmt": self._format_amount(total_gross_paid, currency),
            "total_wht_deducted_fmt": self._format_amount(total_wht_deducted, currency),
            "total_net_paid_fmt": self._format_amount(total_net_paid, currency),
            "interest_outstanding_fmt": self._format_amount(interest_outstanding, currency),
            "closing_balance_fmt": self._format_amount(balance, currency),
            "wht_rate": wht_rate,
            # ── Detail tables ────────────────────────────────────────────────
            "accrual_lines": accrual_lines,
            "payout_lines": payout_lines,
            "topup_lines": topup_lines,
            "withdrawal_lines": withdrawal_lines,
        }
