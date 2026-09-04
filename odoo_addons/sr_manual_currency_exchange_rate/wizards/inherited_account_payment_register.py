# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from collections import defaultdict
from odoo.exceptions import UserError
from odoo import models, fields, api, _


class srAccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    apply_manual_currency_exchange = fields.Boolean(string='Apply Manual Currency Exchange')
    manual_currency_exchange_rate = fields.Float(string='Manual Currency Exchange Rate')
    active_manual_currency_rate = fields.Boolean('active Manual Currency', default=False)


    # V19 Code
    def _convert_to_wizard_currency(self, installments):
        self.ensure_one()
        total_per_currency = defaultdict(lambda: {
            'amount_residual': 0.0,
            'amount_residual_currency': 0.0,
        })
        for installment in installments:
            line = installment['line']
            total_per_currency[line.currency_id]['amount_residual'] += installment['amount_residual']
            total_per_currency[line.currency_id]['amount_residual_currency'] += installment['amount_residual_currency']

        total_amount = 0.0
        wizard_curr = self.currency_id
        comp_curr = self.company_currency_id
        for currency, amounts in total_per_currency.items():
            amount_residual = amounts['amount_residual']
            amount_residual_currency = amounts['amount_residual_currency']
            if currency == wizard_curr:
                # Same currency
                total_amount += amount_residual_currency
            elif currency != comp_curr and wizard_curr == comp_curr:
                # Foreign currency on source line but the company currency one on the opposite line.
                if self.manual_currency_exchange_rate > 0:
                    total_amount += amount_residual_currency / self.manual_currency_exchange_rate
                else:
                    total_amount += currency._convert(amount_residual_currency, comp_curr, self.company_id,
                                                  self.payment_date)
            elif currency == comp_curr and wizard_curr != comp_curr:
                # Company currency on source line but a foreign currency one on the opposite line.
                if self.manual_currency_exchange_rate > 0:
                    total_amount += amount_residual * self.manual_currency_exchange_rate
                else:
                    total_amount += comp_curr._convert(amount_residual, wizard_curr, self.company_id, self.payment_date)
            else:
                # Foreign currency on payment different than the one set on the journal entries.
                total_amount += comp_curr._convert(amount_residual, wizard_curr, self.company_id, self.payment_date)
        return total_amount

    # V19 code
    @api.onchange('currency_id')
    def _onchange_currency_id(self):
        if self.currency_id:
            if self.company_id.currency_id != self.currency_id:
                self.active_manual_currency_rate = True
            else:
                self.active_manual_currency_rate = False
        else:
            self.active_manual_currency_rate = False

        if not self.can_edit_wizard or not self.currency_id or not self.payment_date or not self.custom_user_amount:
            return

        if self.custom_user_amount:
            self.custom_user_amount = self.amount = self.custom_user_currency_id._convert(
                from_amount=self.custom_user_amount,
                to_currency=self.currency_id,
                date=self.payment_date,
                company=self.company_id,
            )

    # V19 Code
    @api.depends('can_edit_wizard', 'source_amount', 'source_amount_currency', 'source_currency_id', 'company_id',
                 'currency_id', 'payment_date', 'installments_mode', 'manual_currency_exchange_rate')
    def _compute_amount(self):
        return super(srAccountPaymentRegister, self)._compute_amount()

    @api.model
    def default_get(self, fields):
        result = super(srAccountPaymentRegister, self).default_get(fields)
        move_id = self.env['account.move.line'].browse(self.env.context.get('active_ids')).filtered(lambda move: move.move_id.is_invoice(include_receipts=True))
        if len(move_id.move_id) !=1:
            return result
        else:
            result.update({
                'apply_manual_currency_exchange': move_id.move_id.apply_manual_currency_exchange,
                'manual_currency_exchange_rate': move_id.move_id.invoice_currency_rate,
            })
            return result

    # V19 code
    # When the wizard is NOT in "edit mode" (i.e. multiple invoices are paid in the
    # same run without "Group Payments"), Odoo core builds each payment after the
    # first one through _create_payment_vals_from_batch instead of
    # _create_payment_vals_from_wizard. That method was not overridden here, so
    # those payments never received the manual currency fields and silently fell
    # back to the standard currency table (recording the foreign amount 1:1 in
    # company currency). Carry the same wizard-level manual currency vals onto
    # every payment created this way.
    def _create_payment_vals_from_batch(self, batch_result):
        payment_vals = super()._create_payment_vals_from_batch(batch_result)
        payment_vals.update({
            'apply_manual_currency_exchange': self.apply_manual_currency_exchange,
            'manual_currency_exchange_rate': self.manual_currency_exchange_rate,
            'active_manual_currency_rate': self.active_manual_currency_rate,
        })
        return payment_vals

    # V19 code
    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = {
            'date': self.payment_date,
            'amount': self.amount,
            'payment_type': self.payment_type,
            'partner_type': self.partner_type,
            'memo': self.communication,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'partner_bank_id': self.partner_bank_id.id,
            'payment_method_line_id': self.payment_method_line_id.id,
            'destination_account_id': self.line_ids[0].account_id.id,
            'write_off_line_vals': [],
            'apply_manual_currency_exchange': self.apply_manual_currency_exchange,
            'manual_currency_exchange_rate':self.manual_currency_exchange_rate,
            'active_manual_currency_rate':self.active_manual_currency_rate
        }

        if self.payment_difference_handling == 'reconcile':
            if self.early_payment_discount_mode:
                epd_aml_values_list = []
                for aml in batch_result['lines']:
                    if aml.move_id._is_eligible_for_early_payment_discount(self.currency_id, self.payment_date):
                        epd_aml_values_list.append({
                            'aml': aml,
                            'amount_currency': -aml.amount_residual_currency,
                            'balance': aml.currency_id._convert(-aml.amount_residual_currency, aml.company_currency_id,
                                                                date=self.payment_date),
                        })

                open_amount_currency = self.payment_difference * (-1 if self.payment_type == 'outbound' else 1)
                open_balance = self.currency_id._convert(open_amount_currency, self.company_id.currency_id,
                                                         self.company_id, self.payment_date)
                early_payment_values = self.env[
                    'account.move']._get_invoice_counterpart_amls_for_early_payment_discount(epd_aml_values_list,
                                                                                             open_balance)
                for aml_values_list in early_payment_values.values():
                    payment_vals['write_off_line_vals'] += aml_values_list

            elif not self.currency_id.is_zero(self.payment_difference):

                if self.writeoff_is_exchange_account:
                    # Force the rate when computing the 'balance' only when the payment has a foreign currency.
                    # If not, the rate is forced during the reconciliation to put the difference directly on the
                    # exchange difference.
                    if self.currency_id != self.company_currency_id:
                        payment_vals['force_balance'] = sum(batch_result['lines'].mapped('amount_residual'))
                else:
                    if self.payment_type == 'inbound':
                        # Receive money.
                        write_off_amount_currency = self.payment_difference
                    else:  # if self.payment_type == 'outbound':
                        # Send money.
                        write_off_amount_currency = -self.payment_difference

                    payment_vals['write_off_line_vals'].append({
                        'name': self.writeoff_label,
                        'account_id': self.writeoff_account_id.id,
                        'partner_id': self.partner_id.id,
                        'currency_id': self.currency_id.id,
                        'amount_currency': write_off_amount_currency,
                        'balance': self.currency_id._convert(write_off_amount_currency, self.company_id.currency_id,
                                                             self.company_id, self.payment_date),
                    })
        return payment_vals
