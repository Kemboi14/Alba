# -*- coding: utf-8 -*-
"""
Alba Capital Loan Partial Payoff
Allow customers to pay extra to reduce principal without full settlement
Two modes: Reduce EMI (keep tenure) or Reduce Tenure (keep EMI)
NO FEE - encourages faster loan repayment
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from datetime import date, timedelta


class AlbaLoanPartialPayoff(models.Model):
    """Partial Payoff - Extra payment to reduce principal"""
    
    _name = "alba.loan.partial.payoff"
    _description = "Loan Partial Payoff"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin", "alba.loan.modification.mixin"]
    
    # Identification
    name = fields.Char(string="Reference", required=True, copy=False, default="New")
    
    # Links
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="restrict",
        domain="[('state', 'not in', ['draft', 'closed', 'written_off'])]",
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="loan_id.customer_id",
        store=True,
        readonly=False,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="loan_id.customer_id.partner_id",
        store=True,
        readonly=False,
    )
    
    # Current Loan Details
    current_outstanding = fields.Monetary(
        string="Current Outstanding",
        currency_field="currency_id",
        related="loan_id.outstanding_balance",
        store=True,
    )
    current_principal = fields.Monetary(
        string="Current Principal",
        currency_field="currency_id",
        related="loan_id.principal_amount",
        store=True,
    )
    current_emi = fields.Monetary(
        string="Current EMI",
        currency_field="currency_id",
        related="loan_id.installment_amount",
        store=True,
    )
    remaining_tenure = fields.Integer(
        string="Remaining Months",
        related="loan_id.remaining_tenure",
        store=True,
    )
    schedule_generated = fields.Boolean(
        related="loan_id.schedule_generated",
        string="Schedule Generated",
        readonly=True,
    )
    
    # Payoff Details
    payoff_amount = fields.Monetary(
        string="Payoff Amount",
        currency_field="currency_id",
        required=True,
        help="Extra amount customer wants to pay to reduce principal",
    )
    reduction_mode = fields.Selection([
        ("reduce_emi", "Reduce EMI (Keep Same Tenure)"),
        ("reduce_tenure", "Reduce Tenure (Keep Same EMI)"),
    ], string="Reduction Mode", required=True, default="reduce_emi",
       help="Reduce EMI: Lower monthly payment, same duration\nReduce Tenure: Same payment, finish earlier")
    
    # Calculated Results
    principal_reduction = fields.Monetary(
        string="Principal Reduction",
        currency_field="currency_id",
        compute="_compute_reduction",
        store=True,
        inverse="_inverse_noop",
    )
    interest_saved = fields.Monetary(
        string="Interest Saved",
        currency_field="currency_id",
        compute="_compute_reduction",
        store=True,
        inverse="_inverse_noop",
    )
    new_outstanding = fields.Monetary(
        string="New Outstanding",
        currency_field="currency_id",
        compute="_compute_reduction",
        store=True,
        inverse="_inverse_noop",
    )
    new_emi = fields.Monetary(
        string="New EMI",
        currency_field="currency_id",
        compute="_compute_reduction",
        store=True,
        inverse="_inverse_noop",
    )
    new_tenure = fields.Integer(
        string="New Tenure (Months)",
        compute="_compute_reduction",
        store=True,
        inverse="_inverse_noop",
    )
    emi_reduction = fields.Monetary(
        string="EMI Reduction",
        currency_field="currency_id",
        compute="_compute_reduction",
        store=True,
        inverse="_inverse_noop",
    )
    tenure_reduction = fields.Integer(
        string="Tenure Reduction (Months)",
        compute="_compute_reduction",
        store=True,
        inverse="_inverse_noop",
    )
    
    # Quote Validity
    quote_date = fields.Date(string="Quote Date", default=fields.Date.today)
    quote_valid_until = fields.Date(
        string="Quote Valid Until",
        compute="_compute_quote_validity",
        store=True,
        inverse="_inverse_noop",
    )
    
    # Currency
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="loan_id.currency_id",
        store=True,
    )
    
    # Status
    state = fields.Selection([
        ("draft", "Draft"),
        ("quoted", "Payoff Created"),
        ("accepted", "Accepted"),
        ("applied", "Applied"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    ], string="Status", default="draft")
    
    # Processing
    payment_date = fields.Date(string="Payment Date")
    payment_method = fields.Selection([
        ("cash", "Cash"),
        ("bank_transfer", "Bank Transfer"),
        ("mpesa", "M-Pesa"),
        ("cheque", "Cheque"),
    ], string="Payment Method")
    payment_reference = fields.Char(string="Payment Reference")
    journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Bank or Cash journal where payment was received",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Journal Payment Method",
        domain="[('payment_type', '=', 'inbound'), ('journal_id', '=', journal_id)]",
        help="Specific payment method for the selected journal.",
    )
    
    # Links
    repayment_id = fields.Many2one(
        "alba.loan.repayment",
        string="Repayment Record",
        readonly=True,
    )
    
    # Applied By
    processed_by = fields.Many2one("res.users", string="Processed By", readonly=True)
    processed_date = fields.Date(string="Processed Date")

    document_ids = fields.One2many(
        "alba.loan.document",
        "partial_payoff_id",
        string="Supporting Documents",
    )
    document_count = fields.Integer(
        string="Documents",
        compute="_compute_document_count",
    )

    @api.depends(
        "payoff_amount",
        "principal_reduction",
        "interest_saved",
        "new_outstanding",
        "new_emi",
        "new_tenure",
        "current_outstanding",
        "current_emi",
        "remaining_tenure",
        "state",
    )
    def _compute_modification_charts(self):
        return super()._compute_modification_charts()

    @api.depends("document_ids")
    def _compute_document_count(self):
        for rec in self:
            rec.document_count = len(rec.document_ids)

    def _get_modification_comparison_chart(self):
        self.ensure_one()
        if not self.loan_id:
            return None
        return self._build_grouped_bar_chart(
            ["Outstanding", "EMI", "Tenure (mo)"],
            [
                self._chart_amount(self.current_outstanding),
                self._chart_amount(self.current_emi),
                float(self.remaining_tenure or 0),
            ],
            [
                self._chart_amount(self.new_outstanding),
                self._chart_amount(self.new_emi),
                float(self.new_tenure or 0),
            ],
        )

    def _get_modification_impact_chart(self):
        self.ensure_one()
        if not self.payoff_amount:
            return None
        return self._build_doughnut_chart(
            ["Principal Reduction", "Interest Saved", "Remaining Balance"],
            [
                self._chart_amount(self.principal_reduction),
                self._chart_amount(self.interest_saved),
                self._chart_amount(self.new_outstanding),
            ],
        )
    
    # =========================================================================
    # Constraints
    # =========================================================================
    
    _positive_payoff = models.Constraint(
        "CHECK(payoff_amount > 0)",
        "Payoff amount must be positive."
    )
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.depends("quote_date")
    def _compute_quote_validity(self):
        for rec in self:
            if rec.quote_date:
                rec.quote_valid_until = rec.quote_date + timedelta(days=7)
            else:
                rec.quote_valid_until = False
    
    @api.depends("loan_id", "payoff_amount", "reduction_mode")
    def _compute_reduction(self):
        for rec in self:
            if not rec.loan_id or not rec.payoff_amount:
                rec.principal_reduction = 0
                rec.interest_saved = 0
                rec.new_outstanding = 0
                rec.new_emi = 0
                rec.new_tenure = 0
                rec.emi_reduction = 0
                rec.tenure_reduction = 0
                continue
            
            loan = rec.loan_id
            current_outstanding = loan.outstanding_balance
            
            # Principal reduction = payoff amount (all goes to principal)
            rec.principal_reduction = rec.payoff_amount
            rec.new_outstanding = current_outstanding - rec.payoff_amount
            
            # Calculate interest saved
            if loan.interest_method == "flat_rate":
                # Flat rate: Interest = Principal * Rate * Time
                rate_per_month = loan.interest_rate / 100
                rec.interest_saved = rec.payoff_amount * rate_per_month * loan.remaining_tenure
            else:
                # Reducing balance: Complex calculation - approximate
                # Simplified: assume average interest on reduced principal
                rate_per_month = loan.interest_rate / 100
                avg_reduction = rec.payoff_amount / 2  # Principal reduces over time
                rec.interest_saved = avg_reduction * rate_per_month * loan.remaining_tenure
            
            # Calculate new terms based on mode
            rate = loan.interest_rate / 100  # monthly rate
            n = loan.remaining_tenure

            if rec.reduction_mode == "reduce_emi":
                # Keep same tenure, recalculate EMI on reduced outstanding
                rec.new_tenure = n
                if n > 0:
                    if loan.interest_method == "reducing_balance" and rate > 0:
                        # Annuity formula on new outstanding
                        rec.new_emi = round(
                            rec.new_outstanding * rate * (1 + rate) ** n
                            / ((1 + rate) ** n - 1),
                            2,
                        )
                    elif loan.interest_method == "reducing_balance" and rate == 0:
                        rec.new_emi = round(rec.new_outstanding / n, 2)
                    else:
                        # Flat-rate: (P_new + P_new*r*n) / n
                        rec.new_emi = round(
                            (rec.new_outstanding + rec.new_outstanding * rate * n) / n,
                            2,
                        )
                else:
                    rec.new_emi = 0
                rec.emi_reduction = max(loan.installment_amount - rec.new_emi, 0.0)
                rec.tenure_reduction = 0
            else:  # reduce_tenure
                # Keep same EMI, reduce tenure
                rec.new_emi = loan.installment_amount
                if loan.installment_amount > 0:
                    if loan.interest_method == "reducing_balance" and rate > 0:
                        # Solve for n: new_outstanding = EMI * (1 - (1+r)^-n) / r
                        import math
                        emi = loan.installment_amount
                        p = rec.new_outstanding
                        if emi > p * rate:  # Ensure EMI > interest on balance
                            rec.new_tenure = int(
                                math.ceil(-math.log(1 - p * rate / emi) / math.log(1 + rate))
                            )
                        else:
                            rec.new_tenure = n  # fallback: EMI too low to amortise
                    else:
                        # Flat-rate or zero-interest approximation.
                        # Round up: paying off in "1.2 installments" still
                        # requires 2 installments, not 1 — truncating would
                        # understate the remaining tenure.
                        import math
                        rec.new_tenure = int(
                            math.ceil(rec.new_outstanding / loan.installment_amount)
                        )
                else:
                    rec.new_tenure = 0
                rec.emi_reduction = 0
                rec.tenure_reduction = loan.remaining_tenure - rec.new_tenure

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        for rec in self:
            if rec.payment_method_line_id and rec.payment_method_line_id.journal_id != rec.journal_id:
                rec.payment_method_line_id = False

    def _inverse_noop(self):
        pass

    def _ensure_payment_method_line(self):
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
                    raise UserError(_("Please select an inbound payment method for payment journal '%s'.") % rec.journal_id.display_name)
                continue

            method_line = self.env["account.payment.method.line"].search([
                ("payment_type", "=", "inbound"),
                ("journal_id", "=", rec.journal_id.id),
            ], limit=1)
            if not method_line:
                raise UserError(_("Please configure an inbound Payment Method on payment journal '%s'.") % rec.journal_id.display_name)
            rec.payment_method_line_id = method_line
    
    # =========================================================================
    # ORM Overrides
    # =========================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("alba.loan.partial.payoff") or "New"
        return super().create(vals_list)
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_generate_quote(self):
        """Generate quote for customer"""
        for rec in self:
            # Validate
            if rec.payoff_amount >= rec.current_outstanding:
                raise UserError(_("Payoff amount must be less than outstanding balance. Use Early Settlement for full payoff."))
            
            if rec.payoff_amount <= 0:
                raise UserError(_("Payoff amount must be positive."))
            
            rec.write({
                "state": "quoted",
                "quote_date": fields.Date.today(),
            })
            
            # Generate message for customer
            if rec.reduction_mode == "reduce_emi":
                mode_desc = _("EMI will reduce by %s %s") % (rec.currency_id.symbol, rec.emi_reduction)
            else:
                mode_desc = _("Tenure will reduce by %s months") % rec.tenure_reduction
            
            rec.message_post(body=_(
                "<b>PARTIAL PAYOFF QUOTE</b>: %s %s (%s). Valid until: %s"
            ) % (
                rec.currency_id.symbol, rec.payoff_amount,
                mode_desc,
                rec.quote_valid_until,
            ))
    
    def action_accept(self):
        """Customer accepts quote"""
        for rec in self:
            # Check if quote expired
            if fields.Date.today() > rec.quote_valid_until:
                rec.state = "expired"
                raise UserError(_("Quote has expired. Please generate a new quote."))
            
            rec.write({
                "state": "accepted",
            })
            rec.message_post(body=_("Quote accepted."))
    
    def action_apply(self):
        """Apply partial payoff to loan"""
        for rec in self:
            if rec.state not in ["quoted", "accepted"]:
                raise UserError(_("Payoff must be quoted and accepted before application."))

            # A single-instalment loan (e.g. Salary Advance) has no future
            # instalment left to regenerate once this payoff's own repayment
            # marks its one-and-only schedule line as history — regenerating
            # a shorter-than-history schedule always fails in that case (see
            # action_generate_schedule's future_count guard). There's no
            # partial-payoff concept on a loan that only ever had one
            # instalment; direct the user to full/early settlement instead.
            if rec.loan_id.tenure_months <= 1:
                raise UserError(_(
                    "Partial payoff is not available on single-instalment loans "
                    "(tenure = %d month). Use Early Settlement or a full repayment instead."
                ) % rec.loan_id.tenure_months)

            # Check if quote expired
            if fields.Date.today() > rec.quote_valid_until:
                rec.state = "expired"
                raise UserError(_("Quote has expired. Please generate a new quote."))

            # Lock the loan row for the rest of this transaction so a
            # concurrent repayment/holiday/another payoff on the same loan
            # can't slip in between the quote and this apply.
            self.env.cr.execute(
                "SELECT id FROM alba_loan WHERE id = %s FOR UPDATE",
                (rec.loan_id.id,),
            )

            # payoff_amount was only validated against outstanding_balance
            # at quote time (action_generate_quote). Time may have passed
            # since then — another repayment posted, a payment holiday
            # capitalized interest — so re-validate against the loan's LIVE
            # outstanding balance before actually applying it.
            outstanding_balance = rec.loan_id.outstanding_balance
            if rec.payoff_amount >= outstanding_balance:
                raise UserError(_("Payoff amount must be less than outstanding balance. Use Early Settlement for full payoff."))

            loan = rec.loan_id

            # Auto-select journal if not set
            if not rec.journal_id:
                rec.journal_id = self.env["account.journal"].search([
                    ("type", "=", "bank"),
                ], limit=1)
            
            if not rec.journal_id:
                raise UserError(_("Please select a Payment Journal before applying."))
            
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
                        'before applying partial payoff.'
                    ) % rec.journal_id.name
                )
            
            # Create repayment record
            pay_method = rec.payment_method
            if not pay_method:
                if rec.journal_id.type == 'cash':
                    pay_method = 'cash'
                elif 'mpesa' in (rec.journal_id.name or '').lower():
                    pay_method = 'mpesa'
                else:
                    pay_method = 'bank_transfer'

            # Force the full payoff amount to principal — a partial payoff is
            # a voluntary extra principal reduction (see _compute_reduction:
            # "Principal reduction = payoff amount"), not a regular
            # instalment payment. Without an explicit principal_component,
            # action_post()'s auto-allocation would divert part of it to any
            # outstanding penalty/interest first, leaving the schedule and
            # loan.principal_amount (reduced by the full payoff_amount below)
            # out of sync with what the repayment actually recorded.
            repayment = self.env["alba.loan.repayment"].create({
                "loan_id": loan.id,
                "payment_date": rec.payment_date or fields.Date.today(),
                "amount_paid": rec.payoff_amount,
                "principal_component": rec.payoff_amount,
                "interest_component": 0.0,
                "fees_component": 0.0,
                "penalty_component": 0.0,
                "payment_method": pay_method,
                "payment_reference": rec.payment_reference or rec.name,
                "journal_id": rec.journal_id.id,
                "payment_method_line_id": rec.payment_method_line_id.id,
                "notes": _("Partial Payoff - %s") % rec.name,
            })
            repayment.action_post()

            # Apply principal reduction to loan.
            # NOTE: outstanding_balance / installment_amount are computed
            # fields driven by the repayment schedule — writing them
            # directly is a no-op (see loan_topup.py). The real inputs are
            # principal_amount (always reduced) and, for "reduce_tenure"
            # mode, tenure_months — action_generate_schedule() below derives
            # the new outstanding balance and installment amount from these.
            new_outstanding = loan.outstanding_balance - rec.principal_reduction
            new_principal_amount = max(loan.principal_amount - rec.principal_reduction, 0.0)
            loan_write_vals = {"principal_amount": new_principal_amount}
            if rec.reduction_mode == "reduce_tenure":
                loan_write_vals["tenure_months"] = rec.new_tenure or loan.tenure_months
            loan.write(loan_write_vals)

            # Archive the current schedule batch (self-contained, matching
            # the pattern in loan_topup.py's action_disburse — no separate
            # manual "archive" click required) then regenerate against the
            # new terms and reapply every already-posted repayment so DPD/
            # PAR/state don't reset to "unpaid" on instalments that were
            # already settled.
            Batch = self.env["alba.repayment.schedule.batch"]
            existing_batch = Batch.search([("loan_id", "=", loan.id), ("state", "=", "active")])
            if existing_batch:
                existing_batch.write({"state": "archived"})
            loan.write({"schedule_generated": False})
            loan.action_generate_schedule()
            loan._recompute_schedule_paid_amounts()

            # Update payoff record
            rec.write({
                "state": "applied",
                "repayment_id": repayment.id,
                "processed_by": self.env.user.id,
                "processed_date": fields.Date.today(),
            })
            
            # Send Email
            template = self.env.ref('alba_loans.email_template_partial_payoff', raise_if_not_found=False)
            if template:
                template.send_mail(rec.id, force_send=True)

            # Log
            if rec.reduction_mode == "reduce_emi":
                mode_result = _("EMI reduced by %s %s") % (rec.currency_id.symbol, rec.emi_reduction)
            else:
                mode_result = _("Tenure reduced by %s months") % rec.tenure_reduction
            
            rec.message_post(body=_(
                "<b>PARTIAL PAYOFF APPLIED</b>: %s %s reduced principal. %s."
            ) % (
                rec.currency_id.symbol, rec.principal_reduction,
                mode_result,
            ))
            
            loan.message_post(body=_(
                "<b>PARTIAL PAYOFF APPLIED</b>: %s %s. New Outstanding: %s %s"
            ) % (rec.currency_id.symbol, rec.payoff_amount,
                 rec.currency_id.symbol, new_outstanding))
    
    def action_archive_schedule(self):
        """Archive the active repayment schedule batch for this loan so a new
        one can be generated after the partial payoff is applied."""
        for rec in self:
            loan = rec.loan_id
            Batch = self.env["alba.repayment.schedule.batch"]
            existing = Batch.search([("loan_id", "=", loan.id), ("state", "=", "active")])
            if existing:
                existing.write({"state": "archived"})
                loan.write({"schedule_generated": False})
                rec.message_post(body=_(
                    "<b>Schedule Archived</b>: Existing repayment schedule archived. "
                    "You can now apply the payoff and a new schedule will be generated."
                ))
            else:
                # No active batch — may use legacy schedule lines; reset the flag
                loan.write({"schedule_generated": False})
                rec.message_post(body=_(
                    "<b>Schedule Reset</b>: schedule_generated flag cleared. "
                    "You can now apply the payoff."
                ))

    def action_cancel(self):
        """Cancel draft/quoted payoff"""
        for rec in self:
            if rec.state not in ["draft", "quoted", "accepted"]:
                raise UserError(_("Only draft, quoted, or accepted payoffs can be cancelled."))
            rec.write({
                "state": "cancelled",
            })
    
    def action_reset_to_draft(self):
        """Reset to draft"""
        for rec in self:
            if rec.state not in ["quoted", "accepted", "expired"]:
                raise UserError(_("Can only reset quoted, accepted, or expired payoffs."))
            rec.write({
                "state": "draft",
                "quote_date": False,
            })

    def action_view_loan(self):
        """Navigate to the linked loan"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loan"),
            "res_model": "alba.loan",
            "view_mode": "form",
            "res_id": self.loan_id.id,
        }
