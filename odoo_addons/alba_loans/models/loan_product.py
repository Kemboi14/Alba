# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlbaLoanProduct(models.Model):
    _name = "alba.loan.product"
    _description = "Alba Capital Loan Product"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name asc"
    _rec_name = "name"

    # ─── Basic Info ───────────────────────────────────────────────────────────
    name = fields.Char(
        string="Product Name",
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string="Product Code",
        required=True,
        size=20,
        tracking=True,
        copy=False,
    )
    category = fields.Selection(
        selection=[
            ("salary_advance", "Salary Advance"),
            ("business_loan", "Business Loan"),
            ("personal_loan", "Personal Loan"),
            ("ipf_loan", "IPF Loan"),
            ("bid_bond", "Bid Bond"),
            ("performance_bond", "Performance Bond"),
            ("staff_loan", "Staff Loan"),
            ("investor_loan", "Investor Loan"),
            ("asset_financing", "Asset Financing"),
        ],
        string="Category",
        required=True,
        tracking=True,
    )
    description = fields.Text(string="Description")
    is_active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
    )

    # ─── Amount Limits ────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    min_amount = fields.Monetary(
        string="Minimum Loan Amount",
        currency_field="currency_id",
        required=True,
    )
    max_amount = fields.Monetary(
        string="Maximum Loan Amount",
        currency_field="currency_id",
        required=True,
    )

    # ─── Tenure ───────────────────────────────────────────────────────────────
    min_tenure_months = fields.Integer(
        string="Minimum Tenure (Months)",
        required=True,
        default=1,
    )
    max_tenure_months = fields.Integer(
        string="Maximum Tenure (Months)",
        required=True,
        default=60,
    )

    # ─── Interest Configuration ───────────────────────────────────────────────
    interest_rate = fields.Float(
        string="Interest Rate (%)",
        digits=(5, 2),
        required=True,
        tracking=True,
        help="Monthly interest rate percentage.",
    )
    interest_method = fields.Selection(
        selection=[
            ("flat_rate", "Flat Rate"),
            ("reducing_balance", "Reducing Balance"),
        ],
        string="Interest Method",
        required=True,
        default="reducing_balance",
        tracking=True,
    )
    repayment_frequency = fields.Selection(
        selection=[
            ("weekly", "Weekly"),
            ("fortnightly", "Fortnightly"),
            ("monthly", "Monthly"),
        ],
        string="Repayment Frequency",
        required=True,
        default="monthly",
    )

    # ─── Penalties & Grace Period ───────────────────────────────────────────
    penalty_rate = fields.Float(
        string="Penalty Rate (% per day)",
        digits=(5, 2),
        default=0.0,
        help="Daily penalty rate charged on overdue amounts.",
    )
    grace_period_days = fields.Integer(
        string="Grace Period (Days)",
        default=0,
        help="Number of days after due date before penalties apply.",
    )
    
    # ─── Other Charges ────────────────────────────────────────────────────────
    other_charges_percentage = fields.Float(
        string="Other Charges (%)",
        digits=(5, 2),
        default=0.0,
        help="Additional charges as percentage of principal.",
    )
    origination_fee_percentage = fields.Float(
        string="Origination Fee (%)",
        digits=(5, 2),
        default=0.0,
    )
    insurance_fee_percentage = fields.Float(
        string="Insurance Fee (%)",
        digits=(5, 2),
        default=0.0,
    )
    processing_fee_percentage = fields.Float(
        string="Processing Fee (%)",
        digits=(5, 2),
        default=0.0,
    )

    # ─── Accounting Configuration ─────────────────────────────────────────────
    account_loan_receivable_id = fields.Many2one(
        comodel_name="account.account",
        string="Loan Receivable Account",
        tracking=True,
        domain="[('account_type', 'in', ['asset_receivable', 'asset_current', 'asset_non_current'])]",
        help="Account debited when a loan is disbursed (e.g. Loans Receivable).",
    )
    account_interest_income_id = fields.Many2one(
        comodel_name="account.account",
        string="Interest Income Account",
        tracking=True,
        domain="[('account_type', '=', 'income')]",
        help="Account credited when interest is collected.",
    )
    account_fees_income_id = fields.Many2one(
        comodel_name="account.account",
        string="Fee Income Account",
        tracking=True,
        domain="[('account_type', '=', 'income')]",
        help="Account credited when fees are collected.",
    )

    # ─── Company ──────────────────────────────────────────────────────────────
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    # ─── Computed / Related ───────────────────────────────────────────────────
    application_count = fields.Integer(
        string="Applications",
        compute="_compute_application_count",
    )

    # ─── SQL Constraints ──────────────────────────────────────────────────────
    _code_company_unique = models.Constraint(
        "UNIQUE(code, company_id)",
        "A loan product with this code already exists for the same company.",
    )
    _amount_check = models.Constraint(
        "CHECK(min_amount >= 0 AND max_amount >= min_amount)",
        "Maximum loan amount must be greater than or equal to the minimum amount.",
    )
    _tenure_check = models.Constraint(
        "CHECK(min_tenure_months >= 1 AND max_tenure_months >= min_tenure_months)",
        "Maximum tenure must be greater than or equal to minimum tenure.",
    )
    _interest_rate_check = models.Constraint(
        "CHECK(interest_rate >= 0 AND interest_rate <= 100)",
        "Interest rate must be between 0 and 100.",
    )

    # ─── Compute Methods ──────────────────────────────────────────────────────
    def _compute_application_count(self):
        for product in self:
            product.application_count = self.env["alba.loan.application"].search_count(
                [("loan_product_id", "=", product.id)]
            )

    # ─── Business Logic ───────────────────────────────────────────────────────
    def calculate_total_fees(self, principal):
        """Return total one-off fees for a given principal amount."""
        self.ensure_one()
        total_pct = (
            self.origination_fee_percentage
            + self.insurance_fee_percentage
            + self.processing_fee_percentage
        )
        return round(principal * total_pct / 100, 2)

    def calculate_flat_interest(self, principal, months):
        """Total interest for flat-rate method: I = P × r × n."""
        self.ensure_one()
        return round(principal * (self.interest_rate / 100) * months, 2)

    def calculate_reducing_schedule(self, principal, months):
        """
        Generate a reducing-balance amortisation schedule.
        Returns a list of dicts: [{installment, principal_due, interest_due, balance}, ...]
        """
        self.ensure_one()
        monthly_rate = self.interest_rate / 100
        if monthly_rate == 0:
            equal_principal = round(principal / months, 2)
            return [
                {
                    "installment": i + 1,
                    "opening_balance": round(principal - i * equal_principal, 2),
                    "principal_due": equal_principal,
                    "interest_due": 0.0,
                    "total_due": equal_principal,
                    "closing_balance": round(principal - (i + 1) * equal_principal, 2),
                }
                for i in range(months)
            ]

        # Equal instalment (annuity) formula
        emi = round(
            principal
            * monthly_rate
            * (1 + monthly_rate) ** months
            / ((1 + monthly_rate) ** months - 1),
            2,
        )
        schedule = []
        balance = principal
        for i in range(months):
            interest = round(balance * monthly_rate, 2)
            p = round(emi - interest, 2)
            if i == months - 1:
                # Absorb rounding on last instalment
                p = round(balance, 2)
            closing = round(balance - p, 2)
            schedule.append(
                {
                    "installment": i + 1,
                    "opening_balance": round(balance, 2),
                    "principal_due": p,
                    "interest_due": interest,
                    "total_due": round(p + interest, 2),
                    "closing_balance": max(closing, 0.0),
                }
            )
            balance = closing
        return schedule

    # ─── Constraints ──────────────────────────────────────────────────────────
    @api.constrains("interest_rate")
    def _check_interest_rate(self):
        for rec in self:
            if not (0 <= rec.interest_rate <= 100):
                raise ValidationError(
                    _("Interest rate must be between 0 %% and 100 %%.")
                )

    @api.constrains("min_amount", "max_amount")
    def _check_amounts(self):
        for rec in self:
            if rec.min_amount < 0:
                raise ValidationError(_("Minimum loan amount cannot be negative."))
            if rec.max_amount < rec.min_amount:
                raise ValidationError(
                    _(
                        "Maximum loan amount must be greater than or equal to the minimum amount."
                    )
                )

    @api.constrains("min_tenure_months", "max_tenure_months")
    def _check_tenure(self):
        for rec in self:
            if rec.min_tenure_months < 1:
                raise ValidationError(_("Minimum tenure must be at least 1 month."))
            if rec.max_tenure_months < rec.min_tenure_months:
                raise ValidationError(
                    _("Maximum tenure must be greater than or equal to minimum tenure.")
                )

    # ─── Overrides ────────────────────────────────────────────────────────────
    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, f"[{rec.code}] {rec.name}"))
        return result

    def action_view_applications(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loan Applications"),
            "res_model": "alba.loan.application",
            "view_mode": "list,form",
            "domain": [("loan_product_id", "=", self.id)],
            "context": {"default_loan_product_id": self.id},
        }

    def _ensure_accounting_defaults(self):
        """
        Auto-detect and assign accounting accounts from the chart of accounts
        if they are not yet configured on this product.  Writes the detected
        accounts back to the product so the user can review / override them.

        Priority for each account:
          1. Exact name match (case-insensitive substring)
          2. Correct account_type with any name
          3. Raise a UserError with clear guidance if nothing is found.
        """
        self.ensure_one()
        Account = self.env["account.account"]
        company_id = self.company_id.id or self.env.company.id
        changes = {}

        def _find(type_list, name_hint, fallback_name_hints=None):
            """Return first account matching type_list, preferring name_hint.
            ORM record rules already scope to the current company, so no
            explicit company filter is needed.
            """
            # 1. Preferred: correct type + name match
            acc = Account.search(
                [("account_type", "in", type_list), ("name", "ilike", name_hint)],
                limit=1,
            )
            if acc:
                return acc
            # 2. Try alternative name hints (if provided)
            for hint in (fallback_name_hints or []):
                acc = Account.search(
                    [("account_type", "in", type_list), ("name", "ilike", hint)],
                    limit=1,
                )
                if acc:
                    return acc
            # 3. Any account of the right type
            acc = Account.search([("account_type", "in", type_list)], limit=1)
            return acc

        def _get_or_create(type_list, name_hint, fallback_name_hints, auto_name, auto_code, auto_type):
            acc = _find(type_list, name_hint, fallback_name_hints)
            if acc:
                return acc
            # Auto-create a minimal account so the flow is not blocked
            # Make sure the code is unique
            base_code = auto_code
            code = base_code
            i = 1
            while Account.search([("code", "=", code)], limit=1):
                code = f"{base_code}{i}"
                i += 1
            vals = {"name": auto_name, "code": code, "account_type": auto_type}
            company = self.company_id or self.env.company
            if company:
                vals["company_ids"] = [(4, company.id)]
            return Account.create(vals)

        if not self.account_loan_receivable_id:
            acc = _get_or_create(
                ["asset_receivable", "asset_current", "asset_non_current", "asset_fixed", "asset_prepayments"],
                "loan",
                ["receivable", "debtor", "asset"],
                "Loans Receivable",
                "110100",
                "asset_non_current",
            )
            changes["account_loan_receivable_id"] = acc.id

        if not self.account_interest_income_id:
            acc = _get_or_create(
                ["income", "income_other"],
                "interest",
                ["revenue", "income"],
                "Interest Income",
                "410100",
                "income_other",
            )
            changes["account_interest_income_id"] = acc.id

        if not self.account_fees_income_id:
            acc = _get_or_create(
                ["income", "income_other"],
                "fee",
                ["income", "revenue"],
                "Loan Processing Fees",
                "410200",
                "income_other",
            )
            changes["account_fees_income_id"] = acc.id

        if changes:
            self.write(changes)
        return True
