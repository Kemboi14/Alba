# -*- coding: utf-8 -*-

from odoo import fields, models

class AlbaMpesaTransactionInvestor(models.Model):
    _inherit = "alba.mpesa.transaction"

    investor_id = fields.Many2one(
        "alba.investor",
        string="Investor",
        index=True,
        ondelete="set null",
        help="Populated for B2C payouts to investors.",
    )
