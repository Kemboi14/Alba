# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import logging
from .reference_utils import safe_investment_reference

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
        """
        Check FX rate coverage for the selected period.

        NOTE: this does NOT fetch or create any rates — it only reports
        which currencies already have a res.currency.rate row in range,
        and which are missing one. Actually refreshing rates from an
        external provider is a separate feature (Accounting > Configuration
        > Currencies > "Automatic Currency Rates") and is out of scope here;
        this method previously reported "Synced N rate records" as a success
        message while writing nothing, which gave false confidence that FX
        data had been refreshed.
        """
        self.ensure_one()

        currencies = self.currency_ids or self.env["res.currency"].search([
            ("active", "=", True),
            ("id", "!=", self.company_id.currency_id.id)  # Exclude company's base currency
        ])

        if not currencies:
            raise UserError(_("No currencies selected or available to check."))

        covered = []
        missing = []

        for currency in currencies:
            rates = self.env["res.currency.rate"].search([
                ("currency_id", "=", currency.id),
                ("name", ">=", self.date_from),
                ("name", "<=", self.date_to),
            ])
            if rates:
                covered.append("%s (%d rate(s))" % (currency.name, len(rates)))
            else:
                missing.append(currency.name)
                _logger.warning(
                    "Currency rate coverage check: no rate found for %s "
                    "between %s and %s.",
                    currency.name, self.date_from, self.date_to,
                )

        message = _(
            "Rate coverage for %(date_from)s to %(date_to)s:\n"
            "Covered: %(covered)s\n"
            "Missing: %(missing)s\n\n"
            "This check does not fetch new rates. Configure automatic "
            "rate updates under Accounting > Configuration > Currencies, "
            "or enter missing rates manually, then re-run this check."
        ) % {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "covered": ", ".join(covered) if covered else _("none"),
            "missing": ", ".join(missing) if missing else _("none"),
        }

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Rate Coverage Check"),
                "message": message,
                "type": "warning" if missing else "success",
                "sticky": bool(missing),
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
