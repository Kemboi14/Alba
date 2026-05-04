# -*- coding: utf-8 -*-
from odoo import api, models, _
import logging

_logger = logging.getLogger(__name__)

class LoanModificationHooks(models.AbstractModel):
    _name = 'alba.loan.modification.hooks'
    _description = 'Loan Modification SMS Hooks'

    @api.model
    def _send_modification_sms(self, record, template_code, extra_context=None):
        """Helper to send modification SMS"""
        if not record.partner_id or not record.partner_id.mobile:
            return
        
        template = self.env['alba.sms.template'].search([('code', '=', template_code)], limit=1)
        if not template:
            _logger.warning("SMS Template not found: %s", template_code)
            return

        context = {
            'customer_name': record.partner_id.name,
            'company_name': self.env.company.name,
        }
        
        # Common fields from loan if available
        loan = getattr(record, 'loan_id', getattr(record, 'original_loan_id', None))
        if loan:
            context.update({
                'loan_number': loan.loan_number,
                'outstanding_balance': f"{loan.currency_id.symbol} {loan.outstanding_balance:,.2f}",
            })

        if extra_context:
            for key, val in extra_context.items():
                if isinstance(val, (float, int)):
                    context[key] = f"{val:,.2f}"
                else:
                    context[key] = str(val)
            
        self.env['alba.sms.log'].send_sms(
            mobile=record.partner_id.mobile,
            template_code=template_code,
            partner_id=record.partner_id.id,
            context=context
        )

class AlbaLoanTopup(models.Model):
    _inherit = 'alba.loan.topup'

    def action_disburse(self):
        res = super(AlbaLoanTopup, self).action_disburse()
        for rec in self:
            if rec.state == 'disbursed':
                self.env['alba.loan.modification.hooks']._send_modification_sms(
                    rec, 'LOAN_TOPUP_DISBURSED',
                    {'amount': rec.topup_amount, 'new_principal': rec.new_principal}
                )
        return res

class AlbaLoanPartialPayoff(models.Model):
    _inherit = 'alba.loan.partial.payoff'

    def action_apply(self):
        res = super(AlbaLoanPartialPayoff, self).action_apply()
        for rec in self:
            if rec.state == 'applied':
                self.env['alba.loan.modification.hooks']._send_modification_sms(
                    rec, 'LOAN_PARTIAL_PAYOFF_APPLIED',
                    {'amount': rec.payoff_amount, 'savings': rec.interest_saved}
                )
        return res

class AlbaLoanPaymentHoliday(models.Model):
    _inherit = 'alba.loan.payment.holiday'

    def action_activate(self):
        res = super(AlbaLoanPaymentHoliday, self).action_activate()
        for rec in self:
            if rec.state == 'active':
                self.env['alba.loan.modification.hooks']._send_modification_sms(
                    rec, 'LOAN_PAYMENT_HOLIDAY_ACTIVATED',
                    {'months': rec.holiday_months, 'end_date': rec.end_date}
                )
        return res

class AlbaLoanRefinance(models.Model):
    _inherit = 'alba.loan.refinance'

    def action_complete(self):
        res = super(AlbaLoanRefinance, self).action_complete()
        for rec in self:
            if rec.state == 'completed':
                self.env['alba.loan.modification.hooks']._send_modification_sms(
                    rec, 'LOAN_REFINANCE_COMPLETED',
                    {'new_loan': rec.new_loan_id.loan_number if rec.new_loan_id else ''}
                )
        return res

class AlbaLoanConsolidation(models.Model):
    _inherit = 'alba.loan.consolidation'

    def action_complete(self):
        res = super(AlbaLoanConsolidation, self).action_complete()
        for rec in self:
            if rec.state == 'completed':
                self.env['alba.loan.modification.hooks']._send_modification_sms(
                    rec, 'LOAN_CONSOLIDATION_COMPLETED',
                    {'loan_count': len(rec.loan_ids), 'new_loan': rec.new_loan_id.loan_number if rec.new_loan_id else ''}
                )
        return res
