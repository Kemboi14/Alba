# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from odoo import models, fields, api, Command


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    def set_line_bank_statement_line(self, move_lines_ids):
        """ Sets the specified move lines to the bank statement line and performs reconciliation.

            :param move_lines_ids: A list of IDs for the move lines to be added to the bank statement line.
        """
        self.ensure_one()
        # We do not want to set a line that is already reconciled, otherwise a user error would be raised. The order
        # is there to keep the same order as the one received in move_line_ids
        move_lines = self.env['account.move.line'].search([
            ('id', 'in', move_lines_ids),
            ('reconciled', '=', False),
        ], order="sequence DESC")
        if not move_lines:
            return

        _liquidity_line, _suspense_lines, other_lines = self._seek_for_lines()
        transaction_amount, transaction_currency, journal_amount, journal_currency, company_amount, company_currency = self._get_accounting_amounts_and_currencies()
        journal_transaction_rate = abs(transaction_amount / journal_amount) if journal_amount else 0.0
        company_transaction_rate = abs(transaction_amount / company_amount) if company_amount else 0.0

        open_balance = company_amount
        open_amount_currency = transaction_amount
        total_early_payment_discount = 0.0
        early_pay_aml_values_list = []

        for line in other_lines + move_lines:
            # move_lines are the lines coming from the reconcile button and other_lines are the lines from the bank
            # statement move (so they are reconciled). We need to invert the sign of move_lines since a positive
            # move_line need to be put as negative in the bank statement move.
            # For the other lines, we can use the balance and amount currency since they are the line on the bank move
            if line in move_lines:
                sign = -1
                amount = line.amount_residual
                amount_currency = line.amount_residual_currency
            else:
                sign = 1
                amount = line.balance
                amount_currency = line.amount_currency

            # Early payment Discount
            if line.move_id._is_eligible_for_early_payment_discount(transaction_currency, self.date):
                total_early_payment_discount += line.amount_currency - line.discount_amount_currency
                early_pay_aml_values_list.append({
                    'aml': line,
                    'amount_currency': -line.amount_currency,
                    'balance': -amount,
                })

            if line.move_id.apply_manual_currency_exchange and line.currency_rate:
                exchange_diff_balance = self._lines_get_account_balance_exchange_diff_cus(line.currency_id, amount,
                                                                                      amount_currency, line)
            else:
                exchange_diff_balance = self._lines_get_account_balance_exchange_diff(line.currency_id, amount,
                                                                                      amount_currency)
            line_balance = amount + exchange_diff_balance
            open_balance += (line_balance * sign)

            if line.currency_id == transaction_currency:
                open_amount_currency += amount_currency * sign
            elif line.currency_id == journal_currency:
                open_amount_currency += transaction_currency.round(amount_currency * journal_transaction_rate) * sign
            else:
                open_amount_currency += transaction_currency.round(line_balance * company_transaction_rate) * sign

        new_lines = []
        is_early_payment_discount = False
        has_exchange_diff = False
        residual_amount = company_amount + sum(line.balance for line in other_lines)
        for index, move_line in enumerate(move_lines):
            if move_line.move_id.apply_manual_currency_exchange and move_line.currency_rate:
                exchange_diff_balance = self._lines_get_account_balance_exchange_diff_cus(move_line.currency_id,
                                                                                  move_line.amount_residual,
                                                                                  move_line.amount_residual_currency, move_line)
            else:
                exchange_diff_balance = self._lines_get_account_balance_exchange_diff(move_line.currency_id,
                                                                                      move_line.amount_residual,
                                                                                      move_line.amount_residual_currency)
            has_exchange_diff = not move_line.currency_id.is_zero(exchange_diff_balance)
            current_balance = -(move_line.amount_residual + exchange_diff_balance)
            residual_amount += current_balance

            new_line_balance = current_balance
            new_amount_currency = -move_line.amount_residual_currency

            # Partial amount will be calculated only on the last invoice of the one selected by the user.
            if index == len(move_lines) - 1:
                partial_amounts = (
                    self._get_partial_amounts(current_balance, move_line, open_amount_currency, open_balance)
                    if (company_currency.compare_amounts(residual_amount, 0) < 0 if company_currency.compare_amounts(
                        company_amount, 0) > 0 else company_currency.compare_amounts(residual_amount, 0) > 0)
                    else None
                )
                if partial_amounts and not company_currency.is_zero(partial_amounts['partial_balance']):
                    new_line_balance = partial_amounts['partial_balance']
                    new_amount_currency = partial_amounts['partial_amount_currency']

            if is_early_payment_discount := move_line.move_id._is_eligible_for_early_payment_discount(
                    transaction_currency, self.date):
                new_line_balance = -move_line.amount_residual
                new_amount_currency = -move_line.amount_residual_currency

            new_lines.append(move_line._get_aml_values(
                balance=new_line_balance,
                amount_currency=new_amount_currency,
                currency_id=move_line.currency_id.id,
                reconciled_lines_ids=[Command.set(move_line.ids)],
            ))
            self.move_id._compute_checked()  # to add to compute dependencies

        if is_early_payment_discount and open_amount_currency and self._qualifies_for_early_payment(
                transaction_currency, open_amount_currency, total_early_payment_discount):
            new_lines.extend(self._set_early_payment_discount_lines(early_pay_aml_values_list, open_balance))

        self.with_context(
            no_exchange_difference_no_recursive=not has_exchange_diff)._add_move_line_to_statement_line_move(new_lines)

    def _lines_get_account_balance_exchange_diff(self, currency_id, amount, amount_currency):
        # Compute the balance of the line using the rate/currency coming from the bank transaction.
        amounts_in_st_curr = self._prepare_counterpart_amounts_using_st_line_rate(
            currency_id,
            amount,
            amount_currency,
        )
        transaction_currency_id = self.foreign_currency_id or self.currency_id
        origin_balance = amounts_in_st_curr['balance']
        if currency_id == self.company_currency_id and transaction_currency_id != self.company_currency_id:
            # The reconciliation will be expressed using the rate of the statement line.
            origin_balance = amount
        elif currency_id != self.company_currency_id and transaction_currency_id == self.company_currency_id:
            # The reconciliation will be expressed using the foreign currency of the aml to cover the Mexican case.
            # origin_balance = currency_id._convert(amount_currency, transaction_currency_id, self.company_id, self.date)
            origin_balance = currency_id._convert(amount_currency, transaction_currency_id, self.company_id, self.date)

        # Compute the exchange difference balance.
        # Useful for example when the currency has a rounding of 1 and that we have a exchange diff of 0.01, we don't want
        # the exchange diff to be created.
        if currency_id.is_zero(origin_balance - amount):
            return 0.0

        return self.company_currency_id.round(origin_balance - amount)

    def _lines_get_account_balance_exchange_diff_cus(self, currency_id, amount, amount_currency, move_line_id):
        # Compute the balance of the line using the rate/currency coming from the bank transaction.
        amounts_in_st_curr = self._prepare_counterpart_amounts_using_st_line_rate(
            currency_id,
            amount,
            amount_currency,
        )
        transaction_currency_id = self.foreign_currency_id or self.currency_id
        origin_balance = amounts_in_st_curr['balance']
        if currency_id == self.company_currency_id and transaction_currency_id != self.company_currency_id:
            # The reconciliation will be expressed using the rate of the statement line.
            origin_balance = amount
        elif currency_id != self.company_currency_id and transaction_currency_id == self.company_currency_id:
            # The reconciliation will be expressed using the foreign currency of the aml to cover the Mexican case.
            # origin_balance = currency_id._convert(amount_currency, transaction_currency_id, self.company_id, self.date)
            if move_line_id:
                origin_balance = amount_currency / move_line_id.currency_rate
            else:
                origin_balance = currency_id._convert(amount_currency, transaction_currency_id, self.company_id, self.date)

        # Compute the exchange difference balance.
        # Useful for example when the currency has a rounding of 1 and that we have a exchange diff of 0.01, we don't want
        # the exchange diff to be created.
        if currency_id.is_zero(origin_balance - amount):
            return 0.0

        return self.company_currency_id.round(origin_balance - amount)

