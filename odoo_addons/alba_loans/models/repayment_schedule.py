# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlbaRepaymentSchedule(models.Model):
    _name = "alba.repayment.schedule"
    _description = "Alba Capital Loan Repayment Schedule"
    _order = "loan_id, installment_number asc"
    _rec_name = "display_name"

    # ── Identification ────────────────────────────────────────────────────────
    display_name = fields.Char(
        string="Label",
        compute="_compute_display_name",
        store=True,
    )

    # ── Loan Link ─────────────────────────────────────────────────────────────
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="cascade",
        index=True,
    )
    batch_id = fields.Many2one(
        "alba.repayment.schedule.batch",
        string="Schedule Batch",
        ondelete="cascade",
        index=True,
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="loan_id.customer_id",
        store=True,
        readonly=True,
        index=True,
    )

    # ── Instalment Details ────────────────────────────────────────────────────
    installment_number = fields.Integer(
        string="Instalment #",
        required=True,
    )
    due_date = fields.Date(
        string="Due Date",
        required=True,
        index=True,
    )

    # ── Amounts ───────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="loan_id.currency_id",
        store=True,
        readonly=True,
    )
    opening_balance = fields.Monetary(
        string="Opening Balance",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    principal_due = fields.Monetary(
        string="Principal Due",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    interest_due = fields.Monetary(
        string="Interest Due",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    total_due = fields.Monetary(
        string="Total Due",
        currency_field="currency_id",
        compute="_compute_total_due",
        inverse="_inverse_total_due",
        store=True,
        # IMPORT-EXPORT FIX
    )
    closing_balance = fields.Monetary(
        string="Closing Balance",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )

    # ── Paid Amounts ──────────────────────────────────────────────────────────
    principal_paid = fields.Monetary(
        string="Principal Paid",
        currency_field="currency_id",
        default=0.0,
    )
    interest_paid = fields.Monetary(
        string="Interest Paid",
        currency_field="currency_id",
        default=0.0,
    )
    penalty_due = fields.Monetary(
        string="Penalty Due",
        currency_field="currency_id",
        default=0.0,
        help="Accrued penalty/late fee amount for this instalment.",
    )
    penalty_paid = fields.Monetary(
        string="Penalty Paid",
        currency_field="currency_id",
        default=0.0,
        help="Penalty amount paid for this instalment.",
    )
    total_paid = fields.Monetary(
        string="Total Paid",
        currency_field="currency_id",
        compute="_compute_total_paid",
        inverse="_inverse_total_paid",
        store=True,
        # IMPORT-EXPORT FIX
    )

    # ── Balances ──────────────────────────────────────────────────────────────
    balance_due = fields.Monetary(
        string="Balance Due",
        currency_field="currency_id",
        compute="_compute_balance_due",
        inverse="_inverse_balance_due",
        store=True,
        help="Remaining amount to be paid for this instalment.",
        # IMPORT-EXPORT FIX
    )
    days_overdue = fields.Integer(
        string="Days Overdue",
        compute="_compute_days_overdue",
        inverse="_inverse_days_overdue",
        store=True,
        # IMPORT-EXPORT FIX
    )
    paid_late = fields.Boolean(
        string="Paid Late",
        compute="_compute_paid_late",
        store=True,
        help="True if this instalment was paid after its due date, but is now fully paid.",
    )

    # ── Status ────────────────────────────────────────────────────────────────
    status = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("partial", "Partially Paid"),
            ("paid", "Paid"),
            ("overdue", "Overdue"),
        ],
        string="Status",
        default="pending",
        compute="_compute_status",
        inverse="_inverse_status",
        store=True,
        index=True,
        # IMPORT-EXPORT FIX
    )

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _installment_loan_unique = models.Constraint(
        "UNIQUE(loan_id, installment_number)",
        "Instalment number must be unique per loan.",
    )
    _principal_non_negative = models.Constraint(
        "CHECK(principal_due >= 0)",
        "Principal due cannot be negative.",
    )
    _interest_non_negative = models.Constraint(
        "CHECK(interest_due >= 0)",
        "Interest due cannot be negative.",
    )
    _principal_paid_non_negative = models.Constraint(
        "CHECK(principal_paid >= 0)",
        "Principal paid cannot be negative.",
    )
    _interest_paid_non_negative = models.Constraint(
        "CHECK(interest_paid >= 0)",
        "Interest paid cannot be negative.",
    )
    _penalty_non_negative = models.Constraint(
        "CHECK(penalty_due >= 0)",
        "Penalty due cannot be negative.",
    )
    _penalty_paid_non_negative = models.Constraint(
        "CHECK(penalty_paid >= 0)",
        "Penalty paid cannot be negative.",
    )

    # =========================================================================
    # Computed Methods
    # =========================================================================

    @api.depends("loan_id", "installment_number")
    def _compute_display_name(self):
        for rec in self:
            loan_ref = rec.loan_id.loan_number or "?"
            rec.display_name = _("Instalment %d — %s") % (
                rec.installment_number,
                loan_ref,
            )

    @api.depends("principal_due", "interest_due", "penalty_due")
    def _compute_total_due(self):
        for rec in self:
            rec.total_due = rec.principal_due + rec.interest_due + rec.penalty_due

    @api.depends("principal_paid", "interest_paid", "penalty_paid")
    def _compute_total_paid(self):
        for rec in self:
            rec.total_paid = rec.principal_paid + rec.interest_paid + rec.penalty_paid

    @api.depends("total_due", "total_paid")
    def _compute_balance_due(self):
        for rec in self:
            rec.balance_due = max(rec.total_due - rec.total_paid, 0.0)

    @api.depends("due_date", "balance_due")
    def _compute_days_overdue(self):
        today = fields.Date.today()
        for rec in self:
            if rec.balance_due > 0.0 and rec.due_date and rec.due_date < today:
                rec.days_overdue = (today - rec.due_date).days
            else:
                rec.days_overdue = 0

    @api.depends("balance_due", "total_paid", "due_date")
    def _compute_paid_late(self):
        """
        Determine if an instalment was paid late (after due date) but is now fully paid.
        This preserves historical timing information while allowing correct current status.
        """
        today = fields.Date.today()
        for rec in self:
            # Only mark as paid late if:
            # 1. Balance is fully paid (balance_due <= 0)
            # 2. Some payment was made (total_paid > 0)
            # 3. Due date was in the past (due_date < today)
            # 4. Due date exists
            rec.paid_late = (
                rec.balance_due <= 0.0
                and rec.total_paid > 0.0
                and rec.due_date
                and rec.due_date < today
            )

    @api.depends("balance_due", "total_paid", "total_due", "due_date")
    def _compute_status(self):
        """
        FIXED: Prioritize balance over timing to avoid showing "overdue" for fully paid late payments.
        
        Status logic:
        - If balance is fully paid: status = "paid" (regardless of payment timing)
        - If partial payment made: status = "partial" or "overdue" based on timing
        - If no payment but due date passed: status = "overdue"
        - If no payment and due date future: status = "pending"
        """
        today = fields.Date.today()
        for rec in self:
            # Priority 1: Fully paid - always "paid" regardless of timing
            if rec.balance_due <= 0.0:
                rec.status = "paid"
            # Priority 2: Partial payment - check timing
            elif rec.total_paid > 0.0:
                if rec.due_date and rec.due_date < today:
                    rec.status = "overdue"  # Partial payment, currently overdue
                else:
                    rec.status = "partial"  # Partial payment, not yet overdue
            # Priority 3: No payment, check timing
            elif rec.due_date and rec.due_date < today:
                rec.status = "overdue"  # No payment, currently overdue
            else:
                rec.status = "pending"  # No payment, not yet due

    # IMPORT-EXPORT FIX: no-op inverses — import can write these; compute resets on trigger
    def _inverse_total_due(self): pass
    def _inverse_total_paid(self): pass
    def _inverse_balance_due(self): pass
    def _inverse_days_overdue(self): pass
    def _inverse_status(self): pass
    def _inverse_paid_late(self): pass

    # =========================================================================
    # Constraint Methods
    # =========================================================================

    @api.constrains("principal_paid", "principal_due")
    def _check_principal_paid(self):
        for rec in self:
            if rec.principal_paid > rec.principal_due + 0.01:
                raise ValidationError(
                    _(
                        "Principal paid (%s) cannot exceed principal due (%s) "
                        "for instalment %d."
                    )
                    % (rec.principal_paid, rec.principal_due, rec.installment_number)
                )

    @api.constrains("interest_paid", "interest_due")
    def _check_interest_paid(self):
        for rec in self:
            if rec.interest_paid > rec.interest_due + 0.01:
                raise ValidationError(
                    _(
                        "Interest paid (%s) cannot exceed interest due (%s) "
                        "for instalment %d."
                    )
                    % (rec.interest_paid, rec.interest_due, rec.installment_number)
                )

    @api.constrains("penalty_paid", "penalty_due")
    def _check_penalty_paid(self):
        for rec in self:
            if rec.penalty_paid > rec.penalty_due + 0.01:
                raise ValidationError(
                    _(
                        "Penalty paid (%s) cannot exceed penalty due (%s) "
                        "for instalment %d."
                    )
                    % (rec.penalty_paid, rec.penalty_due, rec.installment_number)
                )

    # =========================================================================
    # Business Logic
    # =========================================================================

    def apply_payment(self, amount_received):
        """
        Allocate a payment amount to this instalment.
        Returns the unapplied remainder (if any).

        Allocation order: penalty first, then interest, then principal.
        """
        self.ensure_one()
        remainder = amount_received

        # Allocate penalty first
        penalty_outstanding = self.penalty_due - self.penalty_paid
        if penalty_outstanding > 0.0:
            penalty_apply = min(remainder, penalty_outstanding)
            self.penalty_paid += penalty_apply
            remainder -= penalty_apply

        # Allocate interest second
        interest_outstanding = self.interest_due - self.interest_paid
        if interest_outstanding > 0.0 and remainder > 0.0:
            interest_apply = min(remainder, interest_outstanding)
            self.interest_paid += interest_apply
            remainder -= interest_apply

        # Then principal
        principal_outstanding = self.principal_due - self.principal_paid
        if principal_outstanding > 0.0 and remainder > 0.0:
            principal_apply = min(remainder, principal_outstanding)
            self.principal_paid += principal_apply
            remainder -= principal_apply

        return round(remainder, 2)

    def action_reset(self):
        """Reset paid amounts (e.g. after a payment reversal)."""
        self.ensure_one()
        self.write({"principal_paid": 0.0, "interest_paid": 0.0, "penalty_paid": 0.0})
