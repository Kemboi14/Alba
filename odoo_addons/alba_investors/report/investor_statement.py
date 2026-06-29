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
        
        # A) Initial Deposits
        for inv in investments:
            dt = inv.start_date
            transactions.append({
                "date": dt,
                "type": "deposit",
                "description": f"Initial Deposit - {inv.investment_number}",
                "amount": inv.principal_amount,
                "record": inv,
            })
            
        # B) Top-Ups
        topups = self.env["alba.investment.topup"].search([
            ("investor_id", "=", investor.id),
            ("state", "=", "posted")
        ])
        for t in topups:
            transactions.append({
                "date": t.date,
                "type": "topup",
                "description": f"Top-Up - {t.name}",
                "amount": t.amount,
                "record": t,
            })
            
        # C) Interest Accruals  (include 'paid' so paid-out periods still appear)
        accruals = self.env["alba.interest.accrual"].search([
            ("investor_id", "=", investor.id),
            ("state", "in", ["posted", "paid"])
        ])
        for a in accruals:
            inv_num = a.investment_id.investment_number or ""
            transactions.append({
                "date": a.accrual_date,
                "type": "accrual",
                "description": self._accrual_description(a, inv_num),
                "amount": a.interest_amount,
                "record": a,
            })
            
        # D) Interest Payouts
        payouts = self.env["alba.interest.payout"].search([
            ("investor_id", "=", investor.id),
            ("state", "=", "posted")
        ])
        for p in payouts:
            transactions.append({
                "date": p.payout_date,
                "type": "payout",
                "description": f"Interest Payout - {p.name}",
                "amount": -p.gross_interest,
                "record": p,
            })
            
        # E) Withdrawals / Payoffs
        for inv in investments.filtered(lambda i: i.state == "withdrawn" and i.withdrawal_payment_id):
            dt = inv.withdrawal_payment_id.date
            gross_withdrawal = inv.principal_amount + inv.total_topup_amount + inv.total_interest_outstanding
            transactions.append({
                "date": dt,
                "type": "withdrawal",
                "description": f"Investment Payoff/Withdrawal - {inv.investment_number}",
                "amount": -gross_withdrawal,
                "record": inv,
            })
            
        # Sort all transactions chronologically
        transactions.sort(key=lambda x: x["date"])
        
        prior_txs = [t for t in transactions if t["date"] < date_from]
        period_txs = [t for t in transactions if date_from <= t["date"] <= date_to]
        
        opening_balance = sum(t["amount"] for t in prior_txs)
        
        currency = investor.currency_id or self.env.company.currency_id
        account_number = investor.investor_number or ""
        company = investor.company_id or self.env.company
        _logger.debug("Investor %s company=%s logo=%s logo_web=%s", investor.investor_name, bool(company.logo), bool(company.logo_web))
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

        deposits = 0.0
        withdrawals = 0.0
        interest_accrued = 0.0
        
        for tx in period_txs:
            balance += tx["amount"]
            
            is_debit = tx["amount"] < 0
            debit_amt = abs(tx["amount"]) if is_debit else 0.0
            credit_amt = tx["amount"] if not is_debit else 0.0
            
            if tx["type"] in ("deposit", "topup"):
                deposits += tx["amount"]
            elif tx["type"] in ("withdrawal", "payout"):
                withdrawals += abs(tx["amount"])
            elif tx["type"] == "accrual":
                interest_accrued += tx["amount"]

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

        wht_rate = investments[0].wht_rate if investments else 15.0
        wht_amount = interest_accrued * (wht_rate / 100.0)
        net_interest = interest_accrued - wht_amount

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
            "opening_balance_fmt": self._format_amount(opening_balance, currency),
            "deposits_fmt": self._format_amount(deposits, currency),
            "withdrawals_fmt": self._format_amount(withdrawals, currency),
            "interest_accrued_fmt": self._format_amount(interest_accrued, currency),
            "wht_amount_fmt": self._format_amount(wht_amount, currency),
            "net_interest_fmt": self._format_amount(net_interest, currency),
            "closing_balance_fmt": self._format_amount(balance, currency),
            "wht_rate": wht_rate,
        }
