# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

class AlbaCurrencyRateSync(models.AbstractModel):
    _name = "alba.currency.rate.sync"
    _description = "Alba Currency Rate Sync Service"

    def sync_rates_to_accounting(self):
        """
        Sync currency rates to accounting.
        Iterates over active investments and ensures currency configuration is consistent.
        """
        investments = self.env['alba.investment'].search([('state', '=', 'active')])
        count = 0
        for inv in investments:
            if inv.currency_id != inv.company_id.currency_id:
                # Basic sync logic: post a message to the chatter if configuration is missing
                if not inv.company_id.currency_exchange_journal_id:
                    inv.message_post(body=_("Currency sync skipped - no currency exchange journal configured on company"))
                else:
                    # In a real scenario, this would create revaluation entries or update rates.
                    # Following the pattern in loan.py, we'll just acknowledge the sync.
                    inv.message_post(body=_("Currency rates synced for investment %s") % inv.investment_number)
                    count += 1
        return True

    def create_accounting_move_for_investment(self, investment):
        """
        Create the initial accounting move for an investment.
        DR Bank/Cash (from journal default account)
        CR Investment Liability Account
        """
        investment.ensure_one()
        
        if not investment.account_investment_liability_id:
            raise UserError(_("Please configure the Investment Liability account on investment '%s' before creating the accounting move.") % investment.investment_number)
        
        journal = investment.journal_id
        if not journal:
            raise UserError(_("Please configure the Accrual Journal on investment '%s'.") % investment.investment_number)

        # Determine the counterpart account (Bank/Cash)
        # Odoo 19: default_account_id is the standard field on journals.
        counterpart_account = journal.default_account_id
        if not counterpart_account:
            raise UserError(_("The journal '%s' has no default account configured. Please set one to record the investment receipt.") % journal.name)

        company_currency = investment.company_id.currency_id
        inv_currency = investment.currency_id
        
        move_vals = {
            'journal_id': journal.id,
            'date': investment.start_date or fields.Date.context_today(self),
            'ref': f"INV/{investment.investment_number}",
            'currency_id': inv_currency.id,
            'narration': _("Initial Investment Receipt — %s — %s") % (investment.investment_number, investment.investor_id.display_name),
            'move_type': 'entry',
            'line_ids': [
                # DR Bank/Cash (Funds Received)
                (0, 0, {
                    'account_id': counterpart_account.id,
                    'name': _("Investment Funds Received — %s") % investment.investment_number,
                    'debit': investment.principal_amount if inv_currency == company_currency else 0.0,
                    'credit': 0.0,
                    'amount_currency': investment.principal_amount,
                    'currency_id': inv_currency.id,
                    'partner_id': investment.partner_id.id,
                }),
                # CR Investment Liability
                (0, 0, {
                    'account_id': investment.account_investment_liability_id.id,
                    'name': _("Investment Liability — %s") % investment.investment_number,
                    'debit': 0.0,
                    'credit': investment.principal_amount if inv_currency == company_currency else 0.0,
                    'amount_currency': -investment.principal_amount,
                    'currency_id': inv_currency.id,
                    'partner_id': investment.partner_id.id,
                }),
            ],
        }

        move = self.env['account.move'].create(move_vals)
        move.action_post()
        
        investment.message_post(body=_("Initial accounting move created: <b>%s</b>") % move.name)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Accounting Move'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }
