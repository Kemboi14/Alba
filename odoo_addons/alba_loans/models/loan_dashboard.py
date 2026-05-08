# -*- coding: utf-8 -*-
from datetime import date

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
