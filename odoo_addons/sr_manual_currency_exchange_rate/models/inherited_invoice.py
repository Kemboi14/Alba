# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from odoo import models, fields, api
from contextlib import contextmanager


class AccountMove(models.Model):
    _inherit = 'account.move'

    apply_manual_currency_exchange = fields.Boolean(string='Apply Manual Currency Exchange')
    manual_currency_exchange_rate = fields.Float(string='Manual Currency Exchange Rate', digits=(12, 6))
    active_manual_currency_rate = fields.Boolean('active Manual Currency')

    @api.onchange('company_id', 'currency_id')
    def onchange_currency_id(self):
        if self.company_id or self.currency_id:
            if self.company_id.currency_id != self.currency_id:
                self.active_manual_currency_rate = True
            else:
                self.active_manual_currency_rate = False
        else:
            self.active_manual_currency_rate = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'invoice_origin' in vals:
                purchase_order_id = self.env['purchase.order'].search([('name', '=', vals['invoice_origin'])])
                if purchase_order_id:
                    vals['invoice_currency_rate'] = purchase_order_id.manual_currency_exchange_rate
        moves = super(AccountMove, self).create(vals_list)
        return moves


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends('currency_id', 'company_id', 'move_id.invoice_currency_rate', 'move_id.date', 'move_id.apply_manual_currency_exchange')
    def _compute_currency_rate(self):
        for line in self:
            if line.move_id.apply_manual_currency_exchange and line.move_id.move_type == 'entry':
                line.currency_rate = line.move_id.invoice_currency_rate
            else:
                if line.move_id.is_invoice(include_receipts=True):
                    line.currency_rate = line.move_id.invoice_currency_rate or 1.0
                elif line.currency_id:
                    line.currency_rate = self.env['res.currency']._get_conversion_rate(
                        from_currency=line.company_currency_id,
                        to_currency=line.currency_id,
                        company=line.company_id,
                        date=line.move_id.invoice_date or line.move_id.date or fields.Date.context_today(line),
                    )
                else:
                    line.currency_rate = 1

    @api.depends('product_id', 'product_uom_id', 'currency_rate', 'move_id.apply_manual_currency_exchange')
    def _compute_price_unit(self):
        for line in self:
            if not line.product_id or line.display_type in ('line_section', 'line_subsection',
                                                            'line_note') or line.is_imported:
                continue
            if line.move_id.is_sale_document(include_receipts=True):
                document_type = 'sale'
            elif line.move_id.is_purchase_document(include_receipts=True):
                document_type = 'purchase'
            else:
                document_type = 'other'
            if line.price_unit <= 0:
                if line.move_id.apply_manual_currency_exchange and document_type == 'sale':
                    line.price_unit = line.product_id.lst_price * line.currency_rate
                elif line.move_id.apply_manual_currency_exchange and document_type == 'purchase':
                    line.price_unit = line.product_id.standard_price * line.currency_rate
                else:
                    line.price_unit = line.product_id._get_tax_included_unit_price(
                        line.move_id.company_id,
                        line.move_id.currency_id,
                        line.move_id.date,
                        document_type,
                        fiscal_position=line.move_id.fiscal_position_id,
                        product_uom=line.product_uom_id,
                    )

    # V19 Code
    @api.model
    def _prepare_move_line_residual_amounts(self, aml_values, counterpart_currency, shadowed_aml_values=None,
                                            other_aml_values=None):
        """ Prepare the available residual amounts for each currency.
        :param aml_values: The values of account.move.line to consider.
        :param counterpart_currency: The currency of the opposite line this line will be reconciled with.
        :param shadowed_aml_values: A mapping aml -> dictionary to replace some original aml values to something else.
                                    This is usefull if you want to preview the reconciliation before doing some changes
                                    on amls like changing a date or an account.
        :param other_aml_values:    The other aml values to be reconciled with the current one.
        :return: A mapping currency -> dictionary containing:
            * residual: The residual amount left for this currency.
            * rate:     The rate applied regarding the company's currency.
        """

        def is_payment(aml):
            return aml.move_id.origin_payment_id or aml.move_id.statement_line_id

        def get_odoo_rate(aml, other_aml, currency):
            if forced_rate := self.env.context.get('forced_rate_from_register_payment'):
                return forced_rate
            if other_aml and not is_payment(aml) and is_payment(other_aml):
                return get_accounting_rate(other_aml, currency)
            if aml.move_id.is_invoice(include_receipts=True):
                exchange_rate_date = aml.move_id.invoice_date
            else:
                exchange_rate_date = aml._get_reconciliation_aml_field_value('date', shadowed_aml_values)

            # Added new code
            if aml.move_id.apply_manual_currency_exchange:
                return aml.move_id.invoice_currency_rate
            elif other_aml.move_id.apply_manual_currency_exchange:
                return other_aml.move_id.invoice_currency_rate
            else:
                return currency._get_conversion_rate(aml.company_currency_id, currency, aml.company_id, exchange_rate_date)

        def get_accounting_rate(aml, currency):
            balance = aml._get_reconciliation_aml_field_value('balance', shadowed_aml_values)
            amount_currency = aml._get_reconciliation_aml_field_value('amount_currency', shadowed_aml_values)
            if not aml.company_currency_id.is_zero(balance) and not currency.is_zero(amount_currency):
                return abs(amount_currency / balance)

        aml = aml_values['aml']
        other_aml = (other_aml_values or {}).get('aml')
        remaining_amount_curr = aml_values['amount_residual_currency']
        remaining_amount = aml_values['amount_residual']
        company_currency = aml.company_currency_id
        currency = aml._get_reconciliation_aml_field_value('currency_id', shadowed_aml_values)
        account = aml._get_reconciliation_aml_field_value('account_id', shadowed_aml_values)
        has_zero_residual = company_currency.is_zero(remaining_amount)
        has_zero_residual_currency = currency.is_zero(remaining_amount_curr)
        is_rec_pay_account = account.account_type in ('asset_receivable', 'liability_payable')

        available_residual_per_currency = {}

        if not has_zero_residual:
            available_residual_per_currency[company_currency] = {
                'residual': remaining_amount,
                'rate': 1,
            }
        if currency != company_currency and not has_zero_residual_currency:
            available_residual_per_currency[currency] = {
                'residual': remaining_amount_curr,
                'rate': get_accounting_rate(aml, currency),
            }
        if currency == company_currency \
                and is_rec_pay_account \
                and not has_zero_residual \
                and counterpart_currency != company_currency:
            rate = get_odoo_rate(aml, other_aml, counterpart_currency)
            residual_in_foreign_curr = counterpart_currency.round(remaining_amount * rate)
            if not counterpart_currency.is_zero(residual_in_foreign_curr):
                available_residual_per_currency[counterpart_currency] = {
                    'residual': residual_in_foreign_curr,
                    'rate': rate,
                }
        elif currency == counterpart_currency \
                and currency != company_currency \
                and not has_zero_residual_currency:
            available_residual_per_currency[counterpart_currency] = {
                'residual': remaining_amount_curr,
                'rate': get_accounting_rate(aml, currency),
            }
        return available_residual_per_currency