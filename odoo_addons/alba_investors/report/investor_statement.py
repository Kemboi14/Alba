from odoo import models, api, _
from datetime import date

class InvestorStatementReport(models.AbstractModel):
    _name = 'report.alba_investors.investor_statement_template'
    _description = 'Investor Account Statement'

    @api.model
    def _get_report_values(self, docids, data=None):
        investors = self.env['alba.investor'].browse(docids)
        # For simplicity, we handle one investor at a time in the logic below
        # but the template can handle multiple if needed.
        investor = investors[0]
        
        date_from = data.get('date_from') if data else '2026-01-01'
        date_to = data.get('date_to') if data else str(date.today())

        # Fetch interest accrual lines using the correct model 'alba.interest.accrual'
        accruals = self.env['alba.interest.accrual'].search([
            ('investor_id', '=', investor.id),
            ('accrual_date', '>=', date_from),
            ('accrual_date', '<=', date_to),
            ('state', '=', 'posted')
        ], order='accrual_date asc')

        lines = []
        for accrual in accruals:
            lines.append({
                'date': accrual.accrual_date,
                'description': accrual.display_name,
                'opening': accrual.opening_balance,
                'debit': 0, # Assuming no debits for now, or fetch from withdrawals if implemented
                'credit': accrual.interest_amount,
                'balance': accrual.closing_balance,
            })

        total_debit = sum(l['debit'] for l in lines)
        total_credit = sum(l['credit'] for l in lines)

        return {
            'doc_ids': docids,
            'doc_model': 'alba.investor',
            'docs': investors,
            'investor': investor,
            'lines': lines,
            'date_from': date_from,
            'date_to': date_to,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'res_company': investor.env.company,
            'currency': investor.currency_id.currency_id if investor.currency_id else investor.env.company.currency_id,
        }
