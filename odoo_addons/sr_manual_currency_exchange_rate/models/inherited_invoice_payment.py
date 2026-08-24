# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError


class AccountPayments(models.Model):
    _inherit = 'account.payment'

    apply_manual_currency_exchange = fields.Boolean(
        string='Apply Manual Currency Exchange')
    manual_currency_exchange_rate = fields.Float(
        string='Manual Currency Exchange Rate')
    active_manual_currency_rate = fields.Boolean(
        'active Manual Currency', default=False)

    @api.onchange('currency_id')
    def onchange_currency_id(self):
        if self.currency_id:
            if self.company_id.currency_id != self.currency_id:
                self.active_manual_currency_rate = True
            else:
                self.active_manual_currency_rate = False
        else:
            self.active_manual_currency_rate = False

    # V19 code
    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        ''' Prepare the dictionary to create the default account.move.lines for the current payment.
        :param write_off_line_vals: Optional list of dictionaries to create a write-off account.move.line easily containing:
            * amount:       The amount to be added to the counterpart amount.
            * name:         The label to set on the line.
            * account_id:   The account on which create the write-off.
        :param force_balance: Optional balance.
        :return: A list of python dictionary to be passed to the account.move.line's 'create' method.
        '''
        self.ensure_one()
        write_off_line_vals = write_off_line_vals or []

        if not self.outstanding_account_id:
            raise UserError(_(
                "You can't create a new payment without an outstanding payments/receipts account set either on the company or the %(payment_method)s payment method in the %(journal)s journal.",
                payment_method=self.payment_method_line_id.name, journal=self.journal_id.display_name))

        # Compute amounts.
        write_off_line_vals_list = write_off_line_vals or []
        write_off_amount_currency = sum(x['amount_currency'] for x in write_off_line_vals_list)
        write_off_balance = sum(x['balance'] for x in write_off_line_vals_list)

        if self.payment_type == 'inbound':
            # Receive money.
            liquidity_amount_currency = self.amount
        elif self.payment_type == 'outbound':
            # Send money.
            liquidity_amount_currency = -self.amount
        else:
            liquidity_amount_currency = 0.0

        if not write_off_line_vals and force_balance is not None:
            sign = 1 if liquidity_amount_currency > 0 else -1
            liquidity_balance = sign * abs(force_balance)
        else:
            if self.active_manual_currency_rate and self.manual_currency_exchange_rate:
                liquidity_balance = liquidity_amount_currency / self.manual_currency_exchange_rate
            else:
                liquidity_balance = self.currency_id._convert(
                    liquidity_amount_currency,
                    self.company_id.currency_id,
                    self.company_id,
                    self.date,
                )
        counterpart_amount_currency = -liquidity_amount_currency - write_off_amount_currency
        counterpart_balance = -liquidity_balance - write_off_balance
        currency_id = self.currency_id.id

        # Compute a default label to set on the journal items.
        liquidity_line_name = ''.join(x[1] for x in self._get_aml_default_display_name_list() if x[1])
        counterpart_line_name = liquidity_line_name

        line_vals_list = [
            # Liquidity line.
            {
                'name': liquidity_line_name,
                'date_maturity': self.date,
                'amount_currency': liquidity_amount_currency,
                'currency_id': currency_id,
                'debit': liquidity_balance if liquidity_balance > 0.0 else 0.0,
                'credit': -liquidity_balance if liquidity_balance < 0.0 else 0.0,
                'partner_id': self.partner_id.id,
                'account_id': self.outstanding_account_id.id,
            },
            # Receivable / Payable.
            {
                'name': counterpart_line_name,
                'date_maturity': self.date,
                'amount_currency': counterpart_amount_currency,
                'currency_id': currency_id,
                'debit': counterpart_balance if counterpart_balance > 0.0 else 0.0,
                'credit': -counterpart_balance if counterpart_balance < 0.0 else 0.0,
                'partner_id': self.partner_id.id,
                'account_id': self.destination_account_id.id,
            },
        ]

        # Add custom ode
        if write_off_line_vals and isinstance(write_off_line_vals, list):
            write_off_line_vals = write_off_line_vals[0]  # Get the first dictionary if it's a list
            if not self.currency_id.is_zero(write_off_amount_currency):
                line_vals_list.append({
                    'name': write_off_line_vals.get('name') or False,
                    'amount_currency': write_off_line_vals.get('amount_currency'),
                    'currency_id': write_off_line_vals.get('currency_id'),
                    # 'amount_currency': write_off_amount_currency,
                    # 'currency_id': currency_id,
                    'debit': write_off_balance if write_off_balance > 0.0 else 0.0,
                    'credit': -write_off_balance if write_off_balance < 0.0 else 0.0,
                    'partner_id': self.partner_id.id,
                    'account_id': write_off_line_vals.get('account_id'),
                })
            return line_vals_list

        return line_vals_list + write_off_line_vals_list

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        return (
            'date', 'amount', 'payment_type', 'partner_type', 'payment_reference',
            'currency_id', 'partner_id', 'destination_account_id', 'partner_bank_id', 'journal_id', 'manual_currency_exchange_rate'
        )

    # V19 Code
    def _synchronize_to_moves(self, changed_fields):
        '''
            Update the account.move regarding the modified account.payment.
            :param changed_fields: A list containing all modified fields on account.payment.
        '''
        if not any(field_name in changed_fields for field_name in self._get_trigger_fields_to_synchronize()):
            return

        for pay in self:
            if pay.move_id.state == 'posted':
                continue
            liquidity_lines, counterpart_lines, writeoff_lines = pay._seek_for_lines()
            # Make sure to preserve the write-off amount.
            # This allows to create a new payment with custom 'line_ids'.
            write_off_line_vals = []
            if liquidity_lines and counterpart_lines and writeoff_lines:
                write_off_line_vals.append({
                    'name': writeoff_lines[0].name,
                    'account_id': writeoff_lines[0].account_id.id,
                    'partner_id': writeoff_lines[0].partner_id.id,
                    'currency_id': writeoff_lines[0].currency_id.id,
                    'amount_currency': sum(writeoff_lines.mapped('amount_currency')),
                    'balance': sum(writeoff_lines.mapped('balance')),
                })
            line_vals_list = pay._prepare_move_line_default_vals(write_off_line_vals=write_off_line_vals)
            line_ids_commands = [
                Command.update(liquidity_lines.id, line_vals_list[0]) if liquidity_lines else Command.create(line_vals_list[0]),
                Command.update(counterpart_lines.id, line_vals_list[1]) if counterpart_lines else Command.create(line_vals_list[1])
            ]
            for line in writeoff_lines:
                line_ids_commands.append((2, line.id))
            for extra_line_vals in line_vals_list[2:]:
                line_ids_commands.append((0, 0, extra_line_vals))
            # Update the existing journal items.
            # If dealing with multiple write-off lines, they are dropped and a new one is generated.
            to_write = {
                'date': pay.date,
                'partner_id': pay.partner_id.id,
                'currency_id': pay.currency_id.id,
                'partner_bank_id': pay.partner_bank_id.id,
                'apply_manual_currency_exchange': self.apply_manual_currency_exchange,
                'manual_currency_exchange_rate': self.manual_currency_exchange_rate,
                'active_manual_currency_rate': self.active_manual_currency_rate,
                'invoice_currency_rate': self.manual_currency_exchange_rate,
                'line_ids': line_ids_commands,
            }
            if 'journal_id' in changed_fields:
                to_write.update({
                    'name': '/',  # Set the name to '/' to allow it to be changed
                    'journal_id': pay.journal_id.id
                })
            pay.move_id.with_context(skip_invoice_sync=True).write(to_write)

    # V19 code
    def _generate_move_vals(self, write_off_line_vals=None, force_balance=None, line_ids=None):
        """ Prepare the values needed to create a move for self. """
        self.ensure_one()
        return {
            'move_type': 'entry',
            'ref': self.memo,
            'date': self.date,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'currency_id': self.currency_id.id,
            'apply_manual_currency_exchange': self.apply_manual_currency_exchange,
            'manual_currency_exchange_rate' : self.manual_currency_exchange_rate,
            'active_manual_currency_rate' : self.active_manual_currency_rate,
            'invoice_currency_rate': self.manual_currency_exchange_rate,
            'partner_bank_id': self.partner_bank_id.id,
            'line_ids': line_ids or [
                Command.create(line_vals)
                for line_vals in self._prepare_move_line_default_vals(
                    write_off_line_vals=write_off_line_vals,
                    force_balance=force_balance,
                )
            ],
            'origin_payment_id': self.id,
        }