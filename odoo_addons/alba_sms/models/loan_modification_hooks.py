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
        enabled = self.env["ir.config_parameter"].sudo().get_param("alba_sms.enabled", default="1")
        if enabled == "0":
            return

        partner = record.partner_id
        if not partner:
            return
        
        # Resolve Phone (use getattr to avoid AttributeError on partners missing `mobile`)
        customer = getattr(record, 'customer_id', getattr(record.loan_id, 'customer_id', None) if hasattr(record, 'loan_id') else None)
        phone = False
        if customer:
            partner_rec = getattr(customer, 'partner_id', None)
            phone = (
                getattr(customer, 'mpesa_number', False)
                or (getattr(partner_rec, 'mobile', False) if partner_rec else False)
                or (getattr(partner_rec, 'phone', False) if partner_rec else False)
                or getattr(partner, 'phone', False)
                or getattr(partner, 'mobile', False)
            )
        else:
            phone = getattr(partner, 'mobile', False) or getattr(partner, 'phone', False)

        if not phone:
            _logger.warning("No phone number found for partner '%s' — skipping SMS.", partner.name)
            return

        template = self.env['alba.sms.template'].search([('code', '=', template_code)], limit=1)
        if not template:
            _logger.warning("SMS Template not found: %s", template_code)
            return

        provider = self.env["alba.sms.provider"].sudo().search([("is_active", "=", True)], limit=1)
        if not provider:
            _logger.warning("No active SMS provider found.")
            return

        context = {
            'customer_name': partner.name,
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
            
        message = template.render(context)
        
        provider.send_sms(
            phone,
            message,
            res_model=record._name,
            res_id=record.id,
            template_id=template.id,
        )
        
        # Avoid posting chatter for certain loan modification types (topups, partial payoff, refinance, consolidation)
        if hasattr(record, 'message_post') and record._name not in (
            'alba.loan.topup',
            'alba.loan.partial.payoff',
            'alba.loan.refinance',
            'alba.loan.consolidation',
        ):
            record.message_post(body=_("<b>Automated SMS Sent</b>: %s") % message)

class AlbaLoanTopup(models.Model):
    _inherit = 'alba.loan.topup'

    def action_disburse(self):
        res = super(AlbaLoanTopup, self).action_disburse()
        for rec in self:
            if rec.state == 'disbursed':
                try:
                    self.env['alba.loan.modification.hooks']._send_modification_sms(
                        rec, 'LOAN_TOPUP_DISBURSED',
                        {'amount': rec.topup_amount, 'new_principal': rec.new_principal}
                    )
                except Exception as e:  # ensure SMS errors don't block the action
                    _logger.exception("alba_sms: failed to send topup disbursed SMS: %s", e)
        return res

class AlbaLoanPartialPayoff(models.Model):
    _inherit = 'alba.loan.partial.payoff'

    def action_apply(self):
        res = super(AlbaLoanPartialPayoff, self).action_apply()
        for rec in self:
            if rec.state == 'applied':
                try:
                    self.env['alba.loan.modification.hooks']._send_modification_sms(
                        rec, 'LOAN_PARTIAL_PAYOFF_APPLIED',
                        {'amount': rec.payoff_amount, 'savings': rec.interest_saved}
                    )
                except Exception as e:
                    _logger.exception("alba_sms: failed to send partial payoff SMS: %s", e)
        return res

class AlbaLoanPaymentHoliday(models.Model):
    _inherit = 'alba.loan.payment.holiday'

    def action_activate(self):
        res = super(AlbaLoanPaymentHoliday, self).action_activate()
        for rec in self:
            if rec.state == 'active':
                try:
                    self.env['alba.loan.modification.hooks']._send_modification_sms(
                        rec, 'LOAN_PAYMENT_HOLIDAY_ACTIVATED',
                        {'months': rec.holiday_months, 'end_date': rec.end_date}
                    )
                except Exception as e:
                    _logger.exception("alba_sms: failed to send payment holiday SMS: %s", e)
        return res

class AlbaLoanRefinance(models.Model):
    _inherit = 'alba.loan.refinance'

    def action_complete(self):
        res = super(AlbaLoanRefinance, self).action_complete()
        for rec in self:
            if rec.state == 'completed':
                try:
                    self.env['alba.loan.modification.hooks']._send_modification_sms(
                        rec, 'LOAN_REFINANCE_COMPLETED',
                        {'new_loan': rec.new_loan_id.loan_number if rec.new_loan_id else ''}
                    )
                except Exception as e:
                    _logger.exception("alba_sms: failed to send refinance completed SMS: %s", e)
        return res

class AlbaLoanConsolidation(models.Model):
    _inherit = 'alba.loan.consolidation'

    def action_complete(self):
        res = super(AlbaLoanConsolidation, self).action_complete()
        for rec in self:
            if rec.state == 'completed':
                try:
                    self.env['alba.loan.modification.hooks']._send_modification_sms(
                        rec, 'LOAN_CONSOLIDATION_COMPLETED',
                        {'loan_count': len(rec.loan_ids), 'new_loan': rec.new_loan_id.loan_number if rec.new_loan_id else ''}
                    )
                except Exception as e:
                    _logger.exception("alba_sms: failed to send consolidation completed SMS: %s", e)
        return res
