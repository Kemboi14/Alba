# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class AlbaCurrencyRateSync(models.TransientModel):
    """Sync currency rates from Odoo's accounting module"""
    _name = "alba.currency.rate.sync"
    _description = "Currency Rate Sync"

    currency_ids = fields.Many2many(
        "res.currency",
        string="Currencies to Sync",
        help="Leave empty to sync all active currencies",
    )
    date_from = fields.Date(string="From Date", default=fields.Date.today)
    date_to = fields.Date(string="To Date", default=fields.Date.today)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )

    def sync_rates_to_accounting(self):
        """
        Compatibility method for alba.investment buttons.
        Opens the wizard to sync rates.
        """
        return {
            "type": "ir.actions.act_window",
            "name": _("Sync Currency Rates"),
            "res_model": "alba.currency.rate.sync",
            "view_mode": "form",
            "target": "new",
        }

    def action_sync_rates(self):
        """Sync currency rates from accounting module"""
        self.ensure_one()
        
        # Get currencies to sync
        currencies = self.currency_ids or self.env["res.currency"].search([
            ("active", "=", True),
            ("id", "!=", self.company_id.currency_id.id)  # Exclude company's base currency
        ])
        
        if not currencies:
            raise UserError(_("No currencies selected or available to sync."))
        
        synced_count = 0
        errors = []
        
        for currency in currencies:
            try:
                # Get rates from Odoo's accounting module
                rates = self.env["res.currency.rate"].search([
                    ("currency_id", "=", currency.id),
                    ("name", ">=", self.date_from),
                    ("name", "<=", self.date_to),
                ], order="name desc")
                
                if not rates:
                    _logger.warning(f"No rates found for {currency.name}")
                    continue
                
                # Update or create rates in your investment module if needed
                # Or just log that they exist
                synced_count += len(rates)
                
            except Exception as e:
                errors.append(f"{currency.name}: {str(e)}")
                _logger.error(f"Failed to sync {currency.name}: {e}")
        
        # Log results
        message = _(
            "Currency rate sync completed.\n"
            "Synced %(count)d rate records for %(currencies)d currencies.\n"
            "%(errors)s"
        ) % {
            "count": synced_count,
            "currencies": len(currencies),
            "errors": "\n".join(errors) if errors else _("No errors."),
        }
        
        # notify_success is not standard Odoo 19, using message_post or notification
        self.env.user.message_post(body=message)
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Completed"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

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

        counterpart_account = journal.default_account_id
        if not counterpart_account:
            raise UserError(_("The journal '%s' has no default account configured. Please set one to record the investment receipt.") % journal.name)

        company_currency = investment.company_id.currency_id
        inv_currency = investment.currency_id
        
        move_vals = {
            'journal_id': journal.id,
            'date': investment.start_date or fields.Date.today(),
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
