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


class SalesOrder(models.Model):
    _inherit = 'sale.order'

    apply_manual_currency_exchange = fields.Boolean(string='Apply Manual Currency Exchange')
    manual_currency_exchange_rate = fields.Float(string='Manual Currency Exchange Rate', digits=(12, 6))
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    active_manual_currency_rate = fields.Boolean('active Manual Currency', default=False)

    # V19  Code
    @api.onchange('company_currency_id', 'currency_id')
    def onchange_currency_id(self):
        if self.company_currency_id or self.currency_id:
            if self.company_currency_id != self.currency_id:
                self.active_manual_currency_rate = True
            else:
                self.active_manual_currency_rate = False
        else:
            self.active_manual_currency_rate = False

    # V19  Code
    @api.depends('currency_id', 'date_order', 'company_id', 'manual_currency_exchange_rate')
    def _compute_currency_rate(self):
        for order in self:
            if order.apply_manual_currency_exchange:
                order.currency_rate = order.manual_currency_exchange_rate
            else:
                order.currency_rate = self.env['res.currency']._get_conversion_rate(
                    from_currency=order.company_id.currency_id,
                    to_currency=order.currency_id,
                    company=order.company_id,
                    date=(order.date_order or fields.Datetime.now()).date(),
                )

    def _prepare_invoice(self):
        result = super(SalesOrder, self)._prepare_invoice()
        result.update({
            'active_manual_currency_rate':self.active_manual_currency_rate,
            'apply_manual_currency_exchange':self.apply_manual_currency_exchange,
            'manual_currency_exchange_rate':self.manual_currency_exchange_rate,
            })
        return result


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # V19 Code
    def _get_product_price_context(self):
        """Gives the context for product price computation.

        :return: additional context to consider extra prices from attributes in the base product price.
        :rtype: dict
        """
        self.ensure_one()
        price_context = self.product_id._get_product_price_context(
            self.product_no_variant_attribute_value_ids,
        )
        price_context.update({
            'manual_rate':self.order_id.manual_currency_exchange_rate,
            'active_manual_currency' : self.order_id.apply_manual_currency_exchange
        })
        return price_context
