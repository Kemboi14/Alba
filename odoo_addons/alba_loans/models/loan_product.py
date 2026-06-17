# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlbaLoanCategory(models.Model):
    """Loan Category - Defines grouping and defaults for products"""
    _name = "alba.loan.category"
    _description = "Loan Category"
    _order = "sequence, name"
    
    name = fields.Char(string="Category Name", required=True, translate=True)
    code = fields.Char(string="Category Code", required=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string="Color Index", default=0)
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    
    product_count = fields.Integer(compute="_compute_product_count")
    
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = self.env["alba.loan.product"].search_count([("category_id", "=", rec.id)])


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
    )
    code = fields.Char(
        string="Product Code",
        required=True,
        size=20,
        copy=False,
    )
    category_id = fields.Many2one(
        "alba.loan.category",
        string="Category",
        required=False,
        default=lambda self: self.env["alba.loan.category"].search([], limit=1).id,
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
        string="Old Category (Legacy)",
        help="Maintained for migration/legacy sync",
    )
    color = fields.Integer(
        string="Color Index",
        default=0,
        help="Color used in Kanban and Tree views.",
    )
    description = fields.Text(string="Description")
    is_active = fields.Boolean(
        string="Active",
        default=True,
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )

    # ─── Amount Limits ────────────────────────────────────────────────────────
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
    provision_rate = fields.Float(
        string="Default Provisioning Rate (%)",
        digits=(5, 2),
        default=1.0,
        help="Base provisioning rate for Normal loans. Substandard/Doubtful/Loss rates are fixed by company policy.",
    )
    
    # ─── Automation ───────────────────────────────────────────────────────────
    auto_approve_score_threshold = fields.Integer(
        string="Auto-Approve Score Threshold",
        default=85,
        help="Applications with a credit score above this threshold can be auto-approved.",
    )
    auto_disburse = fields.Boolean(
        string="Auto-Disburse via M-Pesa B2C",
        default=False,
        help="If ticked, approved applications will automatically trigger a B2C API call to disburse funds instantly.",
    )

    # ─── Product Requirements (drive UI visibility) ───────────────────────────
    # These flags tell the loan application form EXACTLY what to show/hide.
    # Set these when configuring a product — zero guessing for staff.
    requires_employer = fields.Boolean(
        string="Requires Employer Details",
        default=False,
        help="Show employer, job title, and payslip fields on the application.",
    )
    requires_guarantor = fields.Boolean(
        string="Requires Guarantor",
        default=False,
        help="Show guarantors tab and enforce guarantor confirmation before disbursement.",
    )
    min_guarantors = fields.Integer(
        string="Minimum Guarantors",
        default=0,
        help="Minimum number of confirmed guarantors required before disbursement.",
    )
    requires_collateral = fields.Boolean(
        string="Requires Collateral",
        default=False,
        help="Show collateral tab and enforce collateral pledge before disbursement.",
    )
    requires_business_info = fields.Boolean(
        string="Requires Business Information",
        default=False,
        help="Show business name, registration, type, and revenue fields.",
    )
    requires_payslip = fields.Boolean(
        string="Requires Payslip / Proof of Income",
        default=False,
        help="Enforce payslip document upload before submission.",
    )
    requires_business_reg = fields.Boolean(
        string="Requires Business Registration Docs",
        default=False,
        help="Enforce business registration certificate upload.",
    )

    # ─── Fees & Charges (New Product-based Architecture) ──────────────────────
    fee_template_ids = fields.One2many(
        "alba.loan.fee.template",
        "product_id",
        string="Fee Templates",
        help="Configure standard fees (Processing, Insurance, Tracking, etc.) as products.",
    )

    def calculate_total_fees(self, amount):
        """Calculate total fees based on configured templates."""
        self.ensure_one()
        total_fees = 0.0
        for template in self.fee_template_ids:
            if template.fee_type == "fixed":
                total_fees += template.amount
            else:
                total_fees += amount * (template.amount / 100.0)
        return total_fees

    # ─── Accounting Configuration ─────────────────────────────────────────────
    account_loan_receivable_id = fields.Many2one(
        comodel_name="account.account",
        string="Loan Receivable Account",
        domain="[('account_type', 'in', ['asset_receivable', 'asset_current', 'asset_non_current'])]",
        help="Account debited when a loan is disbursed (e.g. Loans Receivable).",
    )
    account_interest_income_id = fields.Many2one(
        comodel_name="account.account",
        string="Interest Income Account",
        domain="[('account_type', '=', 'income')]",
        help="Account credited when interest is collected.",
    )
    account_fees_income_id = fields.Many2one(
        comodel_name="account.account",
        string="Fee Income Account",
        domain="[('account_type', '=', 'income')]",
        help="Account credited when fees are collected.",
    )
    account_penalty_income_id = fields.Many2one(
        comodel_name="account.account",
        string="Penalty Income Account",
        domain="[('account_type', '=', 'income')]",
        help="Account credited when penalty interest/fees are collected.",
    )
    account_penalty_receivable_id = fields.Many2one(
        comodel_name="account.account",
        string="Penalty Receivable Account",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Account for tracking accrued penalty fees that haven't been collected yet.",
    )
    account_clearing_id = fields.Many2one(
        comodel_name="account.account",
        string="Loan Clearing Account",
        domain="[('account_type', 'in', ['asset_current', 'liability_current'])]",
        help="Intermediary account for disbursements. DR Loan Receivable, CR Clearing; then Entry 2 clears this account.",
    )
    account_interest_receivable_id = fields.Many2one(
        comodel_name="account.account",
        string="Interest Receivable Account",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Account for tracking accrued interest that hasn't been collected yet.",
    )
    account_outstanding_payments_id = fields.Many2one(
        comodel_name="account.account",
        string="Outstanding Payments Account",
        domain="[('account_type', '=', 'asset_current')]",
        help="Bank/Cash transit account for outbound payments (Entry 2).",
    )
    account_outstanding_receipts_id = fields.Many2one(
        comodel_name="account.account",
        string="Outstanding Receipts Account",
        domain="[('account_type', '=', 'asset_current')]",
        help="Bank/Cash transit account for inbound receipts (Entry 4).",
    )
    account_provision_id = fields.Many2one(
        comodel_name="account.account",
        string="Provision Account (Asset Offset)",
        domain="[('account_type', '=', 'asset_current')]",
        help="The allowance for credit losses account (Contra-asset).",
    )
    account_provision_expense_id = fields.Many2one(
        comodel_name="account.account",
        string="Provision Expense Account",
        domain="[('account_type', '=', 'expense')]",
        help="The expense account for loan loss provisioning.",
    )
    account_interest_expense_id = fields.Many2one(
        comodel_name="account.account",
        string="Interest Expense Account (Investors)",
        domain="[('account_type', '=', 'expense')]",
        help="Account for recording interest expenses owed to investors.",
    )
    account_internal_investment_id = fields.Many2one(
        comodel_name="account.account",
        string="Internal Investment Account",
        domain="[('account_type', '=', 'income')]",
        help="Income account for internal investments.",
    )
    account_insurance_receivable_id = fields.Many2one(
        comodel_name="account.account",
        string="Insurance Receivable Account",
        domain="[('account_type', 'in', ['asset_receivable', 'asset_current', 'asset_non_current'])]",
        help="Account debited when a credit life insurance compensation claim is approved.",
    )
    account_insurance_income_id = fields.Many2one(
        comodel_name="account.account",
        string="Insurance Compensation Income Account",
        domain="[('account_type', 'in', ['income', 'income_other'])]",
        help="Account credited when a credit life insurance compensation claim is approved.",
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

    @api.model
    def _name_search(self, name="", domain=None, operator="ilike", limit=None, order=None):
        domain = list(domain or [])
        if name:
            import re
            # Support exact match from import (which includes the [code] prefix)
            match = re.match(r"^\[(.*?)\]", name)
            if match:
                code = match.group(1).strip()
                records = self._search(
                    [("code", "=", code)] + domain,
                    limit=limit,
                    order=order or "id asc",
                )
                if records:
                    return records

            # Fallback to searching code or name
            domain = ["|", ("code", operator, name), ("name", operator, name)] + domain
            return self._search(domain, limit=limit, order=order)
        return super()._name_search(
            name, domain=domain, operator=operator, limit=limit, order=order
        )

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

        if not self.account_penalty_income_id:
            acc = _get_or_create(
                ["income", "income_other"],
                "penalty",
                ["income", "revenue", "interest"],
                "Loan Penalty/Default Income",
                "410400",
                "income_other",
            )
            changes["account_penalty_income_id"] = acc.id

        if not self.account_insurance_receivable_id:
            acc = _get_or_create(
                ["asset_receivable", "asset_current", "asset_non_current", "asset_prepayments"],
                "insurance",
                ["receivable", "claim"],
                "Insurance Claims Receivable",
                "110300",
                "asset_current",
            )
            changes["account_insurance_receivable_id"] = acc.id

        if not self.account_insurance_income_id:
            acc = _get_or_create(
                ["income", "income_other"],
                "insurance",
                ["compensation", "income"],
                "Credit Life Insurance Compensation",
                "410300",
                "income_other",
            )
            changes["account_insurance_income_id"] = acc.id

        if changes:
            self.write(changes)
        return True
