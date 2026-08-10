# -*- coding: utf-8 -*-
"""
Alba Capital — Financial Report Wizard Models

Five MFI-specific reports computed on demand:
  • PAR  — Portfolio at Risk (by arrears bucket)
  • NPL  — Non-Performing Loans
  • P&L  — Profit & Loss Statement
  • CF   — Cash Flow Statement
  • BS   — Balance Sheet
"""
from datetime import date

from odoo import _, fields, models
from odoo.exceptions import UserError


# ─────────────────────────────────────────────────────────────────────────────
# 1.  PAR Report
# ─────────────────────────────────────────────────────────────────────────────
class AlbaReportPAR(models.TransientModel):
    _name = "alba.report.par"
    _description = "Portfolio at Risk (PAR) Report"

    as_of_date = fields.Date(
        string="As of Date",
        required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="company_id.currency_id",
        readonly=True,
    )

    def action_print_pdf(self):
        return self.env.ref("alba_loans.action_report_par").report_action(self)

    def get_par_data(self):
        self.ensure_one()
        # This report always reflects the *current* live state — there is
        # no historical point-in-time snapshot of loan states/balances to
        # query. Rather than silently mislabel today's numbers with a past
        # "as of" date, refuse to run for anything but today.
        if self.as_of_date and self.as_of_date != fields.Date.today():
            raise UserError(_(
                "Historical PAR reporting (as of a past date) is not "
                "supported — this report always reflects the current "
                "portfolio state. Please set 'As of Date' to today."
            ))
        # Non-terminal states — "loss" must be included: PAR buckets
        # "91-180" and ">180" (loan.py par_bucket, days_in_arrears > 90) are
        # exactly the same threshold that flips a loan's state to "loss"
        # (loan.py _compute_state). Excluding "loss" here silently zeroed
        # out both of those buckets and understated total_at_risk/npl by
        # the entire loss book.
        loans = self.env["alba.loan"].search([
            ("state", "in", ("normal", "watch", "substandard", "doubtful", "loss")),
            ("company_id", "=", self.company_id.id),
        ])
        total_portfolio = sum(loans.mapped("outstanding_balance")) or 0.0
        # NPL is now defined as substandard, doubtful, or loss
        npl_loans = loans.filtered(lambda l: l.state in ("substandard", "doubtful", "loss"))
        npl_balance = sum(npl_loans.mapped("outstanding_balance"))

        bucket_defs = [
            ("current",  "Current (0 days)"),
            ("1_30",     "PAR 1 – 30 Days"),
            ("31_60",    "PAR 31 – 60 Days"),
            ("61_90",    "PAR 61 – 90 Days"),
            ("91_180",   "PAR 91 – 180 Days"),
            ("over_180", "PAR > 180 Days"),
        ]
        buckets = []
        total_at_risk = 0.0
        for key, label in bucket_defs:
            bl = loans.filtered(lambda l, k=key: l.par_bucket == k)
            balance = sum(bl.mapped("outstanding_balance"))
            arrears = sum(bl.mapped("arrears_amount"))
            if key != "current":
                total_at_risk += balance
            buckets.append({
                "label":               label,
                "count":               len(bl),
                "outstanding_balance": balance,
                "arrears_amount":      arrears,
                "par_pct":             (balance / total_portfolio * 100.0) if total_portfolio else 0.0,
            })

        return {
            "company":         self.company_id,
            "currency":        self.company_id.currency_id,
            "as_of_date":      self.as_of_date,
            "total_loans":     len(loans),
            "total_portfolio": total_portfolio,
            "total_at_risk":   total_at_risk,
            "overall_par_pct": (total_at_risk / total_portfolio * 100.0) if total_portfolio else 0.0,
            "npl_count":       len(npl_loans),
            "npl_balance":     npl_balance,
            "npl_pct":         (npl_balance / total_portfolio * 100.0) if total_portfolio else 0.0,
            "buckets":         buckets,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 2.  NPL Report
# ─────────────────────────────────────────────────────────────────────────────
class AlbaReportNPL(models.TransientModel):
    _name = "alba.report.npl"
    _description = "Non-Performing Loans (NPL) Report"

    as_of_date = fields.Date(
        string="As of Date",
        required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="company_id.currency_id",
        readonly=True,
    )
    include_written_off = fields.Boolean(
        string="Include Written-Off Loans",
        default=False,
    )

    def action_print_pdf(self):
        return self.env.ref("alba_loans.action_report_npl").report_action(self)

    def get_npl_data(self):
        self.ensure_one()
        if self.as_of_date and self.as_of_date != fields.Date.today():
            raise UserError(_(
                "Historical NPL reporting (as of a past date) is not "
                "supported — this report always reflects the current "
                "portfolio state. Please set 'As of Date' to today."
            ))
        Loan = self.env["alba.loan"]
        # NPL defined as substandard, doubtful, or loss
        states = ["substandard", "doubtful", "loss"]
        if self.include_written_off:
            states.append("written_off")

        npl_loans = Loan.search([
            ("state", "in", states),
            ("company_id", "=", self.company_id.id),
        ], order="days_in_arrears desc")

        # Must match get_par_data()'s state list ("loss" included) — the
        # denominator (total_portfolio) has to cover every non-terminal
        # loan the numerator (npl_balance, which already includes "loss")
        # can draw from, otherwise the ratio is inflated by counting a
        # bucket in the numerator that the denominator omits.
        all_active = Loan.search([
            ("state", "in", ("normal", "watch", "substandard", "doubtful", "loss")),
            ("company_id", "=", self.company_id.id),
        ])
        total_portfolio = sum(all_active.mapped("outstanding_balance")) or 0.0

        npl_only     = npl_loans.filtered(lambda l: l.state in ("substandard", "doubtful", "loss"))
        npl_balance  = sum(npl_only.mapped("outstanding_balance"))
        written_off  = npl_loans.filtered(lambda l: l.state == "written_off")

        return {
            "company":            self.company_id,
            "currency":           self.company_id.currency_id,
            "as_of_date":         self.as_of_date,
            "loans":              npl_loans,
            "total_portfolio":    total_portfolio,
            "npl_count":          len(npl_only),
            "npl_balance":        npl_balance,
            "npl_ratio":          (npl_balance / total_portfolio * 100.0) if total_portfolio else 0.0,
            "include_written_off": self.include_written_off,
            "written_off_count":  len(written_off),
            "written_off_balance": sum(written_off.mapped("outstanding_balance")),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Profit & Loss Report
# ─────────────────────────────────────────────────────────────────────────────
class AlbaReportPL(models.TransientModel):
    _name = "alba.report.pl"
    _description = "Profit & Loss Report"

    date_from = fields.Date(
        string="From",
        required=True,
        default=lambda self: date(date.today().year, date.today().month, 1),
    )
    date_to = fields.Date(
        string="To",
        required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="company_id.currency_id",
        readonly=True,
    )

    def action_print_pdf(self):
        return self.env.ref("alba_loans.action_report_pl").report_action(self)

    def get_pl_data(self):
        self.ensure_one()
        Repayment = self.env["alba.loan.repayment"]

        repayments = Repayment.search([
            ("payment_date", ">=", self.date_from),
            ("payment_date", "<=", self.date_to),
            ("state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
        ])

        interest_income = sum(repayments.mapped("interest_component"))
        fees_income     = sum(repayments.mapped("fees_component"))
        penalty_income  = sum(repayments.mapped("penalty_component"))
        total_income    = interest_income + fees_income + penalty_income

        # Investor interest expense and provision for losses are P&L *flows*
        # for this period, not the current cumulative balance — summing the
        # live accrued_interest/provision_amount snapshot (as before) gave
        # the exact same "expense" for every period regardless of length.
        # Instead, sum the actual posted journal-entry movements that hit
        # each expense account within [date_from, date_to] — the same
        # entries created by the interest accrual cron (alba_investors) and
        # by action_post_provisioning_entry (alba_loans).
        AccountMoveLine = self.env["account.move.line"]

        interest_expense_accounts = self.env["alba.investment.product"].search([
            ("account_interest_expense_id", "!=", False),
        ]).mapped("account_interest_expense_id")
        if interest_expense_accounts:
            investor_interest_exp = sum(AccountMoveLine.search([
                ("account_id", "in", interest_expense_accounts.ids),
                ("move_id.state", "=", "posted"),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("company_id", "=", self.company_id.id),
            ]).mapped(lambda l: l.debit - l.credit))
        else:
            investor_interest_exp = 0.0

        provision_expense_accounts = self.env["alba.loan.product"].search([
            ("account_provision_expense_id", "!=", False),
        ]).mapped("account_provision_expense_id")
        if provision_expense_accounts:
            provision_for_losses = sum(AccountMoveLine.search([
                ("account_id", "in", provision_expense_accounts.ids),
                ("move_id.state", "=", "posted"),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("company_id", "=", self.company_id.id),
            ]).mapped(lambda l: l.debit - l.credit))
        else:
            provision_for_losses = 0.0

        total_expenses = investor_interest_exp + provision_for_losses
        net_profit     = total_income - total_expenses

        # Revenue breakdown by loan product
        products = {}
        for rep in repayments:
            prod = rep.loan_product_id.name or "General"
            if prod not in products:
                products[prod] = {
                    "name":     prod,
                    "interest": 0.0,
                    "fees":     0.0,
                    "penalty":  0.0,
                    "total":    0.0,
                }
            products[prod]["interest"] += rep.interest_component
            products[prod]["fees"]     += rep.fees_component
            products[prod]["penalty"]  += rep.penalty_component
            products[prod]["total"]    += (
                rep.interest_component + rep.fees_component + rep.penalty_component
            )

        return {
            "company":              self.company_id,
            "currency":             self.company_id.currency_id,
            "date_from":            self.date_from,
            "date_to":              self.date_to,
            "repayment_count":      len(repayments),
            "interest_income":      interest_income,
            "fees_income":          fees_income,
            "penalty_income":       penalty_income,
            "total_income":         total_income,
            "investor_interest_exp": investor_interest_exp,
            "provision_for_losses": provision_for_losses,
            "total_expenses":       total_expenses,
            "net_profit":           net_profit,
            "is_profit":            net_profit >= 0,
            "products":             sorted(products.values(), key=lambda p: p["total"], reverse=True),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Cash Flow Statement
# ─────────────────────────────────────────────────────────────────────────────
class AlbaReportCashFlow(models.TransientModel):
    _name = "alba.report.cashflow"
    _description = "Cash Flow Statement"

    date_from = fields.Date(
        string="From",
        required=True,
        default=lambda self: date(date.today().year, date.today().month, 1),
    )
    date_to = fields.Date(
        string="To",
        required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="company_id.currency_id",
        readonly=True,
    )

    def action_print_pdf(self):
        return self.env.ref("alba_loans.action_report_cashflow").report_action(self)

    def get_cashflow_data(self):
        self.ensure_one()
        Repayment = self.env["alba.loan.repayment"]
        Loan      = self.env["alba.loan"]

        repayments = Repayment.search([
            ("payment_date", ">=", self.date_from),
            ("payment_date", "<=", self.date_to),
            ("state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
        ])
        total_collected     = sum(repayments.mapped("amount_paid"))
        principal_collected = sum(repayments.mapped("principal_component"))
        interest_collected  = sum(repayments.mapped("interest_component"))
        fees_collected      = (
            sum(repayments.mapped("fees_component")) +
            sum(repayments.mapped("penalty_component"))
        )

        disbursed_loans = Loan.search([
            ("disbursement_date", ">=", self.date_from),
            ("disbursement_date", "<=", self.date_to),
            ("company_id", "=", self.company_id.id),
        ])
        total_disbursed = sum(disbursed_loans.mapped("principal_amount"))
        net_cash        = total_collected - total_disbursed

        return {
            "company":            self.company_id,
            "currency":           self.company_id.currency_id,
            "date_from":          self.date_from,
            "date_to":            self.date_to,
            "repayment_count":    len(repayments),
            "total_collected":    total_collected,
            "principal_collected": principal_collected,
            "interest_collected": interest_collected,
            "fees_collected":     fees_collected,
            "disbursed_count":    len(disbursed_loans),
            "total_disbursed":    total_disbursed,
            "net_cash":           net_cash,
            "is_positive":        net_cash >= 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5.  Balance Sheet
# ─────────────────────────────────────────────────────────────────────────────
class AlbaReportBalanceSheet(models.TransientModel):
    _name = "alba.report.balance.sheet"
    _description = "Balance Sheet Report"

    as_of_date = fields.Date(
        string="As of Date",
        required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="company_id.currency_id",
        readonly=True,
    )

    def action_print_pdf(self):
        return self.env.ref("alba_loans.action_report_balance_sheet").report_action(self)

    def get_balance_sheet_data(self):
        self.ensure_one()
        if self.as_of_date and self.as_of_date != fields.Date.today():
            raise UserError(_(
                "Historical Balance Sheet reporting (as of a past date) is "
                "not supported — this report always reflects the current "
                "portfolio and investor state. Please set 'As of Date' to "
                "today."
            ))
        Loan     = self.env["alba.loan"]
        Investor = self.env["alba.investor"]

        # Performing loans: normal, watch
        active_loans = Loan.search([
            ("state", "in", ("normal", "watch")),
            ("company_id", "=", self.company_id.id),
        ])
        # NPL loans: substandard, doubtful, loss
        npl_loans = Loan.search([
            ("state", "in", ("substandard", "doubtful", "loss")),
            ("company_id", "=", self.company_id.id),
        ])

        gross_portfolio    = (
            sum(active_loans.mapped("outstanding_balance")) +
            sum(npl_loans.mapped("outstanding_balance"))
        )
        all_loans = active_loans | npl_loans
        specific_provision = sum(all_loans.mapped("provision_amount"))
        net_portfolio      = gross_portfolio - specific_provision

        investors                = Investor.search([("state", "in", ("active", "suspended"))])
        investor_deposits        = sum(investors.mapped("principal_amount"))
        investor_accrued_interest = sum(investors.mapped("accrued_interest"))
        total_liabilities        = investor_deposits + investor_accrued_interest

        net_equity = net_portfolio - total_liabilities

        return {
            "company":                  self.company_id,
            "currency":                 self.company_id.currency_id,
            "as_of_date":               self.as_of_date,
            "active_loan_count":        len(active_loans),
            "npl_loan_count":           len(npl_loans),
            "gross_portfolio":          gross_portfolio,
            "specific_provision":       specific_provision,
            "net_portfolio":            net_portfolio,
            "investor_count":           len(investors),
            "investor_deposits":        investor_deposits,
            "investor_accrued_interest": investor_accrued_interest,
            "total_liabilities":        total_liabilities,
            "net_equity":               net_equity,
            "is_solvent":               net_equity >= 0,
        }
