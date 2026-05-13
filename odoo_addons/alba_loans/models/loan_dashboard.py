# -*- coding: utf-8 -*-
import json
from datetime import date, timedelta

from odoo import _, api, fields, models


class AlbaLoanDashboard(models.TransientModel):
    _name = "alba.loan.dashboard"
    _description = "Alba Loans Consolidated Dashboard"

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
            ("loan_product_id", "Loan Product"),
            ("state", "Status"),
            ("par_bucket", "PAR Bucket"),
            ("sector_id", "Sector"),
            ("subsector_id", "Subsector"),
            ("referral_source", "Referral Source"),
            ("disbursement_date:month", "Disbursement Month"),
        ],
        string="Group Loans By",
        default="loan_product_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        readonly=True,
    )

    loan_count = fields.Integer(compute="_compute_metrics")
    application_count = fields.Integer(compute="_compute_metrics")
    customer_count = fields.Integer(compute="_compute_metrics")
    disbursed_amount = fields.Monetary(currency_field="currency_id", compute="_compute_metrics")
    outstanding_amount = fields.Monetary(currency_field="currency_id", compute="_compute_metrics")
    arrears_amount = fields.Monetary(currency_field="currency_id", compute="_compute_metrics")
    collected_amount = fields.Monetary(currency_field="currency_id", compute="_compute_metrics")
    npl_count = fields.Integer(compute="_compute_metrics")
    par_30_amount = fields.Monetary(currency_field="currency_id", compute="_compute_metrics")
    par_90_amount = fields.Monetary(currency_field="currency_id", compute="_compute_metrics")

    # Graph data fields
    portfolio_composition_data = fields.Text(compute="_compute_graph_data")
    disbursement_trends_data = fields.Text(compute="_compute_graph_data")
    par_analysis_data = fields.Text(compute="_compute_graph_data")
    status_distribution_data = fields.Text(compute="_compute_graph_data")
    repayment_performance_data = fields.Text(compute="_compute_graph_data")
    customer_loan_status_data = fields.Text(compute="_compute_graph_data")
    loan_amount_distribution_data = fields.Text(compute="_compute_graph_data")
    loan_tenure_distribution_data = fields.Text(compute="_compute_graph_data")

    def _loan_domain(self):
        self.ensure_one()
        return [
            ("company_id", "=", self.company_id.id),
            ("disbursement_date", ">=", self.date_from),
            ("disbursement_date", "<=", self.date_to),
        ]

    def _application_domain(self):
        self.ensure_one()
        return [
            ("company_id", "=", self.company_id.id),
            ("create_date", ">=", fields.Datetime.to_datetime(self.date_from)),
            ("create_date", "<=", fields.Datetime.to_datetime(self.date_to)),
        ]

    def _repayment_domain(self):
        self.ensure_one()
        return [
            ("company_id", "=", self.company_id.id),
            ("payment_date", ">=", self.date_from),
            ("payment_date", "<=", self.date_to),
            ("state", "=", "posted"),
        ]

    @api.depends("date_from", "date_to", "company_id")
    def _compute_metrics(self):
        for rec in self:
            Loan = rec.env["alba.loan"]
            Application = rec.env["alba.loan.application"]
            Repayment = rec.env["alba.loan.repayment"]

            loans = Loan.search(rec._loan_domain()) if rec.date_from and rec.date_to else Loan.browse()
            applications = (
                Application.search(rec._application_domain())
                if rec.date_from and rec.date_to
                else Application.browse()
            )
            repayments = (
                Repayment.search(rec._repayment_domain())
                if rec.date_from and rec.date_to
                else Repayment.browse()
            )

            rec.loan_count = len(loans)
            rec.application_count = len(applications)
            rec.customer_count = len(loans.mapped("customer_id"))
            rec.disbursed_amount = sum(loans.mapped("principal_amount"))
            rec.outstanding_amount = sum(loans.mapped("outstanding_balance"))
            rec.arrears_amount = sum(loans.mapped("arrears_amount"))
            rec.collected_amount = sum(repayments.mapped("amount_paid"))
            npl = loans.filtered(lambda loan: loan.state == "npl")
            rec.npl_count = len(npl)
            rec.par_30_amount = sum(
                loans.filtered(lambda loan: loan.par_bucket in ("1_30", "31_60", "61_90")).mapped("outstanding_balance")
            )
            rec.par_90_amount = sum(
                loans.filtered(lambda loan: loan.par_bucket in ("91_180", "over_180") or loan.state == "npl").mapped("outstanding_balance")
            )

    def _group_context(self):
        self.ensure_one()
        return {"group_by": self.group_by} if self.group_by else {}

    def action_refresh(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loans Dashboard"),
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_view_loans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loans"),
            "res_model": "alba.loan",
            "view_mode": "list,pivot,graph,form",
            "domain": self._loan_domain(),
            "context": self._group_context(),
        }

    def action_view_applications(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loan Applications"),
            "res_model": "alba.loan.application",
            "view_mode": "kanban,list,graph,form",
            "domain": self._application_domain(),
        }

    def action_view_repayments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Repayments"),
            "res_model": "alba.loan.repayment",
            "view_mode": "list,graph,form",
            "domain": self._repayment_domain(),
        }

    def action_view_par(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Portfolio at Risk"),
            "res_model": "alba.loan",
            "view_mode": "list,pivot,graph,form",
            "domain": self._loan_domain() + [("par_bucket", "!=", "current")],
            "context": {"group_by": "par_bucket"},
        }

    @api.depends("date_from", "date_to", "company_id")
    def _compute_graph_data(self):
        for rec in self:
            rec.portfolio_composition_data = rec._get_portfolio_composition()
            rec.disbursement_trends_data = rec._get_disbursement_trends()
            rec.par_analysis_data = rec._get_par_analysis()
            rec.status_distribution_data = rec._get_status_distribution()
            rec.repayment_performance_data = rec._get_repayment_performance()
            rec.customer_loan_status_data = rec._get_customer_loan_status()
            rec.loan_amount_distribution_data = rec._get_loan_amount_distribution()
            rec.loan_tenure_distribution_data = rec._get_loan_tenure_distribution()

    def _get_portfolio_composition(self):
        """Get loan portfolio composition by product"""
        self.ensure_one()
        loans = self.env["alba.loan"].search(self._loan_domain())
        
        # Group by loan product
        product_data = {}
        for loan in loans:
            product_name = loan.loan_product_id.name or "Unknown"
            if product_name not in product_data:
                product_data[product_name] = 0
            product_data[product_name] += loan.principal_amount
        
        # Prepare data for pie chart
        labels = list(product_data.keys())
        values = list(product_data.values())
        
        return json.dumps({
            'labels': labels,
            'datasets': [{
                'data': values,
                'backgroundColor': [
                    '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', 
                    '#9966FF', '#FF9F40', '#FF6384', '#C9CBCF'
                ]
            }]
        })

    def _get_disbursement_trends(self):
        """Get monthly disbursement trends for the last 12 months"""
        self.ensure_one()
        
        # Get last 12 months
        end_date = self.date_to or fields.Date.today()
        start_date = end_date - timedelta(days=365)
        
        # Query loans using ORM
        loans = self.env["alba.loan"].search([
            ('company_id', '=', self.company_id.id),
            ('disbursement_date', '>=', start_date),
            ('disbursement_date', '<=', end_date)
        ])
        
        # Group by month
        month_data = {}
        for loan in loans:
            if loan.disbursement_date:
                month_key = loan.disbursement_date.replace(day=1)
                if month_key not in month_data:
                    month_data[month_key] = {'amount': 0.0, 'count': 0}
                month_data[month_key]['amount'] += loan.principal_amount
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
                    'label': 'Disbursement Amount',
                    'data': amounts,
                    'borderColor': '#36A2EB',
                    'backgroundColor': 'rgba(54, 162, 235, 0.1)',
                    'yAxisID': 'y'
                },
                {
                    'label': 'Number of Loans',
                    'data': counts,
                    'borderColor': '#FF6384',
                    'backgroundColor': 'rgba(255, 99, 132, 0.1)',
                    'yAxisID': 'y1'
                }
            ]
        })

    def _get_par_analysis(self):
        """Get Portfolio at Risk analysis by PAR bucket"""
        self.ensure_one()
        loans = self.env["alba.loan"].search(self._loan_domain())
        
        # Group by PAR bucket
        par_buckets = {
            'Current': 0,
            '1-30 Days': 0,
            '31-60 Days': 0,
            '61-90 Days': 0,
            '91-180 Days': 0,
            '180+ Days': 0
        }
        
        for loan in loans:
            bucket = loan.par_bucket or 'Current'
            if bucket == 'current':
                par_buckets['Current'] += loan.outstanding_balance
            elif bucket == '1_30':
                par_buckets['1-30 Days'] += loan.outstanding_balance
            elif bucket == '31_60':
                par_buckets['31-60 Days'] += loan.outstanding_balance
            elif bucket == '61_90':
                par_buckets['61-90 Days'] += loan.outstanding_balance
            elif bucket == '91_180':
                par_buckets['91-180 Days'] += loan.outstanding_balance
            elif bucket == 'over_180':
                par_buckets['180+ Days'] += loan.outstanding_balance
        
        labels = list(par_buckets.keys())
        values = [float(v) for v in par_buckets.values()]
        
        return json.dumps({
            'labels': labels,
            'datasets': [{
                'label': 'Outstanding Amount',
                'data': values,
                'backgroundColor': [
                    '#4BC0C0', '#FFCE56', '#FF9F40', '#FF6384', 
                    '#9966FF', '#C9CBCF'
                ]
            }]
        })

    def _get_status_distribution(self):
        """Get loan status distribution"""
        self.ensure_one()
        loans = self.env["alba.loan"].search(self._loan_domain())
        
        # Group by status
        status_data = {}
        for loan in loans:
            status = dict(loan._fields['state'].selection).get(loan.state, loan.state)
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
                    '#4BC0C0', '#36A2EB', '#FFCE56', '#FF6384', 
                    '#9966FF', '#FF9F40', '#C9CBCF'
                ]
            }]
        })

    def _get_repayment_performance(self):
        """Get monthly repayment performance vs scheduled payments"""
        self.ensure_one()
        
        # Get last 6 months of repayment data
        end_date = self.date_to or fields.Date.today()
        start_date = end_date - timedelta(days=180)
        
        # Query actual collections using ORM
        repayments = self.env["alba.loan.repayment"].search([
            ('company_id', '=', self.company_id.id),
            ('payment_date', '>=', start_date),
            ('payment_date', '<=', end_date),
            ('state', '=', 'posted')
        ])
        
        # Group collections by month
        collection_dict = {}
        for repayment in repayments:
            month_key = repayment.payment_date.replace(day=1)
            if month_key not in collection_dict:
                collection_dict[month_key] = 0.0
            collection_dict[month_key] += repayment.amount_paid
        
        # For scheduled payments, use a simpler approach - get from loan schedules
        loans = self.env["alba.loan"].search(self._loan_domain())
        scheduled_dict = {}
        
        for loan in loans:
            schedules = self.env["alba.repayment.schedule"].search([
                ('loan_id', '=', loan.id),
                ('due_date', '>=', start_date),
                ('due_date', '<=', end_date)
            ])
            for schedule in schedules:
                month_key = schedule.due_date.replace(day=1)
                if month_key not in scheduled_dict:
                    scheduled_dict[month_key] = 0.0
                scheduled_dict[month_key] += schedule.total_due
        
        # Merge the data
        months = []
        collected = []
        scheduled = []
        
        # Get all unique months and sort them
        all_months = set(collection_dict.keys()) | set(scheduled_dict.keys())
        
        for month in sorted(all_months):
            months.append(month.strftime('%b %Y'))
            collected.append(collection_dict.get(month, 0))
            scheduled.append(scheduled_dict.get(month, 0))
        
        return json.dumps({
            'labels': months,
            'datasets': [
                {
                    'label': 'Actual Collections',
                    'data': collected,
                    'borderColor': '#4BC0C0',
                    'backgroundColor': 'rgba(75, 192, 192, 0.1)'
                },
                {
                    'label': 'Scheduled Payments',
                    'data': scheduled,
                    'borderColor': '#FF6384',
                    'backgroundColor': 'rgba(255, 99, 132, 0.1)'
                }
            ]
        })

    def _get_customer_loan_status(self):
        """Get customer loan status distribution"""
        self.ensure_one()
        loans = self.env["alba.loan"].search(self._loan_domain())
        
        # Group customers by their loan status
        customer_status = {}
        for loan in loans:
            if loan.customer_id:
                customer_name = loan.customer_id.display_name or "Unknown"
                status = dict(loan._fields['state'].selection).get(loan.state, loan.state)
                if customer_name not in customer_status:
                    customer_status[customer_name] = status
        
        # Count customers by status
        status_counts = {}
        for status in customer_status.values():
            if status not in status_counts:
                status_counts[status] = 0
            status_counts[status] += 1
        
        labels = list(status_counts.keys())
        values = list(status_counts.values())
        
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

    def _get_loan_amount_distribution(self):
        """Get loan distribution by amount ranges"""
        self.ensure_one()
        loans = self.env["alba.loan"].search(self._loan_domain())
        
        # Define amount ranges
        ranges = {
            '0-50K': 0,
            '50K-100K': 0,
            '100K-200K': 0,
            '200K-500K': 0,
            '500K+': 0
        }
        
        for loan in loans:
            amount = loan.principal_amount
            if amount < 50000:
                ranges['0-50K'] += 1
            elif amount < 100000:
                ranges['50K-100K'] += 1
            elif amount < 200000:
                ranges['100K-200K'] += 1
            elif amount < 500000:
                ranges['200K-500K'] += 1
            else:
                ranges['500K+'] += 1
        
        labels = list(ranges.keys())
        values = list(ranges.values())
        
        return json.dumps({
            'labels': labels,
            'datasets': [{
                'label': 'Number of Loans',
                'data': values,
                'backgroundColor': [
                    '#6366f1', '#8b5cf6', '#ec4899', '#10b981', '#f59e0b'
                ]
            }]
        })

    def _get_loan_tenure_distribution(self):
        """Get loan distribution by tenure"""
        self.ensure_one()
        loans = self.env["alba.loan"].search(self._loan_domain())
        
        # Group by tenure
        tenure_data = {}
        for loan in loans:
            tenure = loan.tenure_months
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
                    '#f59e0b', '#ef4444', '#3b82f6', '#14b8a6',
                    '#f97316', '#84cc16'
                ]
            }]
        })
