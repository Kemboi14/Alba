# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class ResPartner(models.Model):
    _inherit = "res.partner"

    # ── Identity ──────────────────────────────────────────────────────────────
    id_number = fields.Char(string="ID / Passport Number", index=True)
    alba_customer_number = fields.Char(
        string="Alba Capital Customer Number",
        copy=False,
        index=True,
        readonly=True,
        help=(
            "Unique bank-style Alba Capital customer identifier, shared across "
            "all products (loans, investments, ...) held by this person. "
            "Assigned once, the first time this partner becomes an Alba "
            "customer or investor."
        ),
    )
    id_type = fields.Selection(
        selection=[
            ("national_id", "National ID"),
            ("passport", "Passport"),
            ("alien_id", "Alien ID / Foreign Certificate"),
        ],
        string="ID Type",
        default="national_id",
    )
    date_of_birth = fields.Date(string="Date of Birth")
    gender = fields.Selection(
        selection=[
            ("male", "Male"),
            ("female", "Female"),
            ("other", "Other / Prefer not to say"),
        ],
        string="Gender",
    )
    kra_pin = fields.Char(string="KRA PIN")
    registration_number = fields.Char(string="Company Registration")

    # ── Employment (Centralized) ──────────────────────────────────────────────
    employer_id = fields.Many2one(
        "alba.employer",
        string="Employer",
    )
    job_title = fields.Char(string="Job Title")
    monthly_income = fields.Monetary(
        string="Monthly Net Income",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )

    # ── Alba Links ────────────────────────────────────────────────────────────
    # NOTE: intentionally NOT stored. This compute searches related models
    # (alba.customer/alba.guarantor/alba.investor) rather than reading a
    # direct relational field on res.partner, so there is no field-level
    # @api.depends path that would let a *stored* version of these booleans
    # get invalidated when a customer/guarantor/investor is linked to this
    # partner after the partner record already exists. Keeping them
    # non-stored means they are recomputed fresh on every read instead of
    # silently going stale. The no-op inverses are kept so the import tool
    # can still map values onto these fields without erroring.
    is_alba_customer = fields.Boolean(string="Is Alba Customer", compute="_compute_alba_links", inverse="_inverse_alba_links")
    is_alba_guarantor = fields.Boolean(string="Is Alba Guarantor", compute="_compute_alba_links", inverse="_inverse_alba_links")
    is_alba_investor = fields.Boolean(string="Is Alba Investor", compute="_compute_alba_links", inverse="_inverse_alba_links")

    def _compute_alba_links(self):
        for rec in self:
            # Initialize defaults
            rec.is_alba_customer = False
            rec.is_alba_guarantor = False
            rec.is_alba_investor = False
            
            # Check if models are fully loaded in registry before searching
            # This handles cross-module dependencies during updates
            registry = self.env.registry
            
            if 'alba.customer' in registry.models and 'partner_id' in registry.models['alba.customer']._fields:
                rec.is_alba_customer = bool(self.env['alba.customer'].search([('partner_id', '=', rec.id)], limit=1))
            
            if 'alba.guarantor' in registry.models and 'partner_id' in registry.models['alba.guarantor']._fields:
                rec.is_alba_guarantor = bool(self.env['alba.guarantor'].search([('partner_id', '=', rec.id)], limit=1))
            
            if 'alba.investor' in registry.models and 'partner_id' in registry.models['alba.investor']._fields:
                rec.is_alba_investor = bool(self.env['alba.investor'].search([('partner_id', '=', rec.id)], limit=1))

    def _inverse_alba_links(self):
        # IMPORT-EXPORT FIX: no-op inverse — these flags are derived from linked records;
        # importing a True/False value does not create/remove the linked record.
        pass

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _alba_customer_number_unique = models.Constraint(
        "UNIQUE(alba_customer_number)",
        "This Alba Capital Customer Number is already assigned to another partner.",
    )

    # ── Alba Capital Customer Number ──────────────────────────────────────────
    @staticmethod
    def _luhn_check_digit(body):
        """
        Compute the Luhn (mod-10) check digit for a numeric string, the same
        checksum algorithm used to validate bank card/account numbers. This
        lets staff catch a transcription error when the customer number is
        typed into a physical file label or re-keyed manually.
        """
        digits = [int(ch) for ch in body]
        # Double every second digit counting from the rightmost digit of `body`.
        for i in range(len(digits) - 1, -1, -2):
            doubled = digits[i] * 2
            digits[i] = doubled - 9 if doubled > 9 else doubled
        total = sum(digits)
        return str((10 - (total % 10)) % 10)

    def _assign_alba_customer_number(self, origin_code):
        """
        Assign this partner's Alba Capital Customer Number if it doesn't have
        one yet. Safe to call from both `alba.customer` and `alba.investor`
        `create()` — whichever model reaches a shared partner first wins;
        the other reuses the existing number instead of minting a second one.

        Format (11 digits, no punctuation):
            [2-digit branch code][1-digit origin code][7-digit sequence][1 Luhn check digit]

        `origin_code` is "1" for a loan customer, "2" for an investor — it
        just records which product line first created this identity and
        never changes afterwards.
        """
        self.ensure_one()
        if self.alba_customer_number:
            return self.alba_customer_number

        branch_code = (
            self.env["ir.config_parameter"].sudo().get_param("alba_loans.branch_code", "01")
        )
        branch_code = str(branch_code).zfill(2)[:2]
        sequence = self.env["ir.sequence"].next_by_code("alba.customer.number.seq")
        if not sequence:
            raise ValueError(
                "Sequence 'alba.customer.number.seq' is not configured — "
                "cannot assign an Alba Capital Customer Number."
            )
        body = "%s%s%s" % (branch_code, origin_code, sequence.zfill(7))
        check_digit = self._luhn_check_digit(body)
        number = body + check_digit
        self.alba_customer_number = number
        return number
