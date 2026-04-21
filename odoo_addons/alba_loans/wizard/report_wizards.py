from odoo import models, fields


class AlbaReportParWizard(models.TransientModel):
    _name = "alba.report.par.wizard"
    _description = "Portfolio at Risk (PAR) Report Wizard"

    as_of_date = fields.Date(required=True, default=fields.Date.today)

    def action_generate_report(self):
        self.ensure_one()
        report = self.env["alba.report.par"].create({"as_of_date": self.as_of_date})
        return self.env.ref("alba_loans.action_report_par").report_action(report)


class AlbaReportNplWizard(models.TransientModel):
    _name = "alba.report.npl.wizard"
    _description = "Non-Performing Loans (NPL) Report Wizard"

    as_of_date = fields.Date(required=True, default=fields.Date.today)

    def action_generate_report(self):
        self.ensure_one()
        report = self.env["alba.report.npl"].create({"as_of_date": self.as_of_date})
        return self.env.ref("alba_loans.action_report_npl").report_action(report)


class AlbaReportPlWizard(models.TransientModel):
    _name = "alba.report.pl.wizard"
    _description = "Profit & Loss Report Wizard"

    date_from = fields.Date(required=True, default=fields.Date.today)
    date_to = fields.Date(required=True, default=fields.Date.today)

    def action_generate_report(self):
        self.ensure_one()
        report = self.env["alba.report.pl"].create({
            "date_from": self.date_from,
            "date_to": self.date_to,
        })
        return self.env.ref("alba_loans.action_report_pl").report_action(report)


class AlbaReportCashflowWizard(models.TransientModel):
    _name = "alba.report.cashflow.wizard"
    _description = "Cash Flow Statement Report Wizard"

    date_from = fields.Date(required=True, default=fields.Date.today)
    date_to = fields.Date(required=True, default=fields.Date.today)

    def action_generate_report(self):
        self.ensure_one()
        report = self.env["alba.report.cashflow"].create({
            "date_from": self.date_from,
            "date_to": self.date_to,
        })
        return self.env.ref("alba_loans.action_report_cashflow").report_action(report)


class AlbaReportBalanceSheetWizard(models.TransientModel):
    _name = "alba.report.balance.sheet.wizard"
    _description = "Balance Sheet Report Wizard"

    as_of_date = fields.Date(required=True, default=fields.Date.today)

    def action_generate_report(self):
        self.ensure_one()
        report = self.env["alba.report.balance.sheet"].create({
            "as_of_date": self.as_of_date,
        })
        return self.env.ref("alba_loans.action_report_balance_sheet").report_action(report)
