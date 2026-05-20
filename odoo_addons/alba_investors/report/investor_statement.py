# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, models


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
            ("state", "=", "active"),
        ])
        if not investments:
            investments = self.env["alba.investment"].search([
                ("investor_id", "=", investor.id),
            ], limit=1)

        accruals = self.env["alba.interest.accrual"].search([
            ("investor_id", "=", investor.id),
            ("accrual_date", ">=", date_from),
            ("accrual_date", "<=", date_to),
            ("state", "=", "posted"),
        ], order="accrual_date asc")

        prior_accruals = self.env["alba.interest.accrual"].search([
            ("investor_id", "=", investor.id),
            ("accrual_date", "<", date_from),
            ("state", "=", "posted"),
        ])
        principal = sum(investments.mapped("principal_amount"))
        opening_balance = principal + sum(prior_accruals.mapped("interest_amount"))

        currency = investor.currency_id or self.env.company.currency_id
        account_number = investor.investor_number or ""
        company = investor.company_id or self.env.company
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

        Transaction = self.env["alba.investor.transaction"]
        tx_list = []
        if Transaction._name in self.env:
            tx_list = Transaction.search([
                ("investor_id", "=", investor.id),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
            ], order="date asc, id asc")
            for tx in tx_list:
                amount = abs(tx.amount)
                if tx.transaction_type in ("withdrawal",) or tx.amount < 0:
                    balance -= amount
                    lines.append({
                        "date": self._format_stmt_date(tx.date),
                        "description": self._clean_string((tx.description or tx.reference or "REFUND Investment Refund").upper()),
                        "debit": amount,
                        "credit": 0.0,
                        "balance": balance,
                        "debit_fmt": self._format_amount(amount, currency),
                        "credit_fmt": "",
                        "balance_fmt": self._format_amount(balance, currency),
                    })
                else:
                    balance += amount
                    lines.append({
                        "date": self._format_stmt_date(tx.date),
                        "description": self._clean_string((tx.description or tx.reference or "DEPOSIT").upper()),
                        "debit": 0.0,
                        "credit": amount,
                        "balance": balance,
                        "debit_fmt": "",
                        "credit_fmt": self._format_amount(amount, currency),
                        "balance_fmt": self._format_amount(balance, currency),
                    })

        for accrual in accruals:
            balance = accrual.closing_balance
            credit = accrual.interest_amount
            inv_num = accrual.investment_id.investment_number or account_number
            lines.append({
                "date": self._format_stmt_date(accrual.accrual_date),
                "description": self._clean_string(self._accrual_description(accrual, inv_num)),
                "debit": 0.0,
                "credit": credit,
                "balance": balance,
                "debit_fmt": "",
                "credit_fmt": self._format_amount(credit, currency),
                "balance_fmt": self._format_amount(balance, currency),
            })

        total_debit = sum(line["debit"] for line in lines)
        total_credit = sum(line["credit"] for line in lines)

        # Calculate Financial Summary Values Consolidated
        wht_rate = investments[0].wht_rate if investments else 15.0
        interest_accrued = sum(accruals.mapped("interest_amount"))
        wht_amount = interest_accrued * (wht_rate / 100.0)
        net_interest = interest_accrued - wht_amount
        
        deposits = sum(tx.amount for tx in tx_list if tx.transaction_type != 'withdrawal' and tx.amount > 0)
        withdrawals = sum(abs(tx.amount) for tx in tx_list if tx.transaction_type == 'withdrawal' or tx.amount < 0)

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
