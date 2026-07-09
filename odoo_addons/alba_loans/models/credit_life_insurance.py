# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError


class AlbaCreditLifeInsurance(models.Model):
    """
    Credit Life Insurance Model (Req #7)
    Captures insurance events against a loan, triggered upon customer death.
    Allows manual entry of compensation amount by admin.
    """
    _name = "alba.credit.life.insurance"
    _description = "Credit Life Insurance Event"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"
    _rec_name = "insurance_number"

    # ── Identification ────────────────────────────────────────────────────────
    insurance_number = fields.Char(
        string="Insurance Event Number",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _("New"),
    )

    # ── Loan Link ─────────────────────────────────────────────────────────────
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="restrict",
        index=True,
        help="Loan for which the insurance claim is triggered",
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="loan_id.customer_id",
        store=True,
        readonly=True,
        index=True,
    )
    loan_number = fields.Char(
        string="Loan Number",
        related="loan_id.loan_number",
        store=True,
        readonly=True,
    )
    outstanding_balance = fields.Monetary(
        string="Outstanding Balance at Event",
        currency_field="currency_id",
        readonly=True,
        help="Loan's outstanding balance when insurance event occurred",
    )

    # ── Event Details ─────────────────────────────────────────────────────────
    EVENT_TYPE_CHOICES = [
        ("death", "Customer Death"),
        ("disability", "Total Disability"),
        ("critical_illness", "Critical Illness"),
        ("job_loss", "Job Loss"),
        ("other", "Other"),
    ]

    event_type = fields.Selection(
        selection=EVENT_TYPE_CHOICES,
        string="Event Type",
        required=True,
        default="death",
        help="Type of insurance event triggering the claim",
    )
    event_date = fields.Date(
        string="Event Date",
        required=True,
        help="Date when the insured event occurred",
    )
    event_description = fields.Text(
        string="Event Description",
        help="Additional details about the event",
    )

    # ── Compensation (Manual Entry) ───────────────────────────────────────────
    compensation_amount = fields.Monetary(
        string="Compensation Amount",
        currency_field="currency_id",
        required=True,
        help="Amount approved for compensation (manual entry by admin)",
    )
    compensation_date = fields.Date(
        string="Compensation Date",
        help="Date compensation was approved/processed",
    )

    # ── Status & Workflow ─────────────────────────────────────────────────────
    STATE_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("under_review", "Under Review"),
        ("approved", "Approved"),
        ("compensated", "Compensated"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    state = fields.Selection(
        selection=STATE_CHOICES,
        string="Status",
        default="draft",
        index=True,
    )

    # ── Processing ────────────────────────────────────────────────────────────
    submitted_by = fields.Many2one(
        "res.users",
        string="Submitted By",
        readonly=True,
    )
    submitted_date = fields.Datetime(
        string="Submitted Date",
        readonly=True,
    )
    approved_by = fields.Many2one(
        "res.users",
        string="Approved By",
        readonly=True,
    )
    approved_date = fields.Datetime(
        string="Approved Date",
        readonly=True,
    )
    rejection_reason = fields.Text(
        string="Rejection Reason",
        help="Reason for rejection if applicable",
    )

    # ── Journal Entry (Auto-posted upon approval) ─────────────────────────────
    move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
        readonly=True,
        help="Auto-generated accounting entry for compensation",
    )

    # ── Company & Currency ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    internal_notes = fields.Text(
        string="Internal Notes",
        help="Internal notes visible only to staff",
    )

    # Timestamps - FIX: replaced auto_now/auto_now_add with Odoo-native fields
    # Using default values instead of deprecated auto_now parameters
    created_at = fields.Datetime(string="Created At", readonly=True, default=fields.Datetime.now)
    updated_at = fields.Datetime(string="Updated At", readonly=True)

    def write(self, vals):
        # Update updated_at timestamp on write
        vals['updated_at'] = fields.Datetime.now()
        return super().write(vals)

    class Meta:
        db_table = "alba_credit_life_insurance"

    def __str__(self):
        return self.insurance_number

    @api.model_create_multi
    def create(self, vals_list):
        """Generate insurance number on creation"""
        for vals in vals_list:
            if vals.get("insurance_number", _("New")) == _("New"):
                vals["insurance_number"] = self.env["ir.sequence"].next_by_code(
                    "alba.credit.life.insurance"
                ) or _("New")
            if vals.get("loan_id") and not vals.get("outstanding_balance"):
                loan = self.env["alba.loan"].browse(vals["loan_id"])
                vals["outstanding_balance"] = loan.outstanding_balance
            if vals.get("loan_id") and not vals.get("compensation_amount"):
                loan = self.env["alba.loan"].browse(vals["loan_id"])
                vals["compensation_amount"] = loan.outstanding_balance
        return super().create(vals_list)

    @api.onchange("loan_id")
    def _onchange_loan_id(self):
        for rec in self:
            if rec.loan_id:
                rec.outstanding_balance = rec.loan_id.outstanding_balance
                rec.compensation_amount = rec.loan_id.outstanding_balance
                rec.company_id = rec.loan_id.company_id

    def action_submit(self):
        """Submit the insurance claim"""
        if self.state != "draft":
            raise UserError(_("Only draft claims can be submitted."))
        self.write({
            "state": "submitted",
            "submitted_by": self.env.user.id,
            "submitted_date": fields.Datetime.now(),
        })

    def action_approve(self):
        """Approve the claim and create journal entry"""
        if self.state not in ["submitted", "under_review"]:
            raise UserError(_("Only submitted claims can be approved."))
        
        # Create journal entry for compensation
        if not self.move_id:
            move_vals = self._prepare_journal_entry()
            move = self.env["account.move"].create(move_vals)
            move.action_post()
            self.move_id = move.id

        self.write({
            "state": "approved",
            "approved_by": self.env.user.id,
            "approved_date": fields.Datetime.now(),
        })

    def action_compensate(self):
        """Mark as compensated (after funds transferred)"""
        if self.state != "approved":
            raise UserError(_("Only approved claims can be marked as compensated."))
        self.write({
            "state": "compensated",
            "compensation_date": fields.Date.today(),
        })

    def action_reject(self, reason):
        """Reject the claim"""
        if self.state in ["compensated", "cancelled"]:
            raise UserError(_("Cannot reject a finalized claim."))
        self.write({
            "state": "rejected",
            "rejection_reason": reason,
        })

    def action_cancel(self):
        """Cancel the claim"""
        if self.state == "compensated":
            raise UserError(_("Cannot cancel a compensated claim."))
        self.write({"state": "cancelled"})

    def _prepare_journal_entry(self):
        """Prepare journal entry for insurance compensation"""
        self.ensure_one()
        product = self.loan_id.loan_product_id
        product._ensure_accounting_defaults()
        receivable_account = product.account_insurance_receivable_id
        income_account = product.account_insurance_income_id
        if not receivable_account or not income_account:
            raise UserError(
                _(
                    "Please configure insurance receivable and insurance income accounts "
                    "on loan product '%s'."
                )
                % product.name
            )
        journal = self.env["account.journal"].search(
            [
                ("type", "=", "general"),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        if not journal:
            raise UserError(
                _("No General journal found for company '%s'.") % self.company_id.name
            )

        lines = [
            (
                0,
                0,
                {
                    "account_id": receivable_account.id,
                    "debit": self.compensation_amount,
                    "credit": 0,
                    "name": f"Insurance Compensation - {self.loan_number}",
                    "partner_id": self.customer_id.partner_id.id,
                },
            ),
            (
                0,
                0,
                {
                    "account_id": income_account.id,
                    "debit": 0,
                    "credit": self.compensation_amount,
                    "name": f"Insurance Income - {self.loan_number}",
                    "partner_id": self.customer_id.partner_id.id,
                },
            ),
        ]

        return {
            "journal_id": journal.id,
            "date": fields.Date.today(),
            "line_ids": lines,
            "ref": self.insurance_number,
            "company_id": self.company_id.id,
            "alba_loan_id": self.loan_id.id,
        }

    def action_view_journal_entry(self):
        """Open the compensation journal entry (memo) for this insurance claim."""
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No journal entry has been posted for this insurance claim yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Insurance Entry — %s") % self.insurance_number,
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.move_id.id,
        }
