# -*- coding: utf-8 -*-

from odoo import models, fields, api, _





class AccountJournal(models.Model):
    _inherit = "account.journal"

    def create_internal_transfer_payment(self):
        """return action to create a internal transfer payment"""
        return self.open_payments_action('transfer', mode='form')

