# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from markupsafe import Markup


class AlbaLoanRepayment(models.Model):
    _name = "alba.loan.repayment"
    _description = "Alba Capital Loan Repayment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "payment_reference"
    _order = "payment_date desc, id desc"

    # ── Identification ────────────────────────────────────────────────────────
    payment_reference = fields.Char(
        string="Payment Reference",
        copy=False,
        index=True,
        help="Unique reference for this payment (e.g. M-Pesa code, bank ref).",
    )
    django_payment_id = fields.Integer(
        string="Django Payment ID",
        index=True,
        copy=False,
        help="Primary key of the corresponding repayment record in the Django portal.",
    )

    # ── Loan Link ─────────────────────────────────────────────────────────────
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="restrict",
        index=True,
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="loan_id.customer_id",
        store=True,
        readonly=False,
        index=True,
        inverse="_inverse_noop",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="loan_id.customer_id.partner_id",
        store=True,
        readonly=False,
        inverse="_inverse_noop",
    )
    loan_product_id = fields.Many2one(
        "alba.loan.product",
        string="Loan Product",
        related="loan_id.loan_product_id",
        store=True,
        readonly=False,
        inverse="_inverse_noop",
    )

    # ── Payment Details ───────────────────────────────────────────────────────
    payment_date = fields.Date(
        string="Payment Date",
        required=True,
        default=fields.Date.today,
    )
    amount_paid = fields.Monetary(
        string="Amount Paid",
        currency_field="currency_id",
        required=True,
    )

    # ── Allocation ────────────────────────────────────────────────────────────
    principal_component = fields.Monetary(
        string="Principal Component",
        currency_field="currency_id",
        default=0.0,
    )
    interest_component = fields.Monetary(
        string="Interest Component",
        currency_field="currency_id",
        default=0.0,
    )
    fees_component = fields.Monetary(
        string="Fees Component",
        currency_field="currency_id",
        default=0.0,
    )
    penalty_component = fields.Monetary(
        string="Penalty/Late Fee Component",
        currency_field="currency_id",
        default=0.0,
    )
    total_allocated = fields.Monetary(
        string="Total Allocated",
        currency_field="currency_id",
        compute="_compute_total_allocated",
        store=True,
        inverse="_inverse_noop",
    )
    unallocated_amount = fields.Monetary(
        string="Unallocated Amount",
        currency_field="currency_id",
        compute="_compute_total_allocated",
        store=True,
        help="Difference between amount paid and total allocation across components.",
        inverse="_inverse_noop",
    )

    def _inverse_noop(self):
        """No-op inverse for import-export compatibility of computed fields."""
        pass

    # ── Payment Method ────────────────────────────────────────────────────────
    payment_method = fields.Selection(
        selection=[
            ("mpesa", "M-Pesa"),
            ("bank_transfer", "Bank Transfer"),
            ("cash", "Cash"),
            ("cheque", "Cheque"),
            ("rtgs", "RTGS / EFT"),
        ],
        string="Payment Method",
        required=True,
        default="mpesa",
    )
    mpesa_transaction_id = fields.Char(
        string="M-Pesa Transaction ID",
        copy=False,
        index=True,
    )
    bank_transaction_id = fields.Char(
        string="Bank Transaction ID / Cheque No.",
        copy=False,
    )
    received_by = fields.Many2one(
        "res.users",
        string="Received By",
        default=lambda self: self.env.uid,
    )

    # ── Workflow State ────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("reversed", "Reversed"),
        ],
        string="Status",
        default="draft",
        required=True,
        copy=False,
        index=True,
    )

    def _log_professional_status_change(self, old_state, new_state):
        """Post a professional, formatted message to the chatter on status change."""
        state_labels = dict(self._fields['state'].selection)
        old_label = state_labels.get(old_state, old_state)
        new_label = state_labels.get(new_state, new_state)
        
        icon = "💸" if new_state == "posted" else "ℹ️"
        if new_state == "reversed": icon = "🔄"
        
        body = (
            "<div class='o_alba_status_change'>"
            "<strong>%s Repayment Status Changed</strong><br/>"
            "From: <span class='badge badge-secondary' style='color: #666;'>%s</span> "
            "To: <span class='badge badge-primary' style='background-color: #004a99; color: white; padding: 2px 6px; border-radius: 4px;'>%s</span><br/>"
            "Changed by: %s"
            "</div>"
        ) % (icon, old_label.upper(), new_label.upper(), self.env.user.name)
        
        self.message_post(body=body, subtype_xmlid="mail.mt_comment")

    def action_view_journal_entry(self):
        """Open the journal entry (memo) posted for this repayment."""
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No journal entry has been posted for this repayment yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Entry — %s") % self.payment_reference,
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.move_id.id,
        }


    def _fire_repayment_webhook(self, event_type):
        """Fire a webhook to Django when a repayment is posted or reversed."""
        api_key = self.env["alba.api.key"].sudo().search([("is_active", "=", True)], limit=1)
        if not api_key:
            return
        
        payload = {
            "odoo_payment_id": self.id,
            "payment_reference": self.payment_reference,
            "django_payment_id": self.django_payment_id or 0,
            "odoo_loan_id": self.loan_id.id,
            "django_loan_id": self.loan_id.django_loan_id or 0,
            "amount_paid": float(self.amount_paid),
            "state": self.state,
            "payment_date": str(self.payment_date),
            "outstanding_balance": float(self.loan_id.outstanding_balance),
        }
        api_key.send_webhook_with_retry(event_type, payload)

    def write(self, vals):
        if 'state' in vals:
            for rec in self:
                if rec.state != vals['state']:
                    rec._log_professional_status_change(rec.state, vals['state'])
                    if vals['state'] == 'posted':
                        rec._fire_repayment_webhook("loan.repayment_posted")
                    elif vals['state'] == 'reversed':
                        rec._fire_repayment_webhook("loan.repayment_reversed")
        return super().write(vals)

    # ── Accounting ────────────────────────────────────────────────────────────
    move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
        readonly=True,
        copy=False,
    )
    reversal_move_id = fields.Many2one(
        "account.move",
        string="Reversal Journal Entry",
        readonly=True,
        copy=False,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Bank or Cash journal into which this payment was received.",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Journal Payment Method",
        domain="[('payment_type', '=', 'inbound'), ('journal_id', '=', journal_id)]",
        help="Specific payment method (e.g. Manual, M-Pesa) for this journal.",
    )

    # ── Currency / Company ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="loan_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string="Notes / Remarks")
    reversal_reason = fields.Text(string="Reversal Reason")

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _amount_positive = models.Constraint(
        "CHECK(amount_paid > 0)",
        "Payment amount must be greater than zero.",
    )
    _unique_mpesa_transaction = models.Constraint(
        "UNIQUE(mpesa_transaction_id)",
        "A repayment with this M-Pesa transaction ID already exists.",
    )
    _unique_django_payment_id = models.Constraint(
        "UNIQUE(django_payment_id)",
        "A repayment with this Django Payment ID already exists.",
    )
    _mpesa_transaction_id_not_empty = models.Constraint(
        "CHECK(mpesa_transaction_id IS NULL OR mpesa_transaction_id != '')",
        "M-Pesa transaction ID cannot be empty string.",
    )
    # No equivalent "not empty string" constraint for django_payment_id:
    # it is an Integer column, so an empty-string comparison is meaningless
    # (and invalid SQL for that column type) — NULL is the only "not set" value.

    # =========================================================================
    # Computed Methods
    # =========================================================================

    @api.depends(
        "principal_component",
        "interest_component",
        "fees_component",
        "penalty_component",
        "amount_paid",
    )
    def _compute_total_allocated(self):
        for rec in self:
            allocated = (
                rec.principal_component
                + rec.interest_component
                + rec.fees_component
                + rec.penalty_component
            )
            rec.total_allocated = allocated
            rec.unallocated_amount = max(rec.amount_paid - allocated, 0.0)

    # =========================================================================
    # Constraint Methods
    # =========================================================================

    @api.constrains(
        "principal_component",
        "interest_component",
        "fees_component",
        "penalty_component",
    )
    def _check_components_non_negative(self):
        for rec in self:
            if any(
                val < 0
                for val in [
                    rec.principal_component,
                    rec.interest_component,
                    rec.fees_component,
                    rec.penalty_component,
                ]
            ):
                raise ValidationError(
                    _("Repayment component amounts cannot be negative.")
                )

    @api.constrains("amount_paid", "journal_id")
    def _check_large_payment_policy(self):
        """Repayments above 500,000 must be done via Bank journal."""
        THRESHOLD = 500000.0
        for rec in self:
            if rec.amount_paid > THRESHOLD:
                if rec.journal_id and rec.journal_id.type != "bank":
                    raise ValidationError(_(
                        "Compliance Alert: Repayments exceeding %(threshold)s must be processed through a Bank journal. "
                        "The selected journal '%(journal)s' is not a Bank journal.",
                        threshold=f"{THRESHOLD:,.2f}",
                        journal=rec.journal_id.name,
                    ))

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        for rec in self:
            if rec.payment_method_line_id and rec.payment_method_line_id.journal_id != rec.journal_id:
                rec.payment_method_line_id = False

    def _ensure_payment_method_line(self):
        """Ensure inbound repayments always carry a method line for the journal."""
        for rec in self:
            if not rec.journal_id:
                continue
            if rec.payment_method_line_id:
                if rec.payment_method_line_id.journal_id != rec.journal_id:
                    raise UserError(_(
                        "Payment Method '%(method)s' does not belong to Payment Journal '%(journal)s'.",
                        method=rec.payment_method_line_id.display_name,
                        journal=rec.journal_id.display_name,
                    ))
                if rec.payment_method_line_id.payment_type != "inbound":
                    raise UserError(_(
                        "Please select an inbound payment method for journal '%s'."
                    ) % rec.journal_id.display_name)
                continue

            method_line = self.env["account.payment.method.line"].search([
                ("payment_type", "=", "inbound"),
                ("journal_id", "=", rec.journal_id.id),
            ], limit=1)
            if not method_line:
                raise UserError(_(
                    "Please configure an inbound Payment Method on journal '%s' before posting this repayment."
                ) % rec.journal_id.display_name)
            rec.payment_method_line_id = method_line

    @api.constrains(
        "amount_paid",
        "principal_component",
        "interest_component",
        "fees_component",
        "penalty_component",
    )
    def _check_allocation_not_exceed_payment(self):
        for rec in self:
            allocated = (
                rec.principal_component
                + rec.interest_component
                + rec.fees_component
                + rec.penalty_component
            )
            if allocated > rec.amount_paid + 0.01:
                raise ValidationError(
                    _(
                        "Total allocated (%(allocated).2f) cannot exceed the amount paid (%(paid).2f).",
                        allocated=allocated,
                        paid=rec.amount_paid,
                    )
                )

    @api.constrains("mpesa_transaction_id")
    def _check_mpesa_transaction_unique(self):
        for rec in self:
            if not rec.mpesa_transaction_id:
                continue
            duplicate = self.search(
                [
                    ("mpesa_transaction_id", "=", rec.mpesa_transaction_id),
                    ("id", "!=", rec.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "M-Pesa transaction ID '%s' is already recorded on repayment %s.",
                        rec.mpesa_transaction_id,
                        duplicate.payment_reference,
                    )
                )

    # =========================================================================
    # Business Logic
    # =========================================================================

    def _get_schedule_lines(self):
        """
        Safely retrieve the active repayment schedule lines for this loan.

        SAFE PATTERN: Always query by loan_id only (indexed, guaranteed to
        return rows). Then filter to the active batch IN PYTHON MEMORY so we
        are never at the mercy of a stale stored-computed `balance_due` field
        in the database.

        Fallback chain:
          1. Lines belonging to the latest active batch   (preferred)
          2. All lines for the loan                       (fallback when batch
             returns zero lines or no batch exists)
        """
        self.ensure_one()
        # Fetch ALL lines for this loan — single indexed query, always correct
        all_lines = self.env["alba.repayment.schedule"].search(
            [("loan_id", "=", self.loan_id.id)],
            order="due_date asc",
        )
        if not all_lines:
            return all_lines

        # Try to narrow to the latest active batch
        Batch = self.env["alba.repayment.schedule.batch"]
        batch = Batch.search(
            [("loan_id", "=", self.loan_id.id), ("state", "=", "active")],
            limit=1,
            order="generated_on desc",
        )
        if batch:
            batch_lines = all_lines.filtered(lambda l: l.batch_id == batch)
            # Only use batch lines if they actually exist; otherwise fall back
            if batch_lines:
                all_lines = batch_lines

        # Filter for unpaid lines in Python memory — never rely on stored
        # `balance_due` which may be stale across transaction boundaries
        unpaid = all_lines.filtered(
            lambda l: (l.principal_due - l.principal_paid) > 0.001
            or (l.interest_due - l.interest_paid) > 0.001
        )
        return unpaid

    def _auto_allocate_components(self):
        """
        Auto-allocate payment amount to components in priority order:
        1. Penalties (Daily Compounding on arrears)
        2. Fees / Other Charges
        3. Interest
        4. Principal
        Uses the linked repayment schedule to drive allocation.
        """
        self.ensure_one()
        remaining = self.amount_paid
        fees = 0.0
        penalty = 0.0
        interest = 0.0
        principal = 0.0

        # SAFE: use in-memory filtering — never depends on stale stored balance_due
        schedule = self._get_schedule_lines()

        # 1. Allocate to penalties first (Daily Compounding)
        # Penalty accrues based on how late the payment actually was
        # (payment_date), not on when it happens to get posted in Odoo —
        # otherwise a delay in recording an on-time payment gets billed as
        # a late one.
        today = self.payment_date or fields.Date.today()
        for entry in schedule:
            if remaining <= 0:
                break
            if entry.due_date and entry.due_date < today:
                loan_product = self.loan_id.loan_product_id
                if loan_product and loan_product.penalty_rate > 0:
                    # Respect grace period before calculating penalties
                    grace_days = loan_product.grace_period_days or 0
                    effective_due_date = entry.due_date + timedelta(days=grace_days)
                    
                    if effective_due_date < today:
                        days_overdue = (today - effective_due_date).days
                        
                        # Add collection stage additional penalty rate if applicable
                        collection_stage = self.loan_id.collection_stage_id
                        additional_penalty = collection_stage.additional_penalty_rate if collection_stage else 0.0
                        total_daily_rate = loan_product.penalty_rate + additional_penalty
                        
                        # Use raw fields — not stored balance_due
                        overdue_amount = max(
                            (entry.principal_due - entry.principal_paid)
                            + (entry.interest_due - entry.interest_paid),
                            0.0,
                        )
                        if overdue_amount > 0:
                            # Daily compounding: A = P(1+r)^n - P
                            daily_rate = total_daily_rate / 100
                            penalty_owed = overdue_amount * ((1 + daily_rate) ** days_overdue - 1)
                            pay_penalty = min(remaining, penalty_owed)
                            penalty += pay_penalty
                            remaining -= pay_penalty

        # 2. Allocate to fees / other charges (loan-level, not per instalment)
        # Application fees are recognised at disbursement only and are not
        # collected again on repayments. Do not allocate fees during repayment.

        # 3. Allocate to interest across all instalments (oldest first)
        for entry in schedule:
            if remaining <= 0:
                break
            interest_owed = entry.interest_due - entry.interest_paid
            if interest_owed > 0:
                pay_interest = min(remaining, interest_owed)
                interest += pay_interest
                remaining -= pay_interest

        # 4. Allocate to principal across all instalments (oldest first)
        for entry in schedule:
            if remaining <= 0:
                break
            principal_owed = entry.principal_due - entry.principal_paid
            if principal_owed > 0:
                pay_principal = min(remaining, principal_owed)
                principal += pay_principal
                remaining -= pay_principal

        self.write(
            {
                "principal_component": round(principal, 2),
                "interest_component": round(interest, 2),
                "fees_component": round(fees, 2),
                "penalty_component": round(penalty, 2),
            }
        )

    def action_post(self):
        """
        Post the repayment:
        1. Auto-allocate components if not already set.
        2. Post accounting journal entry:
               DR  Bank / Cash Account       (amount_paid)
               CR  Loan Receivable           (principal_component)
               CR  Interest Income           (interest_component)
               CR  Penalty Income            (penalty_component)
        3. Update the repayment schedule entries.
        4. Close the loan if fully repaid.
        """
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    _("Only draft repayments can be posted. '%s' is already %s.")
                    % (rec.payment_reference or rec.id, rec.state)
                )
            if not rec.loan_id:
                raise UserError(_("A loan must be linked before posting a repayment."))
            if rec.loan_id.state in ("written_off", "closed"):
                raise UserError(
                    _("Cannot post a repayment against a %s loan.")
                    % rec.loan_id.state.replace("_", " ")
                )

            # Lock the loan row for the rest of this transaction so two
            # concurrent repayment postings on the same loan (e.g. two
            # near-simultaneous M-Pesa confirmations) can't both read the
            # same pre-payment schedule baseline and overwrite each other's
            # allocation in _update_schedule_entries(). The second poster
            # blocks here until the first one commits.
            self.env.cr.execute(
                "SELECT id FROM alba_loan WHERE id = %s FOR UPDATE",
                (rec.loan_id.id,),
            )

            # Auto-allocate if components are all zero
            total_comp = (
                rec.principal_component
                + rec.interest_component
                + rec.fees_component
                + rec.penalty_component
            )
            if total_comp == 0.0:
                rec._auto_allocate_components()

            # Auto-select journal if not set
            if not rec.journal_id:
                rec.journal_id = self.env["account.journal"].search([
                    ("type", "=", "bank"),
                ], limit=1) or self.env["account.journal"].search([
                    ("type", "=", "cash"),
                ], limit=1)

            # Validate journal
            if not rec.journal_id:
                raise UserError(
                    _("Please select a Payment Journal (Bank or Cash) before posting.")
                )
            if rec.journal_id.type not in ("bank", "cash"):
                raise UserError(
                    _(
                        "Payment journal '%s' must be a Bank or Cash journal."
                    ) % rec.journal_id.display_name
                )

            rec._ensure_payment_method_line()

            outstanding_account = (
                rec.payment_method_line_id.payment_account_id
                or rec.journal_id.default_account_id
            )
            if not outstanding_account:
                raise UserError(
                    _(
                        'Journal "%s" has no bank/cash account configured for receipts. '
                        'Please set the journal default account or the inbound payment method account '
                        'before posting repayments.'
                    ) % rec.journal_id.name
                )

            product = rec.loan_product_id
            if not product.account_loan_receivable_id:
                raise UserError(
                    _("Please configure the Loan Receivable account on product '%s'.")
                    % product.name
                )
            if not product.account_interest_receivable_id:
                raise UserError(_("Please configure Interest Receivable account on product '%s'.") % product.name)
            if rec.fees_component > 0 and not product.account_fees_income_id:
                raise UserError(_("Please configure a Fee Income account on product '%s' to post fee components.") % product.name)

            move_vals = {
                "journal_id": rec.journal_id.id,
                "date": rec.payment_date,
                "ref": f"RPMT/{rec.loan_id.loan_number}/{rec.payment_reference or rec.id}",
                "currency_id": rec.currency_id.id,
                "alba_loan_id": rec.loan_id.id,
                "narration": _("Loan repayment — %s — %s")
                % (rec.loan_id.loan_number, rec.customer_id.display_name),
                "preferred_payment_method_line_id": rec.payment_method_line_id.id if rec.payment_method_line_id else False,
                "line_ids": [
                    # DR Actual bank/cash account used for the receipt
                    (0, 0, {
                        "account_id": outstanding_account.id,
                        "name": _("Repayment — %s") % (rec.payment_reference or rec.loan_id.loan_number),
                        "debit": rec.amount_paid if rec.currency_id == rec.company_id.currency_id else 0.0,
                        "credit": 0.0,
                        "amount_currency": rec.amount_paid,
                        "currency_id": rec.currency_id.id,
                        "partner_id": rec.partner_id.id,
                    }),
                ],
            }

            # CR Loan Receivable (principal portion + any true prepayments only)
            # fees_component is handled separately via the Fee Income account below
            receivable_amount = rec.principal_component + rec.unallocated_amount
            if receivable_amount > 0:
                move_vals["line_ids"].append((0, 0, {
                    "account_id": product.account_loan_receivable_id.id,
                    "name": _("Principal repayment — %s") % rec.loan_id.loan_number,
                    "debit": 0.0,
                    "credit": receivable_amount if rec.currency_id == rec.company_id.currency_id else 0.0,
                    "amount_currency": -receivable_amount,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))

            # CR Loan Interest Receivable (interest portion)
            if rec.interest_component > 0:
                move_vals["line_ids"].append((0, 0, {
                    "account_id": product.account_interest_receivable_id.id,
                    "name": _("Interest repayment — %s") % rec.loan_id.loan_number,
                    "debit": 0.0,
                    "credit": rec.interest_component if rec.currency_id == rec.company_id.currency_id else 0.0,
                    "amount_currency": -rec.interest_component,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))

            # CR Penalty Receivable (if any)
            if rec.penalty_component > 0:
                penalty_acc = product.account_penalty_receivable_id or product.account_interest_receivable_id
                move_vals["line_ids"].append((0, 0, {
                    "account_id": penalty_acc.id,
                    "name": _("Penalty repayment — %s") % rec.loan_id.loan_number,
                    "debit": 0.0,
                    "credit": rec.penalty_component if rec.currency_id == rec.company_id.currency_id else 0.0,
                    "amount_currency": -rec.penalty_component,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))

            # CR Fee Income (fee component — recognised as income, not a receivable reduction)
            if rec.fees_component > 0 and product.account_fees_income_id:
                move_vals["line_ids"].append((0, 0, {
                    "account_id": product.account_fees_income_id.id,
                    "name": _("Fee income — %s") % rec.loan_id.loan_number,
                    "debit": 0.0,
                    "credit": rec.fees_component if rec.currency_id == rec.company_id.currency_id else 0.0,
                    "amount_currency": -rec.fees_component,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))
            move = rec.env["account.move"].create(move_vals)
            move.action_post()
            move.write({
                "ref": move.ref,
                "is_move_sent": False,
            })

            rec.write({"state": "posted", "move_id": move.id})

            # Update repayment schedule
            rec._update_schedule_entries()

            # ── Ensure loan state reflects the repayment immediately ────────
            # The schedule entries' stored computed fields (balance_due, status)
            # may still be cached from before this transaction.  Invalidate the
            # ORM cache so the next reads go back to the DB (which now has fresh
            # principal_paid / interest_paid values), then explicitly recompute
            # the full status chain: financials → PAR → loan state.
            loan = rec.loan_id
            loan.repayment_schedule_ids.invalidate_recordset(
                ["balance_due", "total_paid", "status", "days_overdue"]
            )
            loan._compute_financial_totals()
            loan._compute_par()
            loan._compute_state()

            # Auto-close loan if outstanding balance is zero
            if loan.outstanding_balance <= 0.01 and loan.state not in ("closed", "written_off"):
                loan.action_close()

            # Dynamic provisioning adjustment after repayment
            loan.action_post_provisioning_entry()

            rec.message_post(
                body=_(
                    "Repayment of <b>%(currency)s %(amount).2f</b> posted. "
                    "Journal entry: <b>%(move)s</b>. "
                    "Principal: %(principal).2f | Interest: %(interest).2f | Fees: %(fees).2f",
                    currency=rec.currency_id.name,
                    amount=rec.amount_paid,
                    move=move.name,
                    principal=rec.principal_component,
                    interest=rec.interest_component,
                    fees=rec.fees_component,
                )
            )

            # ── Automated repayment receipt email ───────────────────────────
            receipt_template = self.env.ref(
                "alba_loans.email_template_repayment_receipt",
                raise_if_not_found=False,
            )
            if receipt_template and rec.customer_id.email:
                try:
                    receipt_template.send_mail(rec.id, force_send=False)
                except Exception as exc:
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "action_post: failed to send repayment receipt email for %s: %s",
                        rec.payment_reference, exc,
                    )

        return True

    def _update_schedule_entries(self):
        """
        Mark schedule entries as paid/partial based on the posted repayment
        components.  Allocates penalty, interest, and principal across the oldest
        unpaid/partial instalments first.

        SAFE PATTERN: Uses _get_schedule_lines() which filters in Python memory
        rather than relying on the stale stored `balance_due` DB field.
        """
        self.ensure_one()
        remaining_penalty = self.penalty_component
        remaining_interest = self.interest_component
        remaining_principal = self.principal_component

        if remaining_principal <= 0 and remaining_interest <= 0 and remaining_penalty <= 0:
            return

        # SAFE: in-memory filtering via raw principal/interest/penalty fields
        schedule = self._get_schedule_lines()

        for entry in schedule:
            if remaining_principal <= 0 and remaining_interest <= 0 and remaining_penalty <= 0:
                break

            penalty_owed = entry.penalty_due - entry.penalty_paid
            interest_owed = entry.interest_due - entry.interest_paid
            principal_owed = entry.principal_due - entry.principal_paid

            penalty_pay = min(remaining_penalty, max(penalty_owed, 0.0))
            interest_pay = min(remaining_interest, max(interest_owed, 0.0))
            principal_pay = min(remaining_principal, max(principal_owed, 0.0))

            if penalty_pay == 0.0 and interest_pay == 0.0 and principal_pay == 0.0:
                continue

            new_penalty_paid = round(entry.penalty_paid + penalty_pay, 2)
            new_interest_paid = round(entry.interest_paid + interest_pay, 2)
            new_principal_paid = round(entry.principal_paid + principal_pay, 2)

            entry.write(
                {
                    "penalty_paid": new_penalty_paid,
                    "interest_paid": new_interest_paid,
                    "principal_paid": new_principal_paid,
                }
            )
            # NOTE: do NOT call _compute_balance_due() / _compute_status() manually
            # here.  Those are stored computed fields; direct in-memory calls only
            # update the Python-side cache and never flush to the DB.  The ORM
            # dependency tracker will recompute them correctly once the write() above
            # propagates through the normal @api.depends chain.

            remaining_penalty -= penalty_pay
            remaining_interest -= interest_pay
            remaining_principal -= principal_pay

    def action_reverse(self):
        """Reverse a posted repayment and its journal entry."""
        self.ensure_one()
        if self.state != "posted":
            raise UserError(_("Only posted repayments can be reversed."))
        if not self.reversal_reason:
            raise UserError(_("Please provide a reversal reason before reversing."))

        if self.move_id:
            reversal = self.move_id._reverse_moves(
                [
                    {
                        "date": fields.Date.today(),
                        "journal_id": self.move_id.journal_id.id,
                        "reason": self.reversal_reason,
                    }
                ]
            )
            reversal.action_post()
            self.write({"reversal_move_id": reversal.id})

        self.write({"state": "reversed"})
        
        # 1. Reset and recompute paid amounts on schedule entries
        self.loan_id._recompute_schedule_paid_amounts()
        
        # 2. Force recomputation of financial totals on the loan
        self.loan_id._compute_financial_totals()

        # 3. Recompute PAR and state so the loan's classification is immediately
        #    correct — not just after the next daily cron run.
        self.loan_id._compute_par()
        self.loan_id._compute_state()
        
        # 4. If loan was automatically closed but now has outstanding balance, move back to active
        if self.loan_id.state == "closed" and self.loan_id.outstanding_balance > 0.01:
            self.loan_id.write({"state": "normal"})
            self.loan_id.message_post(
                body=Markup(_("Loan <b>reopened</b> to Active state due to payment reversal."))
            )

        self.message_post(
            body=Markup(_("Repayment <b>reversed</b>. Reason: %s")) % self.reversal_reason
        )
        return True

    # =========================================================================
    # ORM Overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("payment_reference"):
                vals["payment_reference"] = (
                    seq.next_by_code("alba.loan.repayment.seq") or "New"
                )
            if vals.get("journal_id") and not vals.get("payment_method_line_id"):
                method_line = self.env["account.payment.method.line"].search([
                    ("payment_type", "=", "inbound"),
                    ("journal_id", "=", vals["journal_id"]),
                ], limit=1)
                if method_line:
                    vals["payment_method_line_id"] = method_line.id
        return super().create(vals_list)

    def name_get(self):
        return [
            (
                rec.id,
                "%s — %s"
                % (
                    rec.payment_reference or str(rec.id),
                    rec.loan_id.loan_number if rec.loan_id else "",
                ),
            )
            for rec in self
        ]
