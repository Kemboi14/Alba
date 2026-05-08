# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AlbaCurrencyConfig(models.Model):
    """Currency Configuration for multi-currency support"""
    _name = "alba.currency.config"
    _description = "Currency Configuration"
    _rec_name = "currency_id"
    
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(
        string="Name",
        related="currency_id.name",
        store=True,
        readonly=True,
    )
    symbol = fields.Char(
        string="Symbol",
        related="currency_id.symbol",
        readonly=True,
    )
    is_default = fields.Boolean(
        string="Default Currency",
        default=False,
        help="Check if this is the default currency for the company",
    )
    is_active = fields.Boolean(
        string="Active",
        default=True,
    )
    
    # Exchange Rate Configuration
    exchange_rate_manual = fields.Float(
        string="Manual Exchange Rate",
        digits=(12, 6),
        help="Manual exchange rate against company currency",
    )
    use_manual_rate = fields.Boolean(
        string="Use Manual Rate",
        default=False,
        help="If checked, manual rate will be used instead of automatic rates",
    )
    
    # Currency-specific accounts
    account_receivable_id = fields.Many2one(
        "account.account",
        string="Receivable Account",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Default account for receivables in this currency",
    )
    account_payable_id = fields.Many2one(
        "account.account",
        string="Payable Account",
        domain="[('account_type', '=', 'liability_payable')]",
        help="Default account for payables in this currency",
    )
    
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
    )
    
    _sql_constraints = [
        ("unique_currency_company", "unique(currency_id, company_id)", "Currency configuration must be unique per company!"),
    ]
    
    @api.onchange("is_default")
    def _onchange_is_default(self):
        """Ensure only one default currency per company"""
        if self.is_default:
            # Uncheck other default currencies for this company
            other_defaults = self.search([
                ("is_default", "=", True),
                ("company_id", "=", self.company_id.id),
                ("id", "!=", self._origin.id if self._origin else False),
            ])
            other_defaults.write({"is_default": False})


class AlbaExchangeRateHistory(models.Model):
    """Exchange Rate History for audit trail"""
    _name = "alba.exchange.rate.history"
    _description = "Exchange Rate History"
    _order = "date desc, id desc"
    
    date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.today,
        index=True,
    )
    from_currency_id = fields.Many2one(
        "res.currency",
        string="From Currency",
        required=True,
        ondelete="restrict",
    )
    to_currency_id = fields.Many2one(
        "res.currency",
        string="To Currency",
        required=True,
        ondelete="restrict",
    )
    rate = fields.Float(
        string="Exchange Rate",
        digits=(12, 6),
        required=True,
        help="Rate to convert from_currency to to_currency",
    )
    inverse_rate = fields.Float(
        string="Inverse Rate",
        digits=(12, 6),
        compute="_compute_inverse_rate",
        store=True,
    )
    source = fields.Selection([
        ("auto", "Automatic - Bank Rate"),
        ("manual", "Manual Entry"),
        ("api", "External API"),
    ], string="Source", default="manual", required=True)
    notes = fields.Text(string="Notes")
    
    created_by = fields.Many2one(
        "res.users",
        string="Created By",
        default=lambda self: self.env.uid,
        readonly=True,
    )
    
    @api.depends("rate")
    def _compute_inverse_rate(self):
        for rec in self:
            rec.inverse_rate = 1.0 / rec.rate if rec.rate else 0.0
