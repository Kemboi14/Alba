# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AlbaLoanDisburseWizardLine(models.TransientModel):
    _name = "alba.loan.disburse.wizard.line"
    _description = "Loan Disbursement Split Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        "alba.loan.disburse.wizard",
        string="Disbursement Wizard",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    journal_id = fields.Many2one(
        "account.journal",
        string="Source Journal",
        required=True,
        domain="[('type', 'in', ['bank', 'cash'])]",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        domain="[('payment_type', '=', 'outbound'), ('journal_id', '=', journal_id)]",
    )
    amount = fields.Monetary(
        string="Amount",
        required=True,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="wizard_id.currency_id",
        readonly=True,
    )

    @api.constrains("amount")
    def _check_amount_positive(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("Split amount must be greater than zero."))

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        for rec in self:
            if rec.payment_method_line_id and rec.payment_method_line_id.journal_id != rec.journal_id:
                rec.payment_method_line_id = False


class AlbaLoanDisburseWizard(models.TransientModel):
    _name = "alba.loan.disburse.wizard"
    _description = "Alba Capital — Loan Disbursement Wizard"

    # ── Application ───────────────────────────────────────────────────────────
    application_id = fields.Many2one(
        "alba.loan.application",
        string="Loan Application",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    application_number = fields.Char(
        string="Application Number",
        related="application_id.application_number",
        readonly=True,
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="application_id.customer_id",
        readonly=True,
    )
    loan_product_id = fields.Many2one(
        "alba.loan.product",
        string="Loan Product",
        related="application_id.loan_product_id",
        readonly=True,
    )

    # ── Disbursement Terms ────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="application_id.currency_id",
        readonly=True,
    )
    approved_amount = fields.Monetary(
        string="Disbursement Amount",
        currency_field="currency_id",
        required=True,
        help="Amount to actually disburse. Defaults to the approved amount on the application.",
    )
    disbursement_date = fields.Date(
        string="Disbursement Date",
        required=True,
        default=fields.Date.today,
    )
    tenure_months = fields.Integer(
        string="Tenure (Months)",
        required=True,
        default=lambda self: self._default_tenure(),
    )
    repayment_frequency = fields.Selection(
        selection=[
            ("weekly", "Weekly"),
            ("fortnightly", "Fortnightly"),
            ("monthly", "Monthly"),
        ],
        string="Repayment Frequency",
        required=True,
        default=lambda self: self._default_frequency(),
    )
    interest_rate = fields.Float(
        string="Interest Rate (% p.m.)",
        digits=(5, 2),
        required=True,
        default=lambda self: self._default_interest_rate(),
        help="Monthly interest rate. Defaults to the loan product rate.",
    )
    interest_method = fields.Selection(
        selection=[
            ("flat_rate", "Flat Rate"),
            ("reducing_balance", "Reducing Balance"),
        ],
        string="Interest Method",
        required=True,
        default=lambda self: self._default_interest_method(),
    )

    # ── Journal & Payment ─────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        "account.journal",
        string="Disbursement Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Bank or Cash journal used for a single-source disbursement.",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        domain="[('payment_type', '=', 'outbound'), ('journal_id', '=', journal_id)]",
        help="Specific payment method (e.g. Manual, M-Pesa B2C) for this journal.",
    )
    split_line_ids = fields.One2many(
        "alba.loan.disburse.wizard.line",
        "wizard_id",
        string="Disbursement Splits",
        help="Use these lines when one loan is funded from more than one bank or cash journal.",
    )
    split_total = fields.Monetary(
        string="Split Total",
        currency_field="currency_id",
        compute="_compute_split_totals",
    )
    split_balance = fields.Monetary(
        string="Unallocated Balance",
        currency_field="currency_id",
        compute="_compute_split_totals",
    )

    # ── Schedule preview ──────────────────────────────────────────────────────
    generate_schedule = fields.Boolean(
        string="Auto-generate Repayment Schedule",
        default=True,
        help="If ticked, an amortisation schedule will be created immediately after disbursement.",
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(
        string="Disbursement Notes",
        help="Internal notes recorded on the loan and the application chatter.",
    )

    # ── Estimated totals (informational) ──────────────────────────────────────
    estimated_total_interest = fields.Monetary(
        string="Estimated Total Interest",
        currency_field="currency_id",
        compute="_compute_estimates",
    )
    estimated_total_repayable = fields.Monetary(
        string="Estimated Total Repayable",
        currency_field="currency_id",
        compute="_compute_estimates",
    )
    estimated_monthly_instalment = fields.Monetary(
        string="Estimated Monthly Instalment",
        currency_field="currency_id",
        compute="_compute_estimates",
    )
    net_disbursement_amount = fields.Monetary(
        string="Net Payout Amount",
        currency_field="currency_id",
        compute="_compute_net_disbursement",
        help="Amount that will actually be paid to the customer after deducting all fees.",
    )

    # =========================================================================
    # Default helpers
    # =========================================================================

    def _default_tenure(self):
        ctx_app_id = self.env.context.get("default_application_id")
        if ctx_app_id:
            app = self.env["alba.loan.application"].browse(ctx_app_id)
            return app.tenure_months or 12
        return 12

    def _default_frequency(self):
        ctx_app_id = self.env.context.get("default_application_id")
        if ctx_app_id:
            app = self.env["alba.loan.application"].browse(ctx_app_id)
            return app.repayment_frequency or "monthly"
        return "monthly"

    def _default_interest_rate(self):
        ctx_app_id = self.env.context.get("default_application_id")
        if ctx_app_id:
            app = self.env["alba.loan.application"].browse(ctx_app_id)
            return app.loan_product_id.interest_rate if app.loan_product_id else 0.0
        return 0.0

    def _default_interest_method(self):
        ctx_app_id = self.env.context.get("default_application_id")
        if ctx_app_id:
            app = self.env["alba.loan.application"].browse(ctx_app_id)
            return (
                app.loan_product_id.interest_method
                if app.loan_product_id
                else "reducing_balance"
            )
        return "reducing_balance"

    # =========================================================================
    # Compute methods
    # =========================================================================

    @api.depends(
        "approved_amount",
        "tenure_months",
        "interest_rate",
        "interest_method",
        "loan_product_id",
    )
    def _compute_estimates(self):
        for rec in self:
            amount = rec.approved_amount or 0.0
            months = rec.tenure_months or 0
            rate = rec.interest_rate or 0.0
            method = rec.interest_method

            if amount <= 0 or months <= 0:
                rec.estimated_total_interest = 0.0
                rec.estimated_total_repayable = 0.0
                rec.estimated_monthly_instalment = 0.0
                continue

            if method == "flat_rate":
                total_interest = round(amount * (rate / 100) * months, 2)
                total_repayable = amount + total_interest
                monthly = round(total_repayable / months, 2)
            else:
                # Reducing balance — use annuity formula
                monthly_rate = rate / 100
                if monthly_rate == 0:
                    monthly = round(amount / months, 2)
                    total_interest = 0.0
                else:
                    monthly = round(
                        amount
                        * monthly_rate
                        * (1 + monthly_rate) ** months
                        / ((1 + monthly_rate) ** months - 1),
                        2,
                    )
                    total_interest = round(monthly * months - amount, 2)
                total_repayable = amount + total_interest

            rec.estimated_total_interest = total_interest
            rec.estimated_total_repayable = total_repayable
            rec.estimated_monthly_instalment = monthly

    @api.depends("approved_amount", "split_line_ids", "split_line_ids.amount")
    def _compute_split_totals(self):
        for rec in self:
            rec.split_total = sum(rec.split_line_ids.mapped("amount"))
            rec.split_balance = (rec.approved_amount or 0.0) - rec.split_total

    @api.depends("approved_amount", "application_id.fee_line_ids.calculated_amount")
    def _compute_net_disbursement(self):
        for rec in self:
            total_fees = sum(rec.application_id.fee_line_ids.mapped("calculated_amount"))
            rec.net_disbursement_amount = (rec.approved_amount or 0.0) - total_fees

    @api.onchange("journal_id", "approved_amount")
    def _onchange_single_journal_split(self):
        """Keep the split tab useful for the common one-journal case."""
        for rec in self:
            if rec.payment_method_line_id and rec.payment_method_line_id.journal_id != rec.journal_id:
                rec.payment_method_line_id = False
            if rec.journal_id and rec.approved_amount and not rec.split_line_ids:
                rec.split_line_ids = [
                    (
                        0,
                        0,
                        {
                            "sequence": 10,
                            "journal_id": rec.journal_id.id,
                            "payment_method_line_id": rec.payment_method_line_id.id if rec.payment_method_line_id else False,
                            "amount": rec.approved_amount,
                        },
                    )
                ]
            elif rec.journal_id and rec.approved_amount and len(rec.split_line_ids) == 1:
                line = rec.split_line_ids[0]
                if line.journal_id == rec.journal_id:
                    line.amount = rec.approved_amount

    def _ensure_payment_method_line(self):
        self.ensure_one()
        if not self.journal_id:
            return
        if self.payment_method_line_id:
            if self.payment_method_line_id.journal_id != self.journal_id:
                raise UserError(_("Selected payment method does not belong to the disbursement journal."))
            if self.payment_method_line_id.payment_type != "outbound":
                raise UserError(_("Please select an outbound payment method for disbursement journal '%s'.") % self.journal_id.display_name)
            return

        method_line = self.env["account.payment.method.line"].search([
            ("payment_type", "=", "outbound"),
            ("journal_id", "=", self.journal_id.id),
        ], limit=1)
        if not method_line:
            raise UserError(_("Please configure an outbound Payment Method on disbursement journal '%s'.") % self.journal_id.display_name)
        self.payment_method_line_id = method_line

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains("approved_amount", "application_id")
    def _check_disbursement_amount(self):
        for rec in self:
            if rec.approved_amount <= 0:
                raise ValidationError(
                    _("Disbursement amount must be greater than zero.")
                )
            product = rec.application_id.loan_product_id
            if product:
                if rec.approved_amount < product.min_amount:
                    raise ValidationError(
                        _(
                            "Disbursement amount %s is below the minimum of %s "
                            "for product '%s'."
                        )
                        % (rec.approved_amount, product.min_amount, product.name)
                    )
                if rec.approved_amount > product.max_amount:
                    raise ValidationError(
                        _(
                            "Disbursement amount %s exceeds the maximum of %s "
                            "for product '%s'."
                        )
                        % (rec.approved_amount, product.max_amount, product.name)
                    )

    @api.constrains("tenure_months")
    def _check_tenure(self):
        for rec in self:
            if rec.tenure_months < 1:
                raise ValidationError(_("Tenure must be at least 1 month."))

    @api.constrains("interest_rate")
    def _check_interest_rate(self):
        for rec in self:
            if rec.interest_rate < 0:
                raise ValidationError(_("Interest rate cannot be negative."))

    @api.constrains("approved_amount", "split_line_ids", "split_line_ids.amount")
    def _check_split_total(self):
        for rec in self:
            if not rec.split_line_ids:
                continue
            total = sum(rec.split_line_ids.mapped("amount"))
            if abs(total - rec.approved_amount) > 0.01:
                raise ValidationError(
                    _("Disbursement splits must total exactly %s. Current total is %s.")
                    % (rec.approved_amount, total)
                )

    def _prepare_disbursement_split_vals(self, loan):
        self.ensure_one()
        lines = self.split_line_ids
        if lines:
            total = sum(lines.mapped("amount"))
            if abs(total - self.approved_amount) > 0.01:
                raise UserError(
                    _("Disbursement splits must total exactly %s. Current total is %s.")
                    % (self.approved_amount, total)
                )
        elif self.journal_id:
            lines = self.env["alba.loan.disburse.wizard.line"].new(
                {
                    "wizard_id": self.id,
                    "sequence": 10,
                    "journal_id": self.journal_id.id,
                    "payment_method_line_id": self.payment_method_line_id.id if self.payment_method_line_id else False,
                    "amount": self.approved_amount,
                }
            )
        else:
            raise UserError(_("Please select a disbursement journal or add split lines."))

        vals_list = []
        for line in lines:
            if not line.journal_id.default_account_id:
                raise UserError(
                    _("The selected journal '%s' has no default account configured.")
                    % line.journal_id.name
                )
            if line.payment_method_line_id:
                if line.payment_method_line_id.journal_id != line.journal_id:
                    raise UserError(_("Selected payment method does not belong to journal '%s'.") % line.journal_id.display_name)
                if line.payment_method_line_id.payment_type != "outbound":
                    raise UserError(_("Please select an outbound payment method for journal '%s'.") % line.journal_id.display_name)
            else:
                line.payment_method_line_id = self.env["account.payment.method.line"].search([
                    ("payment_type", "=", "outbound"),
                    ("journal_id", "=", line.journal_id.id),
                ], limit=1)
                if not line.payment_method_line_id:
                    raise UserError(_("Please configure an outbound Payment Method on journal '%s'.") % line.journal_id.display_name)
            vals_list.append(
                {
                    "loan_id": loan.id,
                    "sequence": line.sequence,
                    "journal_id": line.journal_id.id,
                    "payment_method_line_id": line.payment_method_line_id.id,
                    "amount": line.amount,
                    "state": "approved",
                }
            )
        return vals_list

    # =========================================================================
    # Main disbursement action
    # =========================================================================

    def action_disburse(self):
        """
        Perform the full disbursement atomically:
        1.  Validate the application and journals.
        2.  Create the alba.loan record.
        3.  Post the disbursement clearing journal entry (DR Loan Rec, CR Clearing).
        4.  Create a Payment Voucher (account.payment) to pay out the net amount.
        5.  Create Vendor POs for Credit Life insurance fees.
        6.  Transition the application to 'disbursed'.
        """
        self.ensure_one()
        
        # Lock and validate application
        application = self.application_id.with_env(self.env).sudo().browse(self.application_id.id)
        application.env.cr.execute(
            "SELECT id FROM alba_loan_application WHERE id = %s FOR UPDATE NOWAIT",
            (application.id,)
        )
        application.invalidate_recordset()

        if application.state not in ("approved", "employer_verification", "guarantor_confirmation"):
            raise UserError(_("Application %s is not in a disbursable state.") % application.application_number)

        if application.loan_id:
            raise UserError(_("Application %s has already been disbursed.") % application.application_number)

        # ── 1. Create alba.loan ───────────────────────────────────────────────
        loan_vals = {
            "application_id": application.id,
            "principal_amount": self.approved_amount,
            "interest_rate": self.interest_rate,
            "interest_method": self.interest_method,
            "tenure_months": self.tenure_months,
            "repayment_frequency": self.repayment_frequency,
            "disbursement_date": self.disbursement_date,
            "journal_id": self.journal_id.id,
            "payment_method_line_id": self.payment_method_line_id.id if self.payment_method_line_id else False,
            "state": "active",
            "notes": self.notes or "",
        }
        loan = self.env["alba.loan"].create(loan_vals)

        # ── 2. Post Disbursement Clearing Entry ──────────────────────────────
        # This creates: DR Loan Receivable, CR Clearing Account, CR Fee Income
        loan.action_post_disbursement_entry()

        # ── 3. Create Payment Voucher (Net Amount) ──────────────────────────
        total_fees = sum(application.fee_line_ids.mapped("calculated_amount"))
        net_disbursement = self.approved_amount - total_fees
        
        if net_disbursement > 0:
            self._ensure_payment_method_line()
            outstanding_account = (
                self.payment_method_line_id.payment_account_id
                or self.journal_id.default_account_id
            )
            if not outstanding_account:
                raise UserError(
                    _(
                        'Journal "%s" has no Outstanding Payments account configured. '
                        'Please set it under Accounting > Configuration > Journals > '
                        'Outgoing Payments tab before posting disbursements.'
                    ) % self.journal_id.name
                )
            if not application.loan_product_id.account_clearing_id:
                raise UserError(
                    _(
                        'Loan Product "%s" has no Loan Clearing account configured. '
                        'Please set the Loan Clearing Account before posting disbursements.'
                    ) % application.loan_product_id.name
                )

            move_vals = {
                "journal_id": self.journal_id.id,
                "date": self.disbursement_date,
                "ref": _("DISB/PAY/%s") % loan.loan_number,
                "move_type": "entry",
                "line_ids": [
                    (0, 0, {
                        "account_id": outstanding_account.id,
                        "name": _("Clear Outstanding Payments — %s") % loan.loan_number,
                        "partner_id": application.customer_id.partner_id.id,
                        "debit": net_disbursement,
                        "credit": 0.0,
                    }),
                    (0, 0, {
                        "account_id": application.loan_product_id.account_clearing_id.id,
                        "name": _("Salary Loan Clearing — %s") % loan.loan_number,
                        "partner_id": application.customer_id.partner_id.id,
                        "debit": 0.0,
                        "credit": net_disbursement,
                    }),
                ],
            }
            payment_move = self.env["account.move"].create(move_vals)
            payment_move.action_post()
            loan.message_post(body=_("Disbursement payment entry created: <a href='#' data-oe-model='account.move' data-oe-id='%s'>%s</a>") % (payment_move.id, payment_move.name))

        # ── 4. Create Vendor POs for Credit Life ────────────────────────────
        credit_life_fees = application.fee_line_ids.filtered(lambda f: f.is_credit_life and f.vendor_id)
        for fee in credit_life_fees:
            po_vals = {
                "partner_id": fee.vendor_id.id,
                "company_id": application.company_id.id,
                "currency_id": self.currency_id.id,
                "date_order": fields.Datetime.now(),
                "origin": loan.loan_number,
                "order_line": [(0, 0, {
                    "product_id": fee.fee_product_id.id,
                    "name": _("Credit Life Insurance for Loan %s") % loan.loan_number,
                    "product_qty": 1.0,
                    "price_unit": fee.calculated_amount,
                    "date_planned": fields.Datetime.now(),
                })],
            }
            po = self.env["purchase.order"].create(po_vals)
            # Optional: po.button_confirm() if automatic confirmation is desired
            loan.message_post(body=_("Vendor PO created for Credit Life: <a href='#' data-oe-model='purchase.order' data-oe-id='%s'>%s</a>") % (po.id, po.name))

        # ── 5. Generate Repayment Schedule ───────────────────────────────────
        if self.generate_schedule:
            loan.action_generate_schedule()

        # ── 6. Finalize Application ──────────────────────────────────────────
        application.write({
            "state": "disbursed",
            "approved_amount": self.approved_amount,
            "disbursed_date": fields.Datetime.now(),
            "disbursed_by": self.env.uid,
            "loan_id": loan.id,
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("Loan — %s") % loan.loan_number,
            "res_model": "alba.loan",
            "view_mode": "form",
            "res_id": loan.id,
            "target": "current",
        }
