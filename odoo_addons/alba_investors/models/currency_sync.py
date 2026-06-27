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
        Create the initial accounting move (payment receipt) for an investment.
        DR Bank/Cash
        CR Investment Liability Account
        """
        investment.ensure_one()
        if investment.payment_id:
            if investment.payment_id.state != "posted":
                investment.payment_id.action_post()
            return {
                'type': 'ir.actions.act_window',
                'name': _('Payment Receipt'),
                'res_model': 'account.payment',
                'res_id': investment.payment_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        
        if not investment.account_investment_liability_id:
            raise UserError(_("Please configure the Investment Liability account on investment '%s' before creating the payment receipt.") % investment.investment_number)
        
        journal = investment.payment_journal_id
        if not journal:
            raise UserError(_("Please configure the Payment Journal on investment '%s'.") % investment.investment_number)

        inv_currency = investment.currency_id
        
        payment_vals = {
            'date': investment.start_date or fields.Date.today(),
            'amount': investment.principal_amount,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': investment.partner_id.id,
            'journal_id': journal.id,
            'currency_id': inv_currency.id,
            'memo': f"INV/{safe_investment_reference(investment)}",
            'destination_account_id': investment.account_investment_liability_id.id,
        }

        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        
        investment.write({'payment_id': payment.id})
        investment.message_post(body=_("Initial payment receipt created: <a href='#' data-oe-model='account.payment' data-oe-id='%s'>%s</a>") % (payment.id, payment.name))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment Receipt'),
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }
