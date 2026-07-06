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
    def _clean_string(self, value):
        if not value:
            return ""
        if isinstance(value, str):
            value = (
                value.replace("—", "-")
                .replace("–", "-")
                .replace("\xa0", " ")
                .replace("\u00a0", " ")
                .replace("\u202f", " ")
            )
        return value

    @api.model
    def _format_stmt_date(self, value):
        if not value:
            return ""
        if isinstance(value, str):
            return self._clean_string(value)
        return value.strftime("%d-%b-%Y")

    @api.model
    def _format_amount(self, amount, currency):
        val = formatLang(
            self.env,
            amount or 0.0,
            currency_obj=currency,
            digits=currency.decimal_places if currency else 2,
        )
        return self._clean_string(val)

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
    def collect_investment_statement_events(
        self,
        investment,
        period_start=None,
        period_end=None,
        include_initial_deposit=False,
        env=None,
    ):
        """Collect all posted transaction events for an investment within a period."""
        if not investment:
            return []

        env = env or self.env
        if not period_start or not period_end:
            return []

        events = []
        if include_initial_deposit and investment.start_date:
            if period_start <= investment.start_date <= period_end:
                events.append({
                    "sort_date": investment.start_date,
                    "date": investment.start_date,
                    "type": "deposit",
                    "description": "Initial Deposit - %s" % (getattr(investment, "investment_number", "") or ""),
                    "amount": investment.principal_amount or 0.0,
                    "record": investment,
                    "debit": 0.0,
                    "credit": investment.principal_amount or 0.0,
                    "sort_id": getattr(investment, "id", 0),
                })

        topups = env["alba.investment.topup"].search([
            ("investment_id", "=", investment.id),
            ("state", "=", "posted"),
            ("date", ">=", period_start),
            ("date", "<=", period_end),
        ], order="date asc, id asc")
        for topup in topups:
            events.append({
                "sort_date": topup.date,
                "date": topup.date,
                "type": "topup",
                "description": "Top-Up - %s" % (topup.name or ""),
                "amount": topup.amount,
                "record": topup,
                "debit": 0.0,
                "credit": topup.amount,
                "sort_id": getattr(topup, "id", 0),
            })

        payouts = env["alba.interest.payout"].search([
            ("investment_id", "=", investment.id),
            ("state", "=", "posted"),
            ("payout_date", ">=", period_start),
            ("payout_date", "<=", period_end),
        ], order="payout_date asc, id asc")
        for payout in payouts:
            events.append({
                "sort_date": payout.payout_date,
                "date": payout.payout_date,
                "type": "payout",
                "description": "Interest Payout - %s" % (payout.name or ""),
                "amount": -payout.gross_interest,
                "record": payout,
                "debit": payout.gross_interest,
                "credit": 0.0,
                "sort_id": getattr(payout, "id", 0),
            })

        accruals = env["alba.interest.accrual"].search([
            ("investment_id", "=", investment.id),
            ("state", "in", ["posted", "paid"]),
            ("accrual_date", ">=", period_start),
            ("accrual_date", "<=", period_end),
        ], order="accrual_date asc, id asc")
        for accrual in accruals:
            events.append({
                "sort_date": accrual.accrual_date,
                "date": accrual.accrual_date,
                "type": "accrual",
                "description": self._accrual_description(accrual, getattr(investment, "investment_number", "") or ""),
                "amount": accrual.interest_amount,
                "record": accrual,
                "debit": 0.0,
                "credit": accrual.interest_amount,
                "sort_id": getattr(accrual, "id", 0),
            })

        if investment.state == "withdrawn" and investment.withdrawal_payment_id:
            withdrawal_date = investment.withdrawal_payment_id.date
            if withdrawal_date and period_start <= withdrawal_date <= period_end:
                gross_withdrawal = (
                    investment.principal_amount
                    + investment.total_topup_amount
                    + investment.total_interest_outstanding
                )
                events.append({
                    "sort_date": withdrawal_date,
                    "date": withdrawal_date,
                    "type": "withdrawal",
                    "description": "Investment Payoff/Withdrawal - %s" % (getattr(investment, "investment_number", "") or ""),
                    "amount": -gross_withdrawal,
                    "record": investment,
                    "debit": gross_withdrawal,
                    "credit": 0.0,
                    "sort_id": getattr(investment, "id", 0),
                })

        events.sort(key=lambda item: (item["sort_date"], item["sort_id"]))
        return events

    @api.model
    def _lines_from_statement(self, stmt):
        """Build debit/credit/balance lines for an investment statement record.

        Each top-up and each interest payout appears as its own dated line,
        sorted chronologically alongside the interest accrual lines.
        """
        currency = stmt.currency_id
        account_number = stmt.investment_id.investment_number or ""
        inv = stmt.investment_id
        lines = []
        balance = stmt.opening_balance

        # ── Opening balance line ───────────────────────────────────────────────
        lines.append({
            "date": self._format_stmt_date(stmt.period_start),
            "description": self._clean_string("OB Opening Balance Period Opening Balance"),
            "debit": 0.0,
            "credit": 0.0,
            "balance": balance,
            "debit_fmt": "",
            "credit_fmt": "",
            "balance_fmt": self._format_amount(balance, currency),
        })

        # ── Individual top-up, payout, accrual and withdrawal lines ─────────
        events = self.collect_investment_statement_events(
            inv,
            period_start=stmt.period_start,
            period_end=stmt.period_end,
            include_initial_deposit=False,
        )

        for ev in events:
            if ev["credit"]:
                balance += ev["credit"]
            else:
                balance -= ev["debit"]
            lines.append({
                "date": self._format_stmt_date(ev["date"]),
                "description": self._clean_string(ev["description"].upper()),
                "debit": ev["debit"],
                "credit": ev["credit"],
                "balance": balance,
                "debit_fmt": self._format_amount(ev["debit"], currency) if ev["debit"] else "",
                "credit_fmt": self._format_amount(ev["credit"], currency) if ev["credit"] else "",
                "balance_fmt": self._format_amount(balance, currency),
            })

        # Fallback: no events but statement has interest accrued total set
        if not events and stmt.interest_accrued:
            balance = stmt.closing_balance
            lines.append({
                "date": self._format_stmt_date(stmt.period_end),
                "description": self._clean_string("ADJUSTMENT Period Interest Earned"),
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
            "customer_name": self._clean_string(partner.name if partner else ""),
            "customer_address": self._clean_string(self._partner_address(partner)),
            "account_number": self._clean_string(account_number),
            "barcode_number": self._clean_string(account_number),
            "product_name": self._clean_string(self._product_label(investment=stmt.investment_id)),
            "date_from": self._format_stmt_date(stmt.period_start),
            "date_to": self._format_stmt_date(stmt.period_end),
            "statement_date": self._format_stmt_date(stmt.statement_date),
            "branch_name": self._clean_string(company.name),
            "res_company": company,
            "currency": currency,
            "lines": lines,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "total_debit_fmt": self._format_amount(total_debit, currency),
            "total_credit_fmt": self._format_amount(total_credit, currency),
            "opening_balance_fmt": self._format_amount(stmt.opening_balance, currency),
            "deposits_fmt": self._format_amount(stmt.deposits, currency),
            "withdrawals_fmt": self._format_amount(stmt.withdrawals, currency),
            "interest_accrued_fmt": self._format_amount(stmt.interest_accrued, currency),
            "wht_amount_fmt": self._format_amount(stmt.wht_amount, currency),
            "net_interest_fmt": self._format_amount(stmt.net_interest, currency),
            "closing_balance_fmt": self._format_amount(stmt.closing_balance, currency),
            "wht_rate": stmt.wht_rate,
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
