# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


INVESTOR_DOCUMENT_TYPES = [
    ("id_card", "ID Card / Passport"),
    ("agreement", "Investment Agreement"),
    ("nda", "NDA"),
    ("tax_certificate", "Tax Certificate (KRA PIN)"),
    ("proof_of_funds", "Proof of Funds"),
    ("other", "Other"),
]


class AlbaInvestmentProduct(models.Model):
    _name = "alba.investment.product"
    _description = "Alba Investment Product Configuration"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
    )
    investment_type = fields.Selection(
        [
            ("fixed_term", "Fixed Term"),
            ("open_ended", "Open Ended"),
        ],
        required=True,
        default="fixed_term",
        tracking=True,
    )
    interest_rate = fields.Float(
        string="Annual Interest Rate (%)",
        digits=(5, 4),
        required=True,
        default=0.0,
        tracking=True,
    )
    compounding_frequency = fields.Selection(
        [
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("annually", "Annually"),
        ],
        required=True,
        default="monthly",
        tracking=True,
    )
    default_principal = fields.Monetary(
        string="Default Principal",
        currency_field="currency_id",
        default=0.0,
        help="Optional default principal amount when creating a new investment from this product.",
    )
    is_default = fields.Boolean(
        string="Default Product",
        default=False,
        tracking=True,
        help="Mark this product as the default for its investment type, currency and company. "
             "Only one product per type/currency/company combination can be the default.",
    )
    auto_accrual_day = fields.Integer(
        string="Automated Accrual Day of Month",
        default=28,
        required=True,
        tracking=True,
        help="The day of the month (1-31) when automated interest accrual should run for this product.",
    )
    early_withdrawal_notice_days = fields.Integer(
        string="Early Withdrawal Notice Days",
        default=60,
        required=True,
        help="Minimum notice period before paying out a fixed-term investment before maturity.",
    )

    account_interest_expense_id = fields.Many2one(
        "account.account",
        string="Interest Expense Account",
        domain="[('account_type', '=', 'expense')]",
        tracking=True,
    )
    account_interest_payable_id = fields.Many2one(
        "account.account",
        string="Interest Payable Account",
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current'])]",
        tracking=True,
    )
    account_investment_liability_id = fields.Many2one(
        "account.account",
        string="Investment Liability Account",
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current'])]",
        tracking=True,
    )
    account_long_term_liability_id = fields.Many2one(
        "account.account",
        string="Long-term Investment Liability Account",
        domain="[('account_type', '=', 'liability_non_current')]",
        tracking=True,
        help="Account used for investments with tenure > 1 year.",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Accrual Journal",
        domain="[('type', '=', 'general')]",
        tracking=True,
    )
    payment_journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        tracking=True,
    )
    wht_rate = fields.Float(
        string="Withholding Tax Rate (%)",
        default=15.0,
        tracking=True,
    )
    account_wht_payable_id = fields.Many2one(
        "account.account",
        string="WHT Payable Account",
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current', 'liability_payable'])]",
        tracking=True,
    )
    required_document_ids = fields.One2many(
        "alba.investment.required.document",
        "product_id",
        string="Mandatory Documents",
    )
    investment_count = fields.Integer(compute="_compute_investment_count")

    _code_company_unique = models.Constraint(
        "UNIQUE(code, company_id)",
        "An investment product with this code already exists for this company.",
    )
    _notice_days_non_negative = models.Constraint(
        "CHECK(early_withdrawal_notice_days >= 0)",
        "Early withdrawal notice days cannot be negative.",
    )

    @api.constrains("interest_rate")
    def _check_interest_rate(self):
        for rec in self:
            if rec.interest_rate < 0 or rec.interest_rate > 1200:
                raise ValidationError(_("Interest rate must be between 0 and 1200 (max 100% per month)."))

    @api.constrains("auto_accrual_day")
    def _check_auto_accrual_day(self):
        for rec in self:
            if rec.auto_accrual_day < 1 or rec.auto_accrual_day > 31:
                raise ValidationError(_("Automated accrual day must be between 1 and 31."))

    @api.constrains("is_default", "investment_type", "currency_id", "company_id")
    def _check_single_default_per_type_currency_company(self):
        """Ensure only one product is marked as default per type/currency/company."""
        for rec in self:
            if not rec.is_default:
                continue
            duplicate = self.search([
                ("id", "!=", rec.id),
                ("is_default", "=", True),
                ("investment_type", "=", rec.investment_type),
                ("currency_id", "=", rec.currency_id.id),
                ("company_id", "=", rec.company_id.id),
                ("active", "=", True),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    _(
                        "'%s' is already marked as the default for %s / %s. "
                        "Please unset it there before marking this product as default."
                    ) % (duplicate.name, rec.currency_id.name, dict(rec._fields['investment_type'].selection).get(rec.investment_type))
                )

    def _compute_investment_count(self):
        Investment = self.env["alba.investment"]
        for rec in self:
            rec.investment_count = Investment.search_count([("investment_product_id", "=", rec.id)])

    def action_view_investments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Investments - %s") % self.name,
            "res_model": "alba.investment",
            "view_mode": "list,kanban,form",
            "domain": [("investment_product_id", "=", self.id)],
            "context": {"default_investment_product_id": self.id},
        }

    @api.model
    def _default_product_for(self, investment_type, currency_id, company_id=None):
        """Return the default product for the given type/currency/company.
        Prefers the product explicitly marked as is_default=True.
        Falls back to the first active product if none is explicitly marked.
        """
        company_id = company_id or self.env.company.id
        base_domain = [
            ("active", "=", True),
            ("investment_type", "=", investment_type or "fixed_term"),
            ("currency_id", "=", currency_id or self.env.company.currency_id.id),
            ("company_id", "=", company_id),
        ]
        # First try to find the explicitly marked default
        product = self.search(base_domain + [("is_default", "=", True)], limit=1)
        if not product:
            # Fall back to the first available product (legacy behaviour)
            product = self.search(base_domain, limit=1)
        return product

    def action_ensure_accounting_defaults(self):
        for product in self:
            product._ensure_accounting_defaults()
        return True

    def _ensure_accounting_defaults(self):
        """Auto-detect and fill missing accounting defaults for this product.

        Strategy (in priority order):
        1. Copy from a sibling product (same type + company, any currency) that already
           has accounts configured.  This lets a new KES tier inherit all the same
           ledgers as an existing KES/USD product without re-entering them.
           Journals are NOT copied this way — a different-currency product may use
           different bank accounts, so those still fall through to the search heuristic.
        2. Search the chart of accounts by account_type and name hints.
        3. Fall back to the first matching account by type alone.
        """
        self.ensure_one()
        Account = self.env["account.account"]
        Journal = self.env["account.journal"]
        changes = {}

        # ── Step 1: inherit from a configured sibling product of the same currency ──
        sibling = self.search([
            ("id", "!=", self.id),
            ("active", "=", True),
            ("investment_type", "=", self.investment_type),
            ("company_id", "=", self.company_id.id),
            ("currency_id", "=", self.currency_id.id),
        ], order="is_default desc, id asc", limit=1)

        inheritable_fields = [
            "account_interest_expense_id",
            "account_interest_payable_id",
            "account_investment_liability_id",
            "account_long_term_liability_id",
            "account_wht_payable_id",
            "journal_id",
            "payment_journal_id",
        ]
        if sibling:
            for field_name in inheritable_fields:
                if not self[field_name] and sibling[field_name]:
                    changes[field_name] = sibling[field_name].id
            # Inherit WHT rate too if this product has the default value (15)
            # and the sibling has a non-zero configured rate
            if self.wht_rate == 15.0 and sibling.wht_rate and sibling.wht_rate != 15.0:
                changes["wht_rate"] = sibling.wht_rate

        # ── Step 2: search the chart of accounts by name hints ───────────────
        def _find_account(type_list, name_hint, fallback_hints=None):
            acc = Account.search(
                [("account_type", "in", type_list), ("name", "ilike", name_hint)],
                limit=1,
            )
            if acc:
                return acc
            for hint in fallback_hints or []:
                acc = Account.search(
                    [("account_type", "in", type_list), ("name", "ilike", hint)],
                    limit=1,
                )
                if acc:
                    return acc
            return Account.search([("account_type", "in", type_list)], limit=1)

        if not self.account_interest_expense_id and "account_interest_expense_id" not in changes:
            acc = _find_account(["expense"], "interest", ["finance", "expense"])
            if acc:
                changes["account_interest_expense_id"] = acc.id
        if not self.account_interest_payable_id and "account_interest_payable_id" not in changes:
            acc = _find_account(
                ["liability_current", "liability_non_current"],
                "interest",
                ["payable", "liability"],
            )
            if acc:
                changes["account_interest_payable_id"] = acc.id
        if not self.account_investment_liability_id and "account_investment_liability_id" not in changes:
            acc = _find_account(
                ["liability_current", "liability_non_current"],
                "investment",
                ["deposit", "payable", "liability"],
            )
            if acc:
                changes["account_investment_liability_id"] = acc.id
        if not self.account_wht_payable_id and "account_wht_payable_id" not in changes:
            acc = _find_account(
                ["liability_current", "liability_non_current", "liability_payable"],
                "tax",
                ["withholding", "payable"],
            )
            if acc:
                changes["account_wht_payable_id"] = acc.id

        # ── Step 3: journals (not inherited cross-currency) ───────────────────
        if not self.journal_id:
            journal = Journal.search(
                [("type", "=", "general"), ("company_id", "=", self.company_id.id)],
                limit=1,
            )
            if journal:
                changes["journal_id"] = journal.id
        if not self.payment_journal_id:
            journal = Journal.search(
                [("type", "in", ["bank", "cash"]), ("company_id", "=", self.company_id.id)],
                limit=1,
            )
            if journal:
                changes["payment_journal_id"] = journal.id

        if changes:
            self.write(changes)

        missing = [
            label
            for field_name, label in [
                ("account_interest_expense_id", _("Interest Expense Account")),
                ("account_interest_payable_id", _("Interest Payable Account")),
                ("account_investment_liability_id", _("Investment Liability Account")),
                ("journal_id", _("Accrual Journal")),
                ("payment_journal_id", _("Payment Journal")),
                ("account_wht_payable_id", _("WHT Payable Account")),
            ]
            if not self[field_name]
        ]
        if missing:
            raise UserError(_("Please configure: %s") % ", ".join(missing))
        return True


class AlbaInvestmentRequiredDocument(models.Model):
    _name = "alba.investment.required.document"
    _description = "Investment Mandatory Document"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        "alba.investment.product",
        required=True,
        ondelete="cascade",
    )
    document_type = fields.Selection(
        INVESTOR_DOCUMENT_TYPES,
        required=True,
    )
    name = fields.Char(required=True)
    require_verified = fields.Boolean(
        string="Must Be Verified",
        default=False,
        help="If enabled, uploaded documents must be verified before activation.",
    )

    _product_document_unique = models.Constraint(
        "UNIQUE(product_id, document_type)",
        "This mandatory document is already configured for the product.",
    )
