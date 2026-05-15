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

    # Graph data fields
    investment_composition_data = fields.Text(compute="_compute_graph_data")
    investment_trends_data = fields.Text(compute="_compute_graph_data")
    investor_status_data = fields.Text(compute="_compute_graph_data")
    interest_payout_trends_data = fields.Text(compute="_compute_graph_data")
    withdrawal_analysis_data = fields.Text(compute="_compute_graph_data")
    investor_type_distribution_data = fields.Text(compute="_compute_graph_data")
    investment_amount_distribution_data = fields.Text(compute="_compute_graph_data")
    tenure_distribution_data = fields.Text(compute="_compute_graph_data")

    def _investor_domain(self):
        self.ensure_one()
        return [
            ("company_id", "=", self.company_id.id),
            ("start_date", ">=", self.date_from),
            ("start_date", "<=", self.date_to),
        ]

    def _transaction_domain(self):
        self.ensure_one()
        return [
            ("investor_id.company_id", "=", self.company_id.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]

    def _withdrawal_domain(self):
        self.ensure_one()
        return [
            ("investor_id.company_id", "=", self.company_id.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]

    @api.depends("date_from", "date_to", "company_id")
    def _compute_metrics(self):
        for rec in self:
            Investor = rec.env["alba.investor"]
            Transaction = rec.env["alba.investor.transaction"]
            Withdrawal = rec.env["alba.investor.withdrawal"]

            investors = Investor.search(rec._investor_domain()) if rec.date_from and rec.date_to else Investor.browse()
            transactions = (
                Transaction.search(rec._transaction_domain())
                if rec.date_from and rec.date_to
                else Transaction.browse()
            )
            withdrawals = (
                Withdrawal.search(rec._withdrawal_domain())
                if rec.date_from and rec.date_to
                else Withdrawal.browse()
            )

            rec.investor_count = len(investors)
            rec.active_investor_count = len(investors.filtered(lambda i: i.state == "active"))
            rec.matured_investor_count = len(investors.filtered(lambda i: i.state == "matured"))
            rec.total_invested_amount = sum(investors.mapped("principal_amount"))
            rec.total_interest_earned = sum(investors.mapped("total_interest"))
            rec.total_balance = sum(investors.mapped("balance"))
            rec.total_withdrawals = sum(withdrawals.mapped("amount"))
            rec.pending_withdrawals = len(withdrawals.filtered(lambda w: w.state == "pending"))
            rec.transaction_count = len(transactions)

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
            "name": _("Investor Transactions"),
            "res_model": "alba.investor.transaction",
            "view_mode": "list,graph,form",
            "domain": self._transaction_domain(),
        }

    def action_view_withdrawals(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Withdrawal Requests"),
            "res_model": "alba.investor.withdrawal",
            "view_mode": "list,graph,form",
            "domain": self._withdrawal_domain(),
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

    def _get_investment_composition(self):
        """Get investment composition by product"""
        self.ensure_one()
        investors = self.env["alba.investor"].search(self._investor_domain())
        
        # Group by investment product
        product_data = {}
        for investor in investors:
            product_name = dict(investor._fields['investment_product'].selection).get(investor.investment_product, investor.investment_product)
            if product_name not in product_data:
                product_data[product_name] = 0
            product_data[product_name] += investor.principal_amount
        
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
        
        # Query investors using ORM
        investors = self.env["alba.investor"].search([
            ('company_id', '=', self.company_id.id),
            ('start_date', '>=', start_date),
            ('start_date', '<=', end_date)
        ])
        
        # Group by month
        month_data = {}
        for investor in investors:
            if investor.start_date:
                month_key = investor.start_date.replace(day=1)
                if month_key not in month_data:
                    month_data[month_key] = {'amount': 0.0, 'count': 0}
                month_data[month_key]['amount'] += investor.principal_amount
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
                    'label': 'Number of Investors',
                    'data': counts,
                    'borderColor': '#ec4899',
                    'backgroundColor': 'rgba(236, 72, 153, 0.1)',
                    'yAxisID': 'y1'
                }
            ]
        })

    def _get_investor_status(self):
        """Get investor status distribution"""
        self.ensure_one()
        investors = self.env["alba.investor"].search(self._investor_domain())
        
        # Group by status
        status_data = {}
        for investor in investors:
            status = dict(investor._fields['state'].selection).get(investor.state, investor.state)
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
                    '#10b981', '#f59e0b', '#3b82f6', '#ef4444'
                ]
            }]
        })

    def _get_interest_payout_trends(self):
        """Get monthly interest payout trends"""
        self.ensure_one()
        
        # Get last 6 months of transaction data
        end_date = self.date_to or fields.Date.today()
        start_date = end_date - timedelta(days=180)
        
        # Query interest transactions using ORM
        transactions = self.env["alba.investor.transaction"].search([
            ('investor_id.company_id', '=', self.company_id.id),
            ('date', '>=', start_date),
            ('date', '<=', end_date),
            ('transaction_type', '=', 'interest')
        ])
        
        # Group by month
        month_data = {}
        for transaction in transactions:
            month_key = transaction.date.replace(day=1)
            if month_key not in month_data:
                month_data[month_key] = 0.0
            month_data[month_key] += transaction.amount
        
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
                'label': 'Interest Payouts',
                'data': amounts,
                'borderColor': '#10b981',
                'backgroundColor': 'rgba(16, 185, 129, 0.1)'
            }]
        })

    def _get_withdrawal_analysis(self):
        """Get withdrawal analysis by status"""
        self.ensure_one()
        withdrawals = self.env["alba.investor.withdrawal"].search(self._withdrawal_domain())
        
        # Group by status
        status_data = {}
        for withdrawal in withdrawals:
            status = dict(withdrawal._fields['state'].selection).get(withdrawal.state, withdrawal.state)
            if status not in status_data:
                status_data[status] = 0.0
            status_data[status] += withdrawal.total_amount
        
        labels = list(status_data.keys())
        values = [float(v) for v in status_data.values()]
        
        return json.dumps({
            'labels': labels,
            'datasets': [{
                'label': 'Withdrawal Amount',
                'data': values,
                'backgroundColor': [
                    '#f59e0b', '#10b981', '#3b82f6', '#ef4444'
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
        investors = self.env["alba.investor"].search(self._investor_domain())
        
        # Define amount ranges
        ranges = {
            '0-100K': 0,
            '100K-500K': 0,
            '500K-1M': 0,
            '1M-5M': 0,
            '5M+': 0
        }
        
        for investor in investors:
            amount = investor.principal_amount
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
                'label': 'Number of Investors',
                'data': values,
                'backgroundColor': [
                    '#6366f1', '#8b5cf6', '#ec4899', '#10b981', '#f59e0b'
                ]
            }]
        })

    def _get_tenure_distribution(self):
        """Get investment distribution by tenure"""
        self.ensure_one()
        investors = self.env["alba.investor"].search(self._investor_domain())
        
        # Group by tenure
        tenure_data = {}
        for investor in investors:
            tenure = investor.tenure_months
            if tenure not in tenure_data:
                tenure_data[tenure] = 0
            tenure_data[tenure] += 1
        
        labels = [f'{tenure} months' for tenure in sorted(tenure_data.keys())]
        values = [tenure_data[tenure] for tenure in sorted(tenure_data.keys())]
        
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
