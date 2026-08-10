# -*- coding: utf-8 -*-
import json
from datetime import date, timedelta

from odoo import _, api, fields, models


class AlbaInvestorDashboard(models.TransientModel):
    _name = "alba.investor.dashboard"
    _description = "Dashboard"
    _rec_name = "name"

    name = fields.Char(string="Name", default="Dashboard")

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
    group_by = fields.Selection(
        selection=[
            ("investment_product", "Investment Product"),
            ("state", "Status"),
            ("investor_type", "Investor Type"),
            ("payout_frequency", "Payout Frequency"),
            ("start_date:month", "Investment Month"),
        ],
        string="Group Investors By",
        default="investment_product",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        readonly=True,
    )

    # KPI Metrics
    investor_count = fields.Integer(compute="_compute_metrics")
    active_investor_count = fields.Integer(compute="_compute_metrics")
    matured_investor_count = fields.Integer(compute="_compute_metrics")
    total_invested_amount = fields.Monetary(currency_field="currency_id", compute="_compute_metrics")
    total_interest_earned = fields.Monetary(currency_field="currency_id", compute="_compute_metrics")
    total_balance = fields.Monetary(currency_field="currency_id", compute="_compute_metrics")
    total_withdrawals = fields.Monetary(currency_field="currency_id", compute="_compute_metrics")
    pending_withdrawals = fields.Integer(compute="_compute_metrics")
    transaction_count = fields.Integer(compute="_compute_metrics")

    # Risk / attention KPIs — point-in-time, not scoped to the disbursement
    # cohort (see _portfolio_domain()) since they answer "what needs
    # attention right now", not "how did this period's cohort turn out".
    outstanding_interest_payable = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_metrics",
        help="Interest accrued on active investments but not yet paid out — "
             "the current interest liability sitting in Interest Payable.",
    )
    maturing_soon_count = fields.Integer(
        compute="_compute_metrics",
        help="Active fixed-term investments maturing within 30 days.",
    )
    maturing_soon_amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_metrics",
        help="Current value of investments maturing within 30 days.",
    )
    kyc_pending_count = fields.Integer(
        compute="_compute_metrics",
        help="Investors whose KYC is not yet verified.",
    )

    # Graph data fields
    investment_composition_data = fields.Text(compute="_compute_graph_data")
    investment_trends_data = fields.Text(compute="_compute_graph_data")
    investor_status_data = fields.Text(compute="_compute_graph_data")
    interest_payout_trends_data = fields.Text(compute="_compute_graph_data")
    withdrawal_analysis_data = fields.Text(compute="_compute_graph_data")
    investor_type_distribution_data = fields.Text(compute="_compute_graph_data")
    investment_amount_distribution_data = fields.Text(compute="_compute_graph_data")
    tenure_distribution_data = fields.Text(compute="_compute_graph_data")
    investor_concentration_data = fields.Text(compute="_compute_graph_data")

    def _investment_domain(self):
        """Cohort domain: investments *started* within the selected period."""
        self.ensure_one()
        return [
            ("company_id", "=", self.company_id.id),
            ("start_date", ">=", self.date_from),
            ("start_date", "<=", self.date_to),
        ]

    def _portfolio_domain(self):
        """
        Point-in-time domain: the full current book of investments, not
        restricted by when an investment started.

        Portfolio-health metrics (balance, outstanding interest, maturity
        risk, pending withdrawals) answer "what does the book look like
        right now" — scoping them to _investment_domain()'s start-date
        cohort made an investment started last year (and still active
        today) invisible the moment the dashboard's default "this month"
        range didn't include its start date.
        """
        self.ensure_one()
        return [("company_id", "=", self.company_id.id)]

    def _investor_domain(self):
        self.ensure_one()
        return [
            ("company_id", "=", self.company_id.id),
        ]

    def _sum_in_dashboard_currency(self, records, field_name):
        """
        Sum a monetary field across records that may be booked in different
        currencies, converting each currency's subtotal to this dashboard's
        currency (company currency) at today's rate before summing.

        Previously these KPIs did a plain sum() across investments
        regardless of currency_id — a USD investment's amount was added to a
        KES investment's amount as if 1 USD == 1 KES.
        """
        self.ensure_one()
        target_currency = self.currency_id or self.company_id.currency_id
        total = 0.0
        by_currency = {}
        for rec in records:
            by_currency.setdefault(rec.currency_id, []).append(rec)
        for currency, recs in by_currency.items():
            subtotal = sum(r[field_name] for r in recs)
            if not currency or currency == target_currency:
                total += subtotal
            else:
                total += currency._convert(
                    subtotal, target_currency, self.company_id, fields.Date.today()
                )
        return total

    @api.depends("date_from", "date_to", "company_id")
    def _compute_metrics(self):
        for rec in self:
            Investment = rec.env["alba.investment"]
            Investor = rec.env["alba.investor"]
            Accrual = rec.env["alba.interest.accrual"]

            investments = Investment.search(rec._investment_domain()) if rec.date_from and rec.date_to else Investment.browse()

            # Portfolio-health figures use the full current book, not the
            # start-date cohort (see _portfolio_domain()).
            portfolio = Investment.search(rec._portfolio_domain())
            active_portfolio = portfolio.filtered(lambda i: i.state == "active")
            matured_portfolio = portfolio.filtered(lambda i: i.state == "matured")
            withdrawn_portfolio = portfolio.filtered(lambda i: i.state == "withdrawn")

            rec.investor_count = len(portfolio.mapped("investor_id"))
            rec.active_investor_count = len(active_portfolio.mapped("investor_id"))
            rec.matured_investor_count = len(matured_portfolio.mapped("investor_id"))

            rec.total_invested_amount = rec._sum_in_dashboard_currency(active_portfolio, "principal_amount")
            rec.total_interest_earned = (
                rec._sum_in_dashboard_currency(active_portfolio, "total_interest_accrued")
                + rec._sum_in_dashboard_currency(matured_portfolio, "total_interest_accrued")
            )
            rec.total_balance = rec._sum_in_dashboard_currency(active_portfolio, "current_value")

            rec.total_withdrawals = rec._sum_in_dashboard_currency(withdrawn_portfolio, "principal_amount")
            rec.pending_withdrawals = len(active_portfolio.filtered(lambda i: i.withdrawal_notice_date))

            rec.outstanding_interest_payable = rec._sum_in_dashboard_currency(
                active_portfolio, "total_interest_outstanding"
            )

            maturing_soon = active_portfolio.filtered(
                lambda i: i.investment_type == "fixed_term"
                and i.maturity_date
                and i.days_to_maturity <= 30
            )
            rec.maturing_soon_count = len(maturing_soon)
            rec.maturing_soon_amount = rec._sum_in_dashboard_currency(maturing_soon, "current_value")

            rec.kyc_pending_count = Investor.search_count([
                ("company_id", "=", rec.company_id.id),
                ("kyc_status", "!=", "verified"),
            ])

            # Period activity — how much happened during the selected range.
            accruals_count = Accrual.search_count([
                ("investment_id.company_id", "=", rec.company_id.id),
                ("accrual_date", ">=", rec.date_from),
                ("accrual_date", "<=", rec.date_to),
            ])
            rec.transaction_count = accruals_count + len(investments)

    def _group_context(self):
        self.ensure_one()
        return {"group_by": self.group_by} if self.group_by else {}

    def action_refresh(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Dashboard"),
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_view_investors(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Investors"),
            "res_model": "alba.investor",
            "view_mode": "list,pivot,graph,form",
            "domain": self._investor_domain(),
            "context": self._group_context(),
        }

    def action_view_transactions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Interest Accruals"),
            "res_model": "alba.interest.accrual",
            "view_mode": "list,graph,form",
            "domain": [
                ("investment_id.company_id", "=", self.company_id.id),
                ("accrual_date", ">=", self.date_from),
                ("accrual_date", "<=", self.date_to),
            ],
        }

    def action_view_withdrawals(self):
        self.ensure_one()
        # Point-in-time: all currently-withdrawn investments, regardless of
        # when they started — there is no "withdrawal completed on" date to
        # scope by, and scoping by start_date excluded withdrawals of
        # investments that began before the selected period.
        return {
            "type": "ir.actions.act_window",
            "name": _("Withdrawn Investments"),
            "res_model": "alba.investment",
            "view_mode": "list,graph,form",
            "domain": self._portfolio_domain() + [("state", "=", "withdrawn")],
        }

    def action_view_maturing_soon(self):
        self.ensure_one()
        cutoff = fields.Date.today() + timedelta(days=30)
        return {
            "type": "ir.actions.act_window",
            "name": _("Maturing Within 30 Days"),
            "res_model": "alba.investment",
            "view_mode": "list,graph,form",
            "domain": self._portfolio_domain() + [
                ("state", "=", "active"),
                ("investment_type", "=", "fixed_term"),
                ("maturity_date", "!=", False),
                ("maturity_date", "<=", cutoff),
            ],
        }

    def action_view_kyc_pending(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Investors Pending KYC"),
            "res_model": "alba.investor",
            "view_mode": "list,form",
            "domain": self._investor_domain() + [("kyc_status", "!=", "verified")],
        }

    @api.depends("date_from", "date_to", "company_id")
    def _compute_graph_data(self):
        for rec in self:
            rec.investment_composition_data = rec._get_investment_composition()
            rec.investment_trends_data = rec._get_investment_trends()
            rec.investor_status_data = rec._get_investor_status()
            rec.interest_payout_trends_data = rec._get_interest_payout_trends()
            rec.withdrawal_analysis_data = rec._get_withdrawal_analysis()
            rec.investor_type_distribution_data = rec._get_investor_type_distribution()
            rec.investment_amount_distribution_data = rec._get_investment_amount_distribution()
            rec.tenure_distribution_data = rec._get_tenure_distribution()
            rec.investor_concentration_data = rec._get_investor_concentration()

    def _get_investment_composition(self):
        """Get investment composition by product"""
        self.ensure_one()
        investments = self.env["alba.investment"].search(self._investment_domain())
        
        # Group by investment product
        product_data = {}
        for inv in investments:
            product_name = inv.investment_product_id.name or _("Other")
            if product_name not in product_data:
                product_data[product_name] = 0.0
            product_data[product_name] += inv.principal_amount
        
        # Prepare data for pie chart
        labels = list(product_data.keys())
        values = list(product_data.values())
        
        return json.dumps({
            'labels': labels,
            'datasets': [{
                'data': values,
                'backgroundColor': [
                    '#6366f1', '#8b5cf6', '#ec4899', '#10b981',
                    '#f59e0b', '#ef4444', '#3b82f6', '#14b8a6'
                ]
            }]
        })

    def _get_investment_trends(self):
        """Get monthly investment trends for the last 12 months"""
        self.ensure_one()
        
        # Get last 12 months
        end_date = self.date_to or fields.Date.today()
        start_date = end_date - timedelta(days=365)
        
        # Query investments using ORM
        investments = self.env["alba.investment"].search([
            ('company_id', '=', self.company_id.id),
            ('start_date', '>=', start_date),
            ('start_date', '<=', end_date)
        ])
        
        # Group by month
        month_data = {}
        for inv in investments:
            if inv.start_date:
                month_key = inv.start_date.replace(day=1)
                if month_key not in month_data:
                    month_data[month_key] = {'amount': 0.0, 'count': 0}
                month_data[month_key]['amount'] += inv.principal_amount
                month_data[month_key]['count'] += 1
        
        # Sort months
        sorted_months = sorted(month_data.keys())
        
        months = []
        amounts = []
        counts = []
        
        for month in sorted_months:
            months.append(month.strftime('%b %Y'))
            amounts.append(month_data[month]['amount'])
            counts.append(month_data[month]['count'])
        
        return json.dumps({
            'labels': months,
            'datasets': [
                {
                    'label': 'Investment Amount',
                    'data': amounts,
                    'borderColor': '#6366f1',
                    'backgroundColor': 'rgba(99, 102, 241, 0.1)',
                    'yAxisID': 'y'
                },
                {
                    'label': 'Number of Investments',
                    'data': counts,
                    'borderColor': '#ec4899',
                    'backgroundColor': 'rgba(236, 72, 153, 0.1)',
                    'yAxisID': 'y1'
                }
            ]
        })

    def _get_investor_status(self):
        """Get investment status distribution (point-in-time, not start-date cohort)"""
        self.ensure_one()
        investments = self.env["alba.investment"].search(self._portfolio_domain())
        
        # Group by status
        status_data = {}
        for inv in investments:
            status = dict(inv._fields['state'].selection).get(inv.state, inv.state)
            if status not in status_data:
                status_data[status] = 0
            status_data[status] += 1
        
        labels = list(status_data.keys())
        values = list(status_data.values())
        
        return json.dumps({
            'labels': labels,
            'datasets': [{
                'data': values,
                'backgroundColor': [
                    '#10b981', '#f59e0b', '#3b82f6', '#ef4444', '#6c757d'
                ]
            }]
        })

    def _get_interest_payout_trends(self):
        """Get monthly interest accrual trends"""
        self.ensure_one()
        
        # Get last 6 months of accrual data
        end_date = self.date_to or fields.Date.today()
        start_date = end_date - timedelta(days=180)
        
        # Query interest accruals
        accruals = self.env["alba.interest.accrual"].search([
            ('investment_id.company_id', '=', self.company_id.id),
            ('accrual_date', '>=', start_date),
            ('accrual_date', '<=', end_date),
            ('state', '=', 'posted')
        ])
        
        # Group by month
        month_data = {}
        for acc in accruals:
            month_key = acc.accrual_date.replace(day=1)
            if month_key not in month_data:
                month_data[month_key] = 0.0
            month_data[month_key] += acc.interest_amount
        
        # Sort months
        sorted_months = sorted(month_data.keys())
        
        months = []
        amounts = []
        
        for month in sorted_months:
            months.append(month.strftime('%b %Y'))
            amounts.append(month_data[month])
        
        return json.dumps({
            'labels': months,
            'datasets': [{
                'label': 'Interest Accruals',
                'data': amounts,
                'borderColor': '#10b981',
                'backgroundColor': 'rgba(16, 185, 129, 0.1)'
            }]
        })

    def _get_withdrawal_analysis(self):
        """Get withdrawal analysis by product"""
        self.ensure_one()
        investments = self.env["alba.investment"].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'withdrawn'),
            ('start_date', '>=', self.date_from),
            ('start_date', '<=', self.date_to),
        ])
        
        # Group by product
        product_data = {}
        for inv in investments:
            product_name = inv.investment_product_id.name or _("Other")
            if product_name not in product_data:
                product_data[product_name] = 0.0
            product_data[product_name] += inv.principal_amount
        
        labels = list(product_data.keys())
        values = [float(v) for v in product_data.values()]
        
        return json.dumps({
            'labels': labels,
            'datasets': [{
                'label': 'Withdrawn Amount',
                'data': values,
                'backgroundColor': [
                    '#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#8b5cf6'
                ]
            }]
        })

    def _get_investor_type_distribution(self):
        """Get investor type distribution"""
        self.ensure_one()
        investors = self.env["alba.investor"].search(self._investor_domain())
        
        # Group by investor type
        type_data = {}
        for investor in investors:
            investor_type = dict(investor._fields['investor_type'].selection).get(investor.investor_type, investor.investor_type)
            if investor_type not in type_data:
                type_data[investor_type] = 0
            type_data[investor_type] += 1
        
        labels = list(type_data.keys())
        values = list(type_data.values())
        
        return json.dumps({
            'labels': labels,
            'datasets': [{
                'data': values,
                'backgroundColor': ['#6366f1', '#8b5cf6']
            }]
        })

    def _get_investment_amount_distribution(self):
        """Get investment distribution by amount ranges"""
        self.ensure_one()
        investments = self.env["alba.investment"].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'active'),
            ('start_date', '>=', self.date_from),
            ('start_date', '<=', self.date_to),
        ])
        
        # Define amount ranges
        ranges = {
            '0-100K': 0,
            '100K-500K': 0,
            '500K-1M': 0,
            '1M-5M': 0,
            '5M+': 0
        }
        
        for inv in investments:
            amount = inv.principal_amount
            if amount < 100000:
                ranges['0-100K'] += 1
            elif amount < 500000:
                ranges['100K-500K'] += 1
            elif amount < 1000000:
                ranges['500K-1M'] += 1
            elif amount < 5000000:
                ranges['1M-5M'] += 1
            else:
                ranges['5M+'] += 1
        
        labels = list(ranges.keys())
        values = list(ranges.values())
        
        return json.dumps({
            'labels': labels,
            'datasets': [{
                'label': 'Number of Investments',
                'data': values,
                'backgroundColor': [
                    '#6366f1', '#8b5cf6', '#ec4899', '#10b981', '#f59e0b'
                ]
            }]
        })

    def _get_tenure_distribution(self):
        """Get investment distribution by tenure"""
        self.ensure_one()
        investments = self.env["alba.investment"].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'active'),
            ('start_date', '>=', self.date_from),
            ('start_date', '<=', self.date_to),
        ])
        
        # Group by tenure
        tenure_data = {}
        for inv in investments:
            if inv.start_date and inv.maturity_date:
                months = (inv.maturity_date.year - inv.start_date.year) * 12 + (inv.maturity_date.month - inv.start_date.month)
                tenure = max(1, months)
            else:
                tenure = 0  # 0 signifies open-ended / not set
            
            if tenure not in tenure_data:
                tenure_data[tenure] = 0
            tenure_data[tenure] += 1
        
        # Sort and format labels
        sorted_tenures = sorted(tenure_data.keys())
        labels = []
        for tenure in sorted_tenures:
            if tenure == 0:
                labels.append(_("Open Ended"))
            else:
                labels.append(f"{tenure} months")
        values = [tenure_data[tenure] for tenure in sorted_tenures]

        return json.dumps({
            'labels': labels,
            'datasets': [{
                'data': values,
                'backgroundColor': [
                    '#6366f1', '#8b5cf6', '#ec4899', '#10b981',
                    '#f59e0b', '#ef4444', '#3b82f6', '#14b8a6'
                ]
            }]
        })

    def _get_investor_concentration(self):
        """
        Concentration risk: current portfolio value held by the top 5
        investors vs. everyone else. A book where a handful of investors
        hold most of the capital is more exposed to a single withdrawal —
        this was not visible anywhere on the dashboard before.
        """
        self.ensure_one()
        investors = self.env["alba.investor"].search(self._investor_domain())
        ranked = investors.filtered(lambda i: i.current_portfolio_value > 0).sorted(
            key=lambda i: i.current_portfolio_value, reverse=True
        )

        top_n = ranked[:5]
        others = ranked[5:]

        labels = [inv.investor_name or inv.investor_number for inv in top_n]
        values = [float(inv.current_portfolio_value) for inv in top_n]

        others_total = sum(others.mapped("current_portfolio_value"))
        if others_total > 0:
            labels.append(_("All Other Investors"))
            values.append(float(others_total))

        return json.dumps({
            'labels': labels,
            'datasets': [{
                'label': 'Portfolio Value',
                'data': values,
                'backgroundColor': [
                    '#6366f1', '#8b5cf6', '#ec4899', '#10b981',
                    '#f59e0b', '#c9cbcf'
                ]
            }]
        })
