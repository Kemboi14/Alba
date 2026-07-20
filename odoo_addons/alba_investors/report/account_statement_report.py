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
    def _statement_event_type_priority(self, event_type):
        priority_map = {
            "deposit": 0,
            "topup": 0,
            "top_up": 0,
            "accrual": 1,
            "interest": 1,
            "payout": 2,
            "withdrawal": 2,
        }
        return priority_map.get((event_type or "").lower(), 99)

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

    # =========================================================================
    # Human-readable event descriptions
    # =========================================================================

    @api.model
    def _desc_initial_deposit(self, investment):
        """Clear description for the initial principal deposit."""
        inv_num = getattr(investment, "investment_number", "") or ""
        start = self._format_stmt_date(getattr(investment, "start_date", None))
        return "Initial Deposit — Inv. %s (Start Date: %s)" % (inv_num, start)

    @api.model
    def _desc_topup(self, topup, investment):
        """Clear description for a top-up deposit."""
        ref = topup.name or ""
        inv_num = getattr(investment, "investment_number", "") or ""
        topup_date = self._format_stmt_date(topup.date)
        return "Top-Up Deposit — %s / Inv. %s (Date: %s)" % (ref, inv_num, topup_date)

    @api.model
    def _desc_accrual(self, accrual, investment):
        """
        Clear description for an interest accrual entry.
        Shows: month, period range, and whether it has been paid out.
        """
        inv_num = getattr(investment, "investment_number", "") or ""
        month_year = accrual.accrual_date.strftime("%b %Y") if accrual.accrual_date else ""
        period = ""
        if accrual.period_start and accrual.period_end:
            period = " (Period: %s to %s)" % (
                self._format_stmt_date(accrual.period_start),
                self._format_stmt_date(accrual.period_end),
            )
        status = ""
        if accrual.state == "paid":
            status = " [PAID OUT]"
        return "Interest Accrual — %s / Inv. %s%s%s" % (month_year, inv_num, period, status)

    @api.model
    def _desc_payout(self, payout, investment):
        """
        Clear description for an interest payout — shows which accrual periods are covered.
        """
        ref = payout.name or ""
        inv_num = getattr(investment, "investment_number", "") or ""
        # Derive the covered accrual period range
        linked_accruals = payout.accrual_ids.sorted(key=lambda a: a.period_start) if payout.accrual_ids else []
        if linked_accruals:
            accrual_range = "%s to %s" % (
                self._format_stmt_date(linked_accruals[0].period_start),
                self._format_stmt_date(linked_accruals[-1].period_end),
            )
            return "Interest Payout — %s / Inv. %s (Covers: %s)" % (ref, inv_num, accrual_range)
        return "Interest Payout — %s / Inv. %s" % (ref, inv_num)

    @api.model
    def _desc_withdrawal(self, investment):
        """Clear description for a principal withdrawal / investment payoff."""
        inv_num = getattr(investment, "investment_number", "") or ""
        pay_ref = ""
        if getattr(investment, "withdrawal_payment_id", None) and investment.withdrawal_payment_id.name:
            pay_ref = " / Payment: %s" % investment.withdrawal_payment_id.name
        return "Investment Withdrawal — Inv. %s (Principal + Outstanding Interest Payoff%s)" % (inv_num, pay_ref)

    # =========================================================================
    # Core event collector
    # =========================================================================

    @api.model
    def collect_investment_statement_events(
        self,
        investment,
        period_start=None,
        period_end=None,
        include_initial_deposit=False,
        env=None,
    ):
        """
        Collect all posted transaction events for an investment within a period.

        Each event dict contains:
            sort_date   : date for sorting
            sort_id     : tie-breaker
            date        : event date (date object)
            type        : 'deposit' | 'topup' | 'accrual' | 'payout' | 'withdrawal'
            type_label  : human-readable badge label for the PDF template
            description : clear, investor-friendly description string
            amount      : signed float (+credit, -debit)
            debit       : absolute debit amount (0 if credit)
            credit      : absolute credit amount (0 if debit)
            record      : the ORM record that produced this event
            accrual_state : (accruals only) 'posted' | 'paid' — for status badge
        """
        if not investment:
            return []

        env = env or self.env
        if not period_start or not period_end:
            return []

        events = []

        # ── 1. Initial principal deposit ─────────────────────────────────────
        if include_initial_deposit and investment.start_date:
            if period_start <= investment.start_date <= period_end:
                amount = investment.principal_amount or 0.0
                events.append({
                    "sort_date": investment.start_date,
                    "sort_id": 0,
                    "date": investment.start_date,
                    "type": "deposit",
                    "type_label": "Initial Deposit",
                    "description": self._desc_initial_deposit(investment),
                    "amount": amount,
                    "debit": 0.0,
                    "credit": amount,
                    "record": investment,
                    "accrual_state": None,
                })

        # ── 2. Top-ups ────────────────────────────────────────────────────────
        topups = env["alba.investment.topup"].search([
            ("investment_id", "=", investment.id),
            ("state", "=", "posted"),
            ("date", ">=", period_start),
            ("date", "<=", period_end),
        ], order="date asc, id asc")
        for topup in topups:
            amount = topup.amount
            events.append({
                "sort_date": topup.date,
                "sort_id": topup.id,
                "date": topup.date,
                "type": "topup",
                "type_label": "Top-Up",
                "description": self._desc_topup(topup, investment),
                "amount": amount,
                "debit": 0.0,
                "credit": amount,
                "record": topup,
                "accrual_state": None,
            })

        # ── 3. Interest accruals ──────────────────────────────────────────────
        # Include both posted (outstanding) and paid accruals so the ledger
        # shows: Credit when earned, then Debit when paid out (via payout event).
        # Filter by the accrual's own period_end (same billing cycle as the statement).
        accruals = env["alba.interest.accrual"].search([
            ("investment_id", "=", investment.id),
            ("state", "in", ["posted", "paid"]),
            ("period_end", ">=", period_start),
            ("period_end", "<=", period_end),
        ], order="accrual_date asc, id asc")
        for accrual in accruals:
            amount = accrual.interest_amount
            events.append({
                "sort_date": accrual.accrual_date,
                "sort_id": accrual.id,
                "date": accrual.accrual_date,
                "type": "accrual",
                "type_label": "Interest Accrual",
                "description": self._desc_accrual(accrual, investment),
                "amount": amount,
                "debit": 0.0,
                "credit": amount,
                "record": accrual,
                "accrual_state": accrual.state,   # 'posted' | 'paid'
            })

        # ── 4. Interest payouts ───────────────────────────────────────────────
        # A payout DEBITS the balance (cash goes OUT to the investor).
        payouts = env["alba.interest.payout"].search([
            ("investment_id", "=", investment.id),
            ("state", "=", "posted"),
            ("payout_date", ">=", period_start),
            ("payout_date", "<=", period_end),
        ], order="payout_date asc, id asc")
        for payout in payouts:
            amount = payout.gross_interest
            events.append({
                "sort_date": payout.payout_date,
                "sort_id": payout.id,
                "date": payout.payout_date,
                "type": "payout",
                "type_label": "Interest Payout",
                "description": self._desc_payout(payout, investment),
                "amount": -amount,
                "debit": amount,
                "credit": 0.0,
                "record": payout,
                "accrual_state": None,
            })

        # ── 5. Investment withdrawal (principal payoff) ───────────────────────
        if getattr(investment, "withdrawal_payment_id", None):
            withdrawal_date = investment.withdrawal_payment_id.date
            if withdrawal_date and period_start <= withdrawal_date <= period_end:
                # Use principal + total top-ups as the withdrawal amount.
                # Outstanding interest should already have been cleared via payouts
                # before the withdrawal is processed; we include it here as a
                # safety net in case interest was settled inside the withdrawal.
                gross_withdrawal = (
                    investment.principal_amount
                    + investment.total_topup_amount
                    + investment.total_interest_outstanding
                )
                events.append({
                    "sort_date": withdrawal_date,
                    "sort_id": getattr(investment, "id", 0),
                    "date": withdrawal_date,
                    "type": "withdrawal",
                    "type_label": "Withdrawal",
                    "description": self._desc_withdrawal(investment),
                    "amount": -gross_withdrawal,
                    "debit": gross_withdrawal,
                    "credit": 0.0,
                    "record": investment,
                    "accrual_state": None,
                })

        # Same-date events must be ordered by logical transaction priority:
        # - A top-up adds to the principal first; it is the basis for accrual.
        # - Accrual/interest is computed on the available principal, so it comes second.
        # - Payout/withdrawal is disbursed from accrued interest, so it comes last.
        events.sort(
            key=lambda item: (
                item["sort_date"],
                self._statement_event_type_priority(item.get("type")),
                item["sort_id"],
            )
        )
        return events

    # =========================================================================
    # Opening balance helper — correct for BOTH fresh and ongoing investments
    # =========================================================================

    @api.model
    def _compute_investment_opening_balance(self, investment, period_start, env=None):
        """
        Return the correct opening balance for an investment as of period_start.

        Formula:
            principal
            + all posted top-ups BEFORE period_start
            + all posted/paid accruals BEFORE period_start
            - all posted payouts BEFORE period_start
            - principal + topups if already withdrawn BEFORE period_start
        """
        env = env or self.env

        prior_topups = env["alba.investment.topup"].search([
            ("investment_id", "=", investment.id),
            ("state", "=", "posted"),
            ("date", "<", period_start),
        ])
        prior_accruals = env["alba.interest.accrual"].search([
            ("investment_id", "=", investment.id),
            ("state", "in", ["posted", "paid"]),
            ("accrual_date", "<", period_start),
        ])
        prior_payouts = env["alba.interest.payout"].search([
            ("investment_id", "=", investment.id),
            ("state", "=", "posted"),
            ("payout_date", "<", period_start),
        ])

        prior_withdrawals = 0.0
        if getattr(investment, "withdrawal_payment_id", None):
            pay_date = investment.withdrawal_payment_id.date
            if pay_date and pay_date < period_start:
                prior_withdrawals = (
                    investment.principal_amount
                    + investment.total_topup_amount
                    + investment.total_interest_outstanding
                )

        return (
            investment.principal_amount
            + sum(prior_topups.mapped("amount"))
            + sum(prior_accruals.mapped("interest_amount"))
            - sum(prior_payouts.mapped("gross_interest"))
            - prior_withdrawals
        )

    # =========================================================================
    # Build statement lines from event list
    # =========================================================================

    @api.model
    def _lines_from_statement(self, stmt):
        """
        Build debit/credit/balance lines for an investment statement record.

        Each top-up and each interest payout appears as its own dated line,
        sorted chronologically alongside the interest accrual lines.
        """
        currency = stmt.currency_id
        inv = stmt.investment_id
        lines = []
        balance = stmt.opening_balance

        # ── Opening balance line ───────────────────────────────────────────────
        lines.append({
            "date": self._format_stmt_date(stmt.period_start),
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
                "description": ev["description"],
                "type": ev["type"],
                "type_label": ev["type_label"],
                "debit": ev["debit"],
                "credit": ev["credit"],
                "balance": balance,
                "debit_fmt": self._format_amount(ev["debit"], currency) if ev["debit"] else "",
                "credit_fmt": self._format_amount(ev["credit"], currency) if ev["credit"] else "",
                "balance_fmt": self._format_amount(balance, currency),
                "accrual_state": ev.get("accrual_state"),
            })

        # Fallback: no events but statement has interest accrued total set
        if not events and stmt.interest_accrued:
            balance = stmt.closing_balance
            lines.append({
                "date": self._format_stmt_date(stmt.period_end),
                "description": "Interest Accrual — Period %s to %s" % (
                    self._format_stmt_date(stmt.period_start),
                    self._format_stmt_date(stmt.period_end),
                ),
                "type": "accrual",
                "type_label": "Interest Accrual",
                "debit": 0.0,
                "credit": stmt.interest_accrued,
                "balance": balance,
                "debit_fmt": "",
                "credit_fmt": self._format_amount(stmt.interest_accrued, currency),
                "balance_fmt": self._format_amount(balance, currency),
                "accrual_state": "posted",
            })

        total_debit = sum(line["debit"] for line in lines)
        total_credit = sum(line["credit"] for line in lines)
        return lines, total_debit, total_credit

    # =========================================================================
    # Build payload from an investment statement record
    # =========================================================================

    @api.model
    def _report_payload_from_statement(self, stmt):
        lines, total_debit, total_credit = self._lines_from_statement(stmt)
        company = stmt.company_id or self.env.company
        partner = stmt.partner_id
        currency = stmt.currency_id
        account_number = stmt.investment_id.investment_number or stmt.investor_id.investor_number or ""

        # ── WHT / payout summary from real payout records ─────────────────────
        period_payouts = self.env["alba.interest.payout"].search([
            ("investment_id", "=", stmt.investment_id.id),
            ("state", "=", "posted"),
            ("payout_date", ">=", stmt.period_start),
            ("payout_date", "<=", stmt.period_end),
        ])
        total_gross_paid = sum(period_payouts.mapped("gross_interest"))
        total_wht_deducted = sum(period_payouts.mapped("wht_amount"))
        total_net_paid = sum(period_payouts.mapped("net_amount"))

        # ── Accrual detail table ───────────────────────────────────────────────
        # Filter by the accrual's own period_end so the table is consistent
        # with the statement lines, regardless of which day the accrual was posted.
        period_accruals = self.env["alba.interest.accrual"].search([
            ("investment_id", "=", stmt.investment_id.id),
            ("state", "in", ["posted", "paid"]),
            ("period_end", ">=", stmt.period_start),
            ("period_end", "<=", stmt.period_end),
        ])
        interest_outstanding = sum(
            a.interest_amount for a in period_accruals if a.state == "posted"
        )
        accrual_lines = []
        for a in period_accruals.sorted(key=lambda x: x.accrual_date):
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
            ("investment_id", "=", stmt.investment_id.id),
            ("state", "=", "posted"),
            ("date", ">=", stmt.period_start),
            ("date", "<=", stmt.period_end),
        ])
        topup_lines = []
        for t in period_topups.sorted(key=lambda x: x.date):
            topup_lines.append({
                "date": self._format_stmt_date(t.date),
                "reference": t.name,
                "amount_fmt": self._format_amount(t.amount, currency),
                "status": t.state.capitalize(),
            })

        # ── Withdrawal detail ──────────────────────────────────────────────────
        withdrawal_lines = []
        inv = stmt.investment_id
        if getattr(inv, "withdrawal_payment_id", None):
            wd = inv.withdrawal_payment_id
            wd_date = wd.date
            if wd_date and stmt.period_start <= wd_date <= stmt.period_end:
                gross_wd = (
                    inv.principal_amount
                    + inv.total_topup_amount
                    + inv.total_interest_outstanding
                )
                withdrawal_lines.append({
                    "date": self._format_stmt_date(wd_date),
                    "reference": wd.name or "\u2014",
                    "principal_fmt": self._format_amount(inv.principal_amount, currency),
                    "topups_fmt": self._format_amount(inv.total_topup_amount, currency),
                    "interest_fmt": self._format_amount(inv.total_interest_outstanding, currency),
                    "gross_fmt": self._format_amount(gross_wd, currency),
                })

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
            # Payout summary
            "total_gross_paid_fmt": self._format_amount(total_gross_paid, currency),
            "total_wht_deducted_fmt": self._format_amount(total_wht_deducted, currency),
            "total_net_paid_fmt": self._format_amount(total_net_paid, currency),
            "interest_outstanding_fmt": self._format_amount(interest_outstanding, currency),
            # Detail tables
            "accrual_lines": accrual_lines,
            "payout_lines": payout_lines,
            "topup_lines": topup_lines,
            "withdrawal_lines": withdrawal_lines,
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
