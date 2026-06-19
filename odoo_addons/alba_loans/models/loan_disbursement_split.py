# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError


class AlbaLoanDisbursementSplit(models.Model):
    """
    Loan Disbursement Split (Req #2)
    Allows a single loan to be split across multiple Alba accounts.
    Example: KES 100,000 split as 50,000 from Account A + 50,000 from Account B
    """
    _name = "alba.loan.disbursement.split"
    _description = "Loan Disbursement Account Split"
    _order = "loan_id, sequence"

    # ── Loan Link ─────────────────────────────────────────────────────────────
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Order of disbursement splits",
    )

    # ── Source Journal ────────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        "account.journal",
        string="Source Journal",
        required=True,
        ondelete="restrict",
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Alba Capital account from which funds are disbursed",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        domain="[('payment_type', '=', 'outbound'), ('journal_id', '=', journal_id)]",
        help="Specific outbound payment method for this funding source.",
    )
    move_id = fields.Many2one(
        "account.move",
        string="Disbursement Move",
        readonly=True,
        copy=False,
    )
    account_name = fields.Char(
        string="Account Name",
        compute="_compute_account_name",
        store=True,
        readonly=True,
    )
    
    @api.depends("journal_id.name")
    def _compute_account_name(self):
        """Compute account name from journal"""
        for record in self:
            record.account_name = record.journal_id.name or ""
    account_number = fields.Char(
        string="Account Number",
        compute="_compute_account_number",
        store=True,
    )

    # ── Disbursement Amount ───────────────────────────────────────────────────
    amount = fields.Monetary(
        string="Disbursement Amount",
        currency_field="currency_id",
        required=True,
        help="Amount to disburse from this account",
    )
    percentage = fields.Float(
        string="Percentage (%)",
        compute="_compute_percentage",
        store=True,
        readonly=True,
        help="Percentage of total loan amount",
    )

    # ── Status ────────────────────────────────────────────────────────────────
    STATE_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("disbursed", "Disbursed"),
        ("failed", "Failed"),
    ]

    state = fields.Selection(
        selection=STATE_CHOICES,
        string="Status",
        default="pending",
        index=True,
    )
    disbursement_date = fields.Date(
        string="Disbursement Date",
        help="Date when funds were actually disbursed",
    )
    reference_number = fields.Char(
        string="Disbursement Reference",
        help="Reference from the disbursing bank/system",
    )

    # ── Company & Currency ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="loan_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    # ── Computed Fields ───────────────────────────────────────────────────────
    principal_amount = fields.Monetary(
        string="Principal Amount",
        related="loan_id.principal_amount",
        store=True,
        readonly=True,
    )

    @api.depends("amount", "loan_id.principal_amount")
    def _compute_percentage(self):
        for rec in self:
            if rec.loan_id.principal_amount > 0:
                rec.percentage = (rec.amount / rec.loan_id.principal_amount) * 100
            else:
                rec.percentage = 0

    @api.depends("journal_id", "journal_id.bank_account_id")
    def _compute_account_number(self):
        for rec in self:
            bank_account = rec.journal_id.bank_account_id
            rec.account_number = bank_account.acc_number if bank_account else ""

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        for rec in self:
            if rec.payment_method_line_id and rec.payment_method_line_id.journal_id != rec.journal_id:
                rec.payment_method_line_id = False

    def _ensure_payment_method_line(self):
        for rec in self:
            if not rec.journal_id:
                continue
            if rec.payment_method_line_id:
                if rec.payment_method_line_id.journal_id != rec.journal_id:
                    raise UserError(_(
                        "Payment Method '%(method)s' does not belong to Source Journal '%(journal)s'.",
                        method=rec.payment_method_line_id.display_name,
                        journal=rec.journal_id.display_name,
                    ))
                if rec.payment_method_line_id.payment_type != "outbound":
                    raise UserError(_("Please select an outbound payment method for source journal '%s'.") % rec.journal_id.display_name)
                continue

            method_line = self.env["account.payment.method.line"].search([
                ("payment_type", "=", "outbound"),
                ("journal_id", "=", rec.journal_id.id),
            ], limit=1)
            if not method_line:
                raise UserError(_("Please configure an outbound Payment Method on source journal '%s'.") % rec.journal_id.display_name)
            rec.payment_method_line_id = method_line

    class Meta:
        db_table = "alba_loan_disbursement_split"

    def __str__(self):
        return f"{self.loan_id.loan_number} - {self.account_name}: {self.amount}"

    @api.constrains("amount")
    def _check_amount_positive(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(
                    _("Disbursement amount must be greater than zero!")
                )

    @api.constrains("amount")
    def _check_total_not_exceeded(self):
        """Ensure total disbursement splits don't exceed principal"""
        for rec in self:
            total_splits = sum(
                split.amount
                for split in rec.loan_id.disbursement_split_ids
                if split != rec
            ) + rec.amount
            if total_splits > rec.loan_id.principal_amount:
                raise ValidationError(
                    _(
                        f"Total disbursement splits ({total_splits}) exceed "
                        f"loan principal ({rec.loan_id.principal_amount})!"
                    )
                )

    def action_approve(self):
        """Approve this disbursement split"""
        if self.state != "pending":
            raise UserError(_("Only pending splits can be approved."))
        self.state = "approved"

    def action_disburse(self):
        """Mark this split as disbursed"""
        if self.state != "approved":
            raise UserError(_("Only approved splits can be disbursed."))
        if self.journal_id.type not in ("bank", "cash"):
            raise UserError(
                _(
                    "Disbursement journal '%s' must be a Bank or Cash journal."
                ) % self.journal_id.display_name
            )
        self._ensure_payment_method_line()

        outstanding_account = (
            self.payment_method_line_id.payment_account_id
            or self.journal_id.default_account_id
        )
        if not outstanding_account:
            raise UserError(
                _(
                    'Journal "%s" has no bank/cash account configured for disbursement. '
                    'Please set the journal default account or the outbound payment method account '
                    'before posting disbursements.'
                ) % self.journal_id.name
            )

        if not self.loan_id.loan_product_id.account_loan_receivable_id:
            raise UserError(
                _(
                    "Loan product '%s' has no Loan Receivable account configured."
                ) % self.loan_id.loan_product_id.name
            )

        move_vals = {
            "journal_id": self.journal_id.id,
            "date": fields.Date.today(),
            "ref": _("Disbursement Split: %s") % self.display_name,
            "preferred_payment_method_line_id": self.payment_method_line_id.id if self.payment_method_line_id else False,
            "line_ids": [
                (0, 0, {
                    "account_id": self.loan_id.loan_product_id.account_loan_receivable_id.id,
                    "partner_id": self.loan_id.customer_id.partner_id.id,
                    "name": _("Disbursement split — %s") % self.display_name,
                    "debit": self.amount,
                }),
                (0, 0, {
                    "account_id": outstanding_account.id,  # FIX: use Outstanding Payments transit account
                    "partner_id": self.loan_id.customer_id.partner_id.id,
                    "name": _("Disbursement split — %s") % self.display_name,
                    "credit": self.amount,
                }),
            ],
        }
        move = self.env["account.move"].create(move_vals)
        move.action_post()
        move.write({
            "ref": move.ref,
            "is_move_sent": False,
        })
        self.write({
            "state": "disbursed",
            "disbursement_date": fields.Date.today(),
            "move_id": move.id,
        })

    def action_mark_failed(self):
        """Mark this split as failed"""
        self.state = "failed"
