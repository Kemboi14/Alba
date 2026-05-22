# -*- coding: utf-8 -*-
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
        tracking=True,
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
        tracking=True,
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
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="loan_id.customer_id.partner_id",
        store=True,
        readonly=True,
    )
    loan_product_id = fields.Many2one(
        "alba.loan.product",
        string="Loan Product",
        related="loan_id.loan_product_id",
        store=True,
        readonly=True,
    )

    # ── Payment Details ───────────────────────────────────────────────────────
    payment_date = fields.Date(
        string="Payment Date",
        required=True,
        tracking=True,
        default=fields.Date.today,
    )
    amount_paid = fields.Monetary(
        string="Amount Paid",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )

    # ── Allocation ────────────────────────────────────────────────────────────
    principal_component = fields.Monetary(
        string="Principal Component",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    interest_component = fields.Monetary(
        string="Interest Component",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    fees_component = fields.Monetary(
        string="Fees Component",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    penalty_component = fields.Monetary(
        string="Penalty / Late Fee Component",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    total_allocated = fields.Monetary(
        string="Total Allocated",
        currency_field="currency_id",
        compute="_compute_total_allocated",
        store=True,
    )
    unallocated_amount = fields.Monetary(
        string="Unallocated Amount",
        currency_field="currency_id",
        compute="_compute_total_allocated",
        store=True,
        help="Difference between amount paid and total allocation across components.",
    )

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
        tracking=True,
    )
    mpesa_transaction_id = fields.Char(
        string="M-Pesa Transaction ID",
        copy=False,
        index=True,
        tracking=True,
    )
    bank_transaction_id = fields.Char(
        string="Bank Transaction ID / Cheque No.",
        copy=False,
    )
    received_by = fields.Many2one(
        "res.users",
        string="Received By",
        default=lambda self: self.env.uid,
        tracking=True,
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
        tracking=True,
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
        api_key.send_webhook(event_type, payload)

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
        tracking=True,
        help="Bank or Cash journal into which this payment was received.",
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
    _django_payment_id_not_empty = models.Constraint(
        "CHECK(django_payment_id IS NULL OR django_payment_id != '')",
        "Django payment ID cannot be empty string.",
    )

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

        # Pull overdue/pending schedule entries ordered by due_date asc
        schedule = self.env["alba.repayment.schedule"].search(
            [
                ("loan_id", "=", self.loan_id.id),
                ("balance_due", ">", 0),
            ],
            order="due_date asc",
        )

        # 1. Allocate to penalties first (Daily Compounding)
        for entry in schedule:
            if remaining <= 0:
                break
            
            if entry.due_date and entry.due_date < fields.Date.today():
                loan_product = self.loan_id.loan_product_id
                if loan_product and loan_product.penalty_rate > 0:
                    days_overdue = (fields.Date.today() - entry.due_date).days
                    overdue_amount = entry.balance_due
                    # Daily compounding: A = P(1+r)^n - P
                    daily_rate = (loan_product.penalty_rate / 100)
                    penalty_owed = overdue_amount * ((1 + daily_rate)**days_overdue - 1)
                    
                    pay_penalty = min(remaining, penalty_owed)
                    penalty += pay_penalty
                    remaining -= pay_penalty

        # 2. Allocate to fees / other charges
        for entry in schedule:
            if remaining <= 0:
                break
            
            # Allocate to fees based on loan product fee structure
            if fees == 0:  # Only allocate fees once if they are fixed, or per instalment if applicable
                loan_product = self.loan_id.loan_product_id
                if loan_product:
                    fee_amount = loan_product.calculate_total_fees(self.loan_id.principal_amount)
                    # Only pay unpaid portion
                    total_fees_paid = sum(self.loan_id.repayment_ids.mapped('fees_component'))
                    unpaid_fees = max(0, fee_amount - total_fees_paid)
                    pay_fees = min(remaining, unpaid_fees)
                    fees += pay_fees
                    remaining -= pay_fees
        
        # 3. Allocate to interest across all instalments
        for entry in schedule:
            if remaining <= 0:
                break
            interest_owed = entry.interest_due - entry.interest_paid
            if interest_owed > 0:
                pay_interest = min(remaining, interest_owed)
                interest += pay_interest
                remaining -= pay_interest
        
        # 4. Allocate to principal across all instalments
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
               CR  Fee Income                (fees_component)
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
            if rec.loan_id.state == "written_off":
                raise UserError(
                    _("Cannot post a repayment against a written-off loan.")
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

            # Validate journal
            if not rec.journal_id:
                raise UserError(
                    _("Please select a Payment Journal (Bank or Cash) before posting.")
                )
            bank_account = rec.journal_id.default_account_id
            if not bank_account:
                raise UserError(
                    _("Journal '%s' has no default account configured.")
                    % rec.journal_id.name
                )

            product = rec.loan_product_id
            if not product.account_loan_receivable_id:
                raise UserError(
                    _("Please configure the Loan Receivable account on product '%s'.")
                    % product.name
                )

            move_vals = {
                "journal_id": rec.journal_id.id,
                "date": rec.payment_date,
                "ref": f"RPMT/{rec.loan_id.loan_number}/{rec.payment_reference or rec.id}",
                "currency_id": rec.currency_id.id,
                "narration": _("Loan repayment — %s — %s")
                % (rec.loan_id.loan_number, rec.customer_id.display_name),
                "line_ids": [
                    # DR Bank / Cash
                    (0, 0, {
                        "account_id": bank_account.id,
                        "name": _("Repayment — %s") % (rec.payment_reference or rec.loan_id.loan_number),
                        "debit": rec.amount_paid if rec.currency_id == rec.company_id.currency_id else 0.0,
                        "credit": 0.0,
                        "amount_currency": rec.amount_paid,
                        "currency_id": rec.currency_id.id,
                        "partner_id": rec.partner_id.id,
                    }),
                ],
            }

            # CR Loan Receivable (principal)
            if rec.principal_component > 0:
                move_vals["line_ids"].append((0, 0, {
                    "account_id": product.account_loan_receivable_id.id,
                    "name": _("Principal repayment — %s") % rec.loan_id.loan_number,
                    "debit": 0.0,
                    "credit": rec.principal_component if rec.currency_id == rec.company_id.currency_id else 0.0,
                    "amount_currency": -rec.principal_component,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))

            # CR Interest Income
            if rec.interest_component > 0:
                interest_account = product.account_interest_income_id
                if not interest_account:
                    raise UserError(_("Please configure the Interest Income account on product '%s'.") % product.name)
                move_vals["line_ids"].append((0, 0, {
                    "account_id": interest_account.id,
                    "name": _("Interest collected — %s") % rec.loan_id.loan_number,
                    "debit": 0.0,
                    "credit": rec.interest_component if rec.currency_id == rec.company_id.currency_id else 0.0,
                    "amount_currency": -rec.interest_component,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))

            # CR Fee Income
            if rec.fees_component > 0:
                fee_account = product.account_fees_income_id
                if not fee_account:
                    raise UserError(_("Please configure the Fee Income account on product '%s'.") % product.name)
                move_vals["line_ids"].append((0, 0, {
                    "account_id": fee_account.id,
                    "name": _("Fees collected — %s") % rec.loan_id.loan_number,
                    "debit": 0.0,
                    "credit": rec.fees_component if rec.currency_id == rec.company_id.currency_id else 0.0,
                    "amount_currency": -rec.fees_component,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))

            # CR Penalty Income
            if rec.penalty_component > 0:
                penalty_account = product.account_penalty_income_id or product.account_fees_income_id or product.account_interest_income_id
                if not penalty_account:
                    raise UserError(_("Please configure the Penalty Income account on product '%s'.") % product.name)
                move_vals["line_ids"].append((0, 0, {
                    "account_id": penalty_account.id,
                    "name": _("Penalty collected — %s") % rec.loan_id.loan_number,
                    "debit": 0.0,
                    "credit": rec.penalty_component if rec.currency_id == rec.company_id.currency_id else 0.0,
                    "amount_currency": -rec.penalty_component,
                    "currency_id": rec.currency_id.id,
                    "partner_id": rec.partner_id.id,
                }))
            move = rec.env["account.move"].create(move_vals)
            move.action_post()

            rec.write({"state": "posted", "move_id": move.id})

            # Update repayment schedule
            rec._update_schedule_entries()

            # Auto-close loan if outstanding balance is zero
            loan = rec.loan_id
            if loan.outstanding_balance <= 0.01 and loan.state == "active":
                loan.action_close()

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
        components.  Allocates principal and interest across the oldest
        unpaid/partial instalments first.
        """
        self.ensure_one()
        remaining_principal = self.principal_component
        remaining_interest = self.interest_component

        schedule = self.env["alba.repayment.schedule"].search(
            [
                ("loan_id", "=", self.loan_id.id),
                ("balance_due", ">", 0),
            ],
            order="due_date asc",
        )

        for entry in schedule:
            if remaining_principal <= 0 and remaining_interest <= 0:
                break

            interest_owed = entry.interest_due - entry.interest_paid
            principal_owed = entry.principal_due - entry.principal_paid

            interest_pay = min(remaining_interest, max(interest_owed, 0.0))
            principal_pay = min(remaining_principal, max(principal_owed, 0.0))

            if interest_pay == 0.0 and principal_pay == 0.0:
                continue

            new_interest_paid = round(entry.interest_paid + interest_pay, 2)
            new_principal_paid = round(entry.principal_paid + principal_pay, 2)

            entry.write(
                {
                    "interest_paid": new_interest_paid,
                    "principal_paid": new_principal_paid,
                }
            )
            # Recompute status
            entry._compute_status()

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
        
        # 3. If loan was automatically closed but now has outstanding balance, move back to active
        if self.loan_id.state == "closed" and self.loan_id.outstanding_balance > 0.01:
            self.loan_id.write({"state": "active"})
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
