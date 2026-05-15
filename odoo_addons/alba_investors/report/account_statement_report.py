# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, models
from odoo.tools import formatLang

PRODUCT_LABELS = {
    "fixed_term": "Fixed Term Investment",
    "open_ended": "Open Ended Investment",
    "fixed_deposit": "Fixed Deposit",
    "savings": "Savings Account",
    "term_deposit": "Term Deposit",
}


class AccountStatementReportMixin(models.AbstractModel):
    _name = "alba.account.statement.report.mixin"
    _description = "Shared investor account statement helpers"

    @api.model
    def _format_stmt_date(self, value):
        if not value:
            return ""
        if isinstance(value, str):
            return value
        return value.strftime("%d-%b-%Y")

    @api.model
    def _format_amount(self, amount, currency):
        return formatLang(
            self.env,
            amount or 0.0,
            currency_obj=currency,
            digits=currency.decimal_places if currency else 2,
        )

    @api.model
    def _partner_address(self, partner):
        if not partner:
            return ""
        parts = [
            partner.street,
            partner.street2,
            partner.city,
            partner.zip,
            partner.country_id.name if partner.country_id else None,
        ]
        address = ", ".join(p for p in parts if p)
        return address or partner.id_number or ""

    @api.model
    def _product_label(self, investment=None, investor=None):
        if investment:
            return "Investments Received"
        if investor and investor.investment_product:
            return dict(
                investor._fields["investment_product"].selection
            ).get(investor.investment_product, "Investments Received")
        return "Investments Received"

    @api.model
    def _accrual_description(self, accrual, account_number):
        month_year = accrual.accrual_date.strftime("%B %Y") if accrual.accrual_date else ""
        return (
            "ADJUSTMENT %(month)s interest Earned %(account)s/SAV-REC: %(account)s/"
            % {"month": month_year, "account": account_number or ""}
        )

    @api.model
    def _lines_from_statement(self, stmt):
        """Build debit/credit/balance lines for an investment statement record."""
        currency = stmt.currency_id
        account_number = stmt.investment_id.investment_number or ""
        lines = []
        balance = stmt.opening_balance

        lines.append({
            "date": self._format_stmt_date(stmt.period_start),
            "description": "OB Opening Balance Period Opening Balance",
            "debit": 0.0,
            "credit": 0.0,
            "balance": balance,
            "debit_fmt": "",
            "credit_fmt": "",
            "balance_fmt": self._format_amount(balance, currency),
        })

        Transaction = self.env["alba.investor.transaction"]
        if Transaction._name in self.env:
            transactions = Transaction.search([
                ("investor_id", "=", stmt.investor_id.id),
                ("date", ">=", stmt.period_start),
                ("date", "<=", stmt.period_end),
            ], order="date asc, id asc")
            for tx in transactions:
                amount = abs(tx.amount)
                if tx.transaction_type in ("withdrawal",) or tx.amount < 0:
                    balance -= amount
                    lines.append({
                        "date": self._format_stmt_date(tx.date),
                        "description": (tx.description or tx.reference or "WITHDRAWAL").upper(),
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
                        "description": (tx.description or tx.reference or "DEPOSIT").upper(),
                        "debit": 0.0,
                        "credit": amount,
                        "balance": balance,
                        "debit_fmt": "",
                        "credit_fmt": self._format_amount(amount, currency),
                        "balance_fmt": self._format_amount(balance, currency),
                    })

        if stmt.withdrawals and not any(l.get("debit") for l in lines[1:]):
            balance -= stmt.withdrawals
            lines.append({
                "date": self._format_stmt_date(stmt.period_end),
                "description": "WITHDRAWAL Investment Withdrawal",
                "debit": stmt.withdrawals,
                "credit": 0.0,
                "balance": balance,
                "debit_fmt": self._format_amount(stmt.withdrawals, currency),
                "credit_fmt": "",
                "balance_fmt": self._format_amount(balance, currency),
            })

        if stmt.deposits:
            balance += stmt.deposits
            lines.append({
                "date": self._format_stmt_date(stmt.period_end),
                "description": "DEPOSIT Investment Deposit",
                "debit": 0.0,
                "credit": stmt.deposits,
                "balance": balance,
                "debit_fmt": "",
                "credit_fmt": self._format_amount(stmt.deposits, currency),
                "balance_fmt": self._format_amount(balance, currency),
            })

        for accrual in stmt.accrual_ids.sorted("accrual_date"):
            balance = accrual.closing_balance
            credit = accrual.interest_amount
            lines.append({
                "date": self._format_stmt_date(accrual.accrual_date),
                "description": self._accrual_description(accrual, account_number),
                "debit": 0.0,
                "credit": credit,
                "balance": balance,
                "debit_fmt": "",
                "credit_fmt": self._format_amount(credit, currency),
                "balance_fmt": self._format_amount(balance, currency),
            })

        if not stmt.accrual_ids and stmt.interest_accrued:
            balance = stmt.closing_balance
            lines.append({
                "date": self._format_stmt_date(stmt.period_end),
                "description": "ADJUSTMENT Period Interest Earned",
                "debit": 0.0,
                "credit": stmt.interest_accrued,
                "balance": balance,
                "debit_fmt": "",
                "credit_fmt": self._format_amount(stmt.interest_accrued, currency),
                "balance_fmt": self._format_amount(balance, currency),
            })

        total_debit = sum(line["debit"] for line in lines)
        total_credit = sum(line["credit"] for line in lines)
        return lines, total_debit, total_credit

    @api.model
    def _report_payload_from_statement(self, stmt):
        lines, total_debit, total_credit = self._lines_from_statement(stmt)
        company = stmt.company_id or self.env.company
        partner = stmt.partner_id
        currency = stmt.currency_id
        account_number = stmt.investment_id.investment_number or stmt.investor_id.investor_number or ""
        return {
            "doc": stmt,
            "partner": partner,
            "customer_name": partner.name if partner else "",
            "customer_address": self._partner_address(partner),
            "account_number": account_number,
            "barcode_number": account_number,
            "product_name": self._product_label(investment=stmt.investment_id),
            "date_from": self._format_stmt_date(stmt.period_start),
            "date_to": self._format_stmt_date(stmt.period_end),
            "statement_date": self._format_stmt_date(stmt.statement_date),
            "branch_name": company.name,
            "res_company": company,
            "currency": currency,
            "lines": lines,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "total_debit_fmt": self._format_amount(total_debit, currency),
            "total_credit_fmt": self._format_amount(total_credit, currency),
        }


class ReportInvestmentStatement(models.AbstractModel):
    _name = "report.alba_investors.report_investment_statement_template"
    _description = "Investment Account Statement"
    _inherit = "alba.account.statement.report.mixin"

    @api.model
    def _get_report_values(self, docids, data=None):
        statements = self.env["alba.investment.statement"].browse(docids)
        payloads = [self._report_payload_from_statement(stmt) for stmt in statements]
        return {
            "doc_ids": docids,
            "doc_model": "alba.investment.statement",
            "docs": statements,
            "statements": payloads,
        }
