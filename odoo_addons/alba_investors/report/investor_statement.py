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
        """Aggregate statement lines across the investor's active investments."""
        if isinstance(date_from, str):
            date_from = date.fromisoformat(date_from)
        if isinstance(date_to, str):
            date_to = date.fromisoformat(date_to)

        investments = self.env["alba.investment"].search([
            ("investor_id", "=", investor.id),
            ("state", "!=", "draft"),
        ])

        transactions = []

        for inv in investments:
            for event in self.collect_investment_statement_events(
                inv,
                period_start=date_from,
                period_end=date_to,
                include_initial_deposit=True,
            ):
                transactions.append({
                    "date": event["date"],
                    "type": event["type"],
                    "description": event["description"],
                    "amount": event["amount"],
                    "record": event["record"],
                })

        # Sort all transactions chronologically
        transactions.sort(key=lambda x: x["date"])

        prior_txs = [t for t in transactions if t["date"] < date_from]
        period_txs = [t for t in transactions if date_from <= t["date"] <= date_to]

        opening_balance = sum(t["amount"] for t in prior_txs)

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
            "description": self._clean_string("OB Opening Balance Period Opening Balance"),
            "debit": 0.0,
            "credit": 0.0,
            "balance": balance,
            "debit_fmt": "",
            "credit_fmt": "",
            "balance_fmt": self._format_amount(balance, currency),
        })

        # ── Summary accumulators ──────────────────────────────────────────────
        deposits = 0.0
        # "withdrawals" = ONLY real principal payoffs, NEVER interest payouts
        principal_withdrawals = 0.0
        interest_accrued = 0.0

        for tx in period_txs:
            balance += tx["amount"]

            is_debit = tx["amount"] < 0
            debit_amt = abs(tx["amount"]) if is_debit else 0.0
            credit_amt = tx["amount"] if not is_debit else 0.0

            if tx["type"] in ("deposit", "topup"):
                deposits += tx["amount"]
            elif tx["type"] == "withdrawal":
                # Only PRINCIPAL withdrawals (investment payoff) count here.
                # Interest payouts (type=="payout") are tracked separately below.
                principal_withdrawals += abs(tx["amount"])
            elif tx["type"] == "accrual":
                interest_accrued += tx["amount"]
            # "payout" deliberately excluded from both deposits and withdrawals

            lines.append({
                "date": self._format_stmt_date(tx["date"]),
                "description": self._clean_string(tx["description"].upper()),
                "debit": debit_amt,
                "credit": credit_amt,
                "balance": balance,
                "debit_fmt": self._format_amount(debit_amt, currency) if is_debit else "",
                "credit_fmt": self._format_amount(credit_amt, currency) if not is_debit else "",
                "balance_fmt": self._format_amount(balance, currency),
            })

        total_debit = sum(line["debit"] for line in lines)
        total_credit = sum(line["credit"] for line in lines)

        # ── WHT / Net Interest — sourced ONLY from real payout records ─────────
        # WHT is deducted only when a payout actually happens.  We NEVER apply
        # a flat rate to unpaid accrued interest — that would be a phantom figure.
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

        # WHT rate kept for the column label only — no longer used for computation
        wht_rate = investments[0].wht_rate if investments else 0.0

        # ── Accrual detail table ───────────────────────────────────────────────
        accrual_lines = []
        for a in period_accruals_in_range.sorted(key=lambda x: x.accrual_date):
            if a.state == "paid":
                status_label = "Paid Out"
            elif a.state == "posted":
                status_label = "Outstanding"
            else:
                status_label = a.state.capitalize()
            accrual_lines.append({
                "accrual_date": self._format_stmt_date(a.accrual_date),
                "period_start": self._format_stmt_date(a.period_start),
                "period_end": self._format_stmt_date(a.period_end),
                "opening_balance_fmt": self._format_amount(a.opening_balance, currency),
                "interest_amount_fmt": self._format_amount(a.interest_amount, currency),
                "closing_balance_fmt": self._format_amount(a.closing_balance, currency),
                "status": status_label,
            })

        # ── Payout detail table ────────────────────────────────────────────────
        payout_lines = []
        for p in period_payouts.sorted(key=lambda x: x.payout_date):
            # Derive covered period range from linked accruals
            linked_accruals = p.accrual_ids.sorted(key=lambda a: a.period_start)
            if linked_accruals:
                accrual_range = "%s \u2013 %s" % (
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
            # Withdrawals = ONLY real principal payoffs, never interest payouts
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
        }
