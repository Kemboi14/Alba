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
        """Approve the claim, post the settlement journal entry, and apply
        the payout to the loan itself. Previously this only booked Insurance
        Receivable/Income and never touched the loan's outstanding balance
        or schedule — the loan kept aging into arrears/write-off candidacy
        as if untouched while the books already showed it "compensated",
        double-counting the settlement.
        """
        self.ensure_one()
        if self.state not in ["submitted", "under_review"]:
            raise UserError(_("Only submitted claims can be approved."))

        loan = self.loan_id
        settlement = min(self.compensation_amount, max(loan.outstanding_balance, 0.0))

        # Create journal entry for compensation
        if not self.move_id:
            move_vals = self._prepare_journal_entry(settlement)
            move = self.env["account.move"].create(move_vals)
            move.action_post()
            self.move_id = move.id

        if settlement > 0.01:
            # Record it as an already-posted, zero-cash repayment so it goes
            # through the exact same allocation/schedule-sync/close pipeline
            # a cash repayment does (see loan_repayment.py's create() override)
            # — the accounting side is already handled by the move above, so
            # no second journal entry is created here.
            self.env["alba.loan.repayment"].create({
                "loan_id": loan.id,
                "payment_date": fields.Date.today(),
                "amount_paid": settlement,
                "payment_method": "insurance",
                "payment_reference": self.insurance_number,
                "state": "posted",
            })

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

    def _prepare_journal_entry(self, settlement=0.0):
        """Prepare the settlement journal entry for insurance compensation.

        DR Insurance Receivable          compensation_amount (owed by insurer)
        CR Loan/Interest/Penalty Receivable   settlement (clears the customer's
            actual debt, waterfalled penalty -> interest -> principal, same
            priority order used everywhere else in the module)
        CR Insurance Income               compensation_amount - settlement
            (only the genuine excess over what was owed is P&L income — the
            portion that pays down real debt is a balance-sheet reclass, not
            income, otherwise the loan's discharge would be double-counted:
            once as "insurance income" and once (never, previously) as debt
            actually cleared).
        """
        self.ensure_one()
        loan = self.loan_id
        product = loan.loan_product_id
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

        partner_id = self.customer_id.partner_id.id
        lines = [
            (
                0,
                0,
                {
                    "account_id": receivable_account.id,
                    "debit": self.compensation_amount,
                    "credit": 0,
                    "name": f"Insurance Compensation - {self.loan_number}",
                    "partner_id": partner_id,
                },
            ),
        ]

        remaining = settlement
        if remaining > 0.01:
            if not product.account_loan_receivable_id or not product.account_interest_receivable_id:
                raise UserError(
                    _(
                        "Please configure Loan Receivable and Interest Receivable accounts "
                        "on loan product '%s' before settling a claim against the loan."
                    )
                    % product.name
                )
            schedule = loan.current_repayment_schedule_ids or loan.repayment_schedule_ids
            penalty_owed = sum(max(l.penalty_due - l.penalty_paid, 0.0) for l in schedule)
            interest_owed = sum(max(l.interest_due - l.interest_paid, 0.0) for l in schedule)
            principal_owed = sum(max(l.principal_due - l.principal_paid, 0.0) for l in schedule)

            pay_penalty = min(remaining, penalty_owed)
            remaining -= pay_penalty
            pay_interest = min(remaining, interest_owed)
            remaining -= pay_interest
            pay_principal = min(remaining, principal_owed)
            remaining -= pay_principal

            if pay_penalty > 0.01:
                penalty_account = product.account_penalty_receivable_id or product.account_interest_receivable_id
                lines.append((0, 0, {
                    "account_id": penalty_account.id,
                    "debit": 0,
                    "credit": round(pay_penalty, 2),
                    "name": f"Insurance Settlement — Penalty — {self.loan_number}",
                    "partner_id": partner_id,
                }))
            if pay_interest > 0.01:
                lines.append((0, 0, {
                    "account_id": product.account_interest_receivable_id.id,
                    "debit": 0,
                    "credit": round(pay_interest, 2),
                    "name": f"Insurance Settlement — Interest — {self.loan_number}",
                    "partner_id": partner_id,
                }))
            if pay_principal > 0.01:
                lines.append((0, 0, {
                    "account_id": product.account_loan_receivable_id.id,
                    "debit": 0,
                    "credit": round(pay_principal, 2),
                    "name": f"Insurance Settlement — Principal — {self.loan_number}",
                    "partner_id": partner_id,
                }))

        excess = self.compensation_amount - settlement
        if excess > 0.01:
            lines.append((0, 0, {
                "account_id": income_account.id,
                "debit": 0,
                "credit": round(excess, 2),
                "name": f"Insurance Income - {self.loan_number}",
                "partner_id": partner_id,
            }))

        return {
            "journal_id": journal.id,
            "date": fields.Date.today(),
            "line_ids": lines,
            "ref": self.insurance_number,
            "company_id": self.company_id.id,
            "alba_loan_id": loan.id,
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
