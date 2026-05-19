# -*- coding: utf-8 -*-
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from markupsafe import Markup


class AlbaLoan(models.Model):
    _name = "alba.loan"
    _description = "Alba Capital Active Loan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "loan_number"
    _order = "disbursement_date desc, id desc"

    # ── Identification ────────────────────────────────────────────────────────
    loan_number = fields.Char(
        string="Loan Number",
        readonly=True,
        copy=False,
        index=True,
        default="New",
    )
    django_loan_id = fields.Integer(
        string="Django Loan ID",
        index=True,
        copy=False,
        help="Primary key of the corresponding Loan record in the Django portal.",
    )

    # ── Application link ──────────────────────────────────────────────────────
    application_id = fields.Many2one(
        "alba.loan.application",
        string="Loan Application",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )

    # ── Derived from application (stored for performance) ─────────────────────
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="application_id.customer_id",
        store=True,
        index=True,
        readonly=True,
    )
    loan_product_id = fields.Many2one(
        "alba.loan.product",
        string="Loan Product",
        related="application_id.loan_product_id",
        store=True,
        readonly=True,
    )
    sector_id = fields.Many2one(
        "alba.business.sector",
        string="Sector",
        related="customer_id.sector_id",
        store=True,
        readonly=True,
        index=True,
    )
    subsector_id = fields.Many2one(
        "alba.business.subsector",
        string="Subsector",
        related="customer_id.subsector_id",
        store=True,
        readonly=True,
        index=True,
    )
    referral_source = fields.Selection(
        related="customer_id.referral_source",
        string="Referral Source",
        store=True,
        readonly=True,
        index=True,
    )
    employer_id = fields.Many2one(
        "alba.employer",
        string="Employer",
        tracking=True,
        ondelete="restrict",
    )

    # ── Loan Terms ────────────────────────────────────────────────────────────
    principal_amount = fields.Monetary(
        string="Principal Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    interest_rate = fields.Float(
        string="Interest Rate (% p.m.)",
        digits=(5, 2),
        required=True,
        tracking=True,
    )
    interest_method = fields.Selection(
        selection=[
            ("flat_rate", "Flat Rate"),
            ("reducing_balance", "Reducing Balance"),
        ],
        string="Interest Method",
        required=True,
        default="reducing_balance",
        tracking=True,
    )
    tenure_months = fields.Integer(
        string="Tenure (Months)",
        required=True,
        tracking=True,
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
        tracking=True,
    )

    # ── Dates ─────────────────────────────────────────────────────────────────
    loan_date = fields.Date(
        string="Loan Date",
        default=fields.Date.context_today,
        tracking=True,
    )
    disbursement_date = fields.Date(
        string="Disbursement Date",
        required=True,
        tracking=True,
    )
    maturity_date = fields.Date(
        string="Maturity Date",
        compute="_compute_maturity_date",
        store=True,
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("active", "Active"),
            ("closed", "Closed / Fully Repaid"),
            ("npl", "Non-Performing"),
            ("written_off", "Written Off"),
        ],
        string="Loan Status",
        default="active",
        required=True,
        tracking=True,
        index=True,
    )

    # ── Onchange Methods ──────────────────────────────────────────────────────

    @api.onchange("customer_id")
    def _onchange_customer_id(self):
        if self.customer_id and self.customer_id.employer_id:
            self.employer_id = self.customer_id.employer_id

    def _log_professional_status_change(self, old_state, new_state):
        """Post a professional, formatted message to the chatter on status change."""
        state_labels = dict(self._fields['state'].selection)
        old_label = state_labels.get(old_state, old_state)
        new_label = state_labels.get(new_state, new_state)
        
        icon = "📈" if new_state == "active" else "ℹ️"
        if new_state == "closed": icon = "✅"
        if new_state == "npl": icon = "🔴"
        if new_state == "written_off": icon = "🗑️"
        
        body = (
            "<div class='o_alba_status_change'>"
            "<strong>%s Loan Status Changed</strong><br/>"
            "From: <span class='badge badge-secondary' style='color: #666;'>%s</span> "
            "To: <span class='badge badge-primary' style='background-color: #004a99; color: white; padding: 2px 6px; border-radius: 4px;'>%s</span><br/>"
            "Changed by: %s"
            "</div>"
        ) % (icon, old_label.upper(), new_label.upper(), self.env.user.name)
        
        self.message_post(body=body, subtype_xmlid="mail.mt_comment")

    def write(self, vals):
        if 'state' in vals:
            for rec in self:
                if rec.state != vals['state']:
                    rec._log_professional_status_change(rec.state, vals['state'])
        return super().write(vals)

    # ── Financial Summary ───────────────────────────────────────────────────────
    total_repayable = fields.Monetary(
        string="Total Repayable",
        compute="_compute_financial_totals",
        store=True,
        currency_field="currency_id",
        help="Principal + all scheduled interest and fees.",
    )
    net_disbursement_amount = fields.Monetary(
        string="Net Disbursed",
        currency_field="currency_id",
        compute="_compute_net_disbursement_amount",
        store=True
    )
    total_paid = fields.Monetary(
        string="Total Paid",
        compute="_compute_financial_totals",
        store=True,
        currency_field="currency_id",
    )
    outstanding_balance = fields.Monetary(
        string="Outstanding Balance",
        compute="_compute_financial_totals",
        store=True,
        currency_field="currency_id",
    )
    arrears_amount = fields.Monetary(
        string="Arrears Amount",
        compute="_compute_par",
        store=True,
        currency_field="currency_id",
        help="Sum of overdue but unpaid instalments.",
    )
    days_in_arrears = fields.Integer(
        string="Days in Arrears",
        compute="_compute_par",
        store=True,
        help="Number of days since the oldest overdue unpaid instalment.",
    )
    par_bucket = fields.Selection(
        selection=[
            ("current", "Current"),
            ("1_30", "1-30 Days"),
            ("31_60", "31-60 Days"),
            ("61_90", "61-90 Days"),
            ("91_180", "91-180 Days"),
            ("over_180", "Over 180 Days"),
        ],
        string="PAR Bucket",
        compute="_compute_par",
        store=True,
        tracking=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    repayment_schedule_ids = fields.One2many(
        "alba.repayment.schedule",
        "loan_id",
        string="Repayment Schedule",
    )
    repayment_ids = fields.One2many(
        "alba.loan.repayment",
        "loan_id",
        string="Repayment History",
    )
    # Multi-account disbursement splits (Req #2)
    disbursement_split_ids = fields.One2many(
        "alba.loan.disbursement.split",
        "loan_id",
        string="Disbursement Splits",
        help="Account splits for multi-account loan disbursement",
    )
    # Credit life insurance events (Req #7)
    credit_life_insurance_ids = fields.One2many(
        "alba.credit.life.insurance",
        "loan_id",
        string="Insurance Events",
        help="Credit life insurance claims against this loan",
    )
    # Note: journal entries are tracked via disbursement_move_id (Many2one below)

    # ── Accounting ────────────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        "account.journal",
        string="Disbursement Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        tracking=True,
        help="Bank or Cash journal used when disbursing this loan.",
    )

    # ── Currency / Company ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )

    # ── Misc ──────────────────────────────────────────────────────────────────
    notes = fields.Text(string="Notes")
    schedule_generated = fields.Boolean(
        string="Schedule Generated",
        default=False,
        readonly=True,
        copy=False,
    )
    disbursement_move_id = fields.Many2one(
        "account.move",
        string="Disbursement Journal Entry",
        readonly=True,
        copy=False,
    )
    provision_move_id = fields.Many2one(
        "account.move",
        string="Provision Journal Entry",
        readonly=True,
        copy=False,
    )

    repayment_count = fields.Integer(
        string="Payments",
        compute="_compute_repayment_count",
    )
    credit_life_insurance_count = fields.Integer(
        string="Insurance Events",
        compute="_compute_credit_life_insurance_count",
    )

    # ── UX Helpers ────────────────────────────────────────────────────────────
    repayment_progress = fields.Integer(
        string="Repayment Progress %",
        compute="_compute_ux_helpers",
    )
    next_payment_due_date = fields.Date(
        string="Next Payment Due Date",
        compute="_compute_ux_helpers",
    )
    next_payment_amount = fields.Monetary(
        string="Next Payment Amount",
        currency_field="currency_id",
        compute="_compute_ux_helpers",
    )
    days_until_due = fields.Integer(
        string="Days Until Due",
        compute="_compute_ux_helpers",
    )
    remaining_tenure = fields.Integer(
        string="Remaining Tenure (Months)",
        compute="_compute_remaining_tenure",
        store=True,
        help="Number of unpaid installments remaining",
    )
    installment_amount = fields.Monetary(
        string="Installment Amount (EMI)",
        currency_field="currency_id",
        compute="_compute_installment_amount",
        store=True,
        help="Equal Monthly Installment amount",
    )
    first_installment_date = fields.Date(
        string="First Installment Date",
        compute="_compute_report_fields",
        store=True,
    )
    last_installment_date = fields.Date(
        string="Last Installment Date",
        compute="_compute_report_fields",
        store=True,
    )
    outstanding_principal = fields.Monetary(
        string="Outstanding Principal",
        currency_field="currency_id",
        compute="_compute_report_fields",
        store=True,
    )
    outstanding_interest = fields.Monetary(
        string="Outstanding Interest",
        currency_field="currency_id",
        compute="_compute_report_fields",
        store=True,
    )
    outstanding_charges = fields.Monetary(
        string="Outstanding Charges",
        currency_field="currency_id",
        compute="_compute_report_fields",
        store=True,
    )
    prepayment_amount = fields.Monetary(
        string="Prepayments",
        currency_field="currency_id",
        compute="_compute_report_fields",
        store=True,
    )
    total_topup_amount = fields.Monetary(
        string="Top-Up Amount",
        currency_field="currency_id",
        compute="_compute_report_fields",
        store=True,
    )

    # ── Loan Modifications ──────────────────────────────────────────────────
    # Top-Up tracking
    topup_ids = fields.One2many(
        "alba.loan.topup",
        "loan_id",
        string="Top-Ups",
    )
    topup_count = fields.Integer(
        string="Top-Up Count",
        compute="_compute_modification_counts",
    )
    can_request_topup = fields.Boolean(
        string="Can Request Top-Up",
        compute="_compute_modification_counts",
    )

    # Partial Payoff tracking
    partial_payoff_ids = fields.One2many(
        "alba.loan.partial.payoff",
        "loan_id",
        string="Partial Payoffs",
    )
    payoff_count = fields.Integer(
        string="Payoff Count",
        compute="_compute_modification_counts",
    )

    # ── Guarantors ───────────────────────────────────────────────────────────
    guarantor_ids = fields.One2many(
        "alba.loan.guarantor",
        "loan_application_id",
        string="Guarantors",
        related="application_id.loan_guarantor_ids",
        readonly=True,
    )
    guarantor_count = fields.Integer(
        string="Guarantor Count",
        related="application_id.guarantor_count",
        readonly=True,
    )

    # =========================================================================
    # SQL Constraints
    # =========================================================================
    _loan_number_unique = models.Constraint(
        "UNIQUE(loan_number)",
        "A loan with this loan number already exists.",
    )
    _principal_positive = models.Constraint(
        "CHECK(principal_amount > 0)",
        "Principal amount must be greater than zero.",
    )

    # =========================================================================
    # Compute Methods
    # =========================================================================

    @api.depends("disbursement_date", "tenure_months")
    def _compute_maturity_date(self):
        for rec in self:
            if rec.disbursement_date and rec.tenure_months:
                d = rec.disbursement_date
                month = d.month + rec.tenure_months
                year = d.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                # Clamp day to last valid day of the target month
                import calendar

                last_day = calendar.monthrange(year, month)[1]
                rec.maturity_date = date(year, month, min(d.day, last_day))
            else:
                rec.maturity_date = False

    @api.depends(
        "principal_amount",
        "repayment_schedule_ids.total_due",
        "repayment_ids.state",
        "repayment_ids.amount_paid",
    )
    def _compute_financial_totals(self):
        for rec in self:
            schedule = rec.repayment_schedule_ids
            repayments = rec.repayment_ids.filtered(lambda r: r.state == "posted")
            rec.total_repayable = (
                sum(schedule.mapped("total_due")) or rec.principal_amount
            )
            rec.total_paid = sum(repayments.mapped("amount_paid"))
            rec.outstanding_balance = max(rec.total_repayable - rec.total_paid, 0.0)

    @api.depends("principal_amount", "application_id.fee_line_ids.calculated_amount")
    def _compute_net_disbursement_amount(self):
        for loan in self:
            if loan.application_id:
                total_fees = sum(loan.application_id.fee_line_ids.mapped("calculated_amount"))
                loan.net_disbursement_amount = loan.principal_amount - total_fees
            else:
                loan.net_disbursement_amount = loan.principal_amount

    @api.depends(
        "repayment_schedule_ids.status",
        "repayment_schedule_ids.balance_due",
        "repayment_schedule_ids.due_date",
    )
    def _compute_par(self):
        today = fields.Date.today()
        for rec in self:
            overdue = rec.repayment_schedule_ids.filtered(
                lambda s: s.due_date < today and s.balance_due > 0
            )
            if not overdue:
                rec.arrears_amount = 0.0
                rec.days_in_arrears = 0
                rec.par_bucket = "current"
                continue

            rec.arrears_amount = sum(overdue.mapped("balance_due"))
            oldest_due = min(overdue.mapped("due_date"))
            rec.days_in_arrears = (today - oldest_due).days

            d = rec.days_in_arrears
            if d <= 30:
                rec.par_bucket = "1_30"
            elif d <= 60:
                rec.par_bucket = "31_60"
            elif d <= 90:
                rec.par_bucket = "61_90"
            elif d <= 180:
                rec.par_bucket = "91_180"
            else:
                rec.par_bucket = "over_180"

    def _compute_repayment_count(self):
        for rec in self:
            rec.repayment_count = len(rec.repayment_ids)

    def _compute_credit_life_insurance_count(self):
        for rec in self:
            rec.credit_life_insurance_count = len(rec.credit_life_insurance_ids)

    def _compute_ux_helpers(self):
        today = fields.Date.today()
        for rec in self:
            # Repayment Progress
            if rec.total_repayable > 0:
                rec.repayment_progress = min(100, int((rec.total_paid / rec.total_repayable) * 100))
            else:
                rec.repayment_progress = 0
            
            # Next Payment Info
            unpaid_schedule = rec.repayment_schedule_ids.filtered(lambda s: s.status != "paid").sorted("due_date")
            if unpaid_schedule:
                next_item = unpaid_schedule[0]
                rec.next_payment_due_date = next_item.due_date
                rec.next_payment_amount = next_item.balance_due
                rec.days_until_due = (next_item.due_date - today).days
            else:
                rec.next_payment_due_date = False
                rec.next_payment_amount = 0.0
                rec.days_until_due = 0

    @api.depends("topup_ids", "topup_ids.state", "partial_payoff_ids", "state", "days_in_arrears")
    def _compute_modification_counts(self):
        for rec in self:
            # Count completed topups
            rec.topup_count = len(rec.topup_ids.filtered(lambda t: t.state == "disbursed"))
            
            # Count completed payoffs
            rec.payoff_count = len(rec.partial_payoff_ids.filtered(lambda p: p.state == "applied"))
            
            # Check if eligible for topup
            rec.can_request_topup = (
                rec.state == "active"
                and rec.days_in_arrears <= 90
                and not rec.topup_ids.filtered(lambda t: t.state in ["draft", "pending"])
            )

    @api.depends("repayment_schedule_ids", "repayment_schedule_ids.status")
    def _compute_remaining_tenure(self):
        for rec in self:
            unpaid = rec.repayment_schedule_ids.filtered(lambda s: s.status != "paid")
            rec.remaining_tenure = len(unpaid)

    @api.depends("repayment_schedule_ids", "repayment_schedule_ids.total_due")
    def _compute_installment_amount(self):
        for rec in self:
            # Get the installment amount from the first unpaid schedule line
            unpaid = rec.repayment_schedule_ids.filtered(lambda s: s.status != "paid")
            if unpaid:
                rec.installment_amount = unpaid[0].total_due
            elif rec.repayment_schedule_ids:
                # All paid - get from first paid
                rec.installment_amount = rec.repayment_schedule_ids[0].total_due
            else:
                rec.installment_amount = 0

    @api.depends(
        "principal_amount",
        "repayment_schedule_ids.due_date",
        "repayment_schedule_ids.principal_due",
        "repayment_schedule_ids.principal_paid",
        "repayment_schedule_ids.interest_due",
        "repayment_schedule_ids.interest_paid",
        "repayment_ids.state",
        "repayment_ids.fees_component",
        "repayment_ids.penalty_component",
        "partial_payoff_ids.state",
        "partial_payoff_ids.payoff_amount",
        "topup_ids.state",
        "topup_ids.topup_amount",
    )
    def _compute_report_fields(self):
        for rec in self:
            schedule = rec.repayment_schedule_ids.sorted("due_date")
            rec.first_installment_date = schedule[:1].due_date if schedule else False
            rec.last_installment_date = schedule[-1:].due_date if schedule else False

            rec.outstanding_principal = sum(
                max(line.principal_due - line.principal_paid, 0.0)
                for line in schedule
            )
            rec.outstanding_interest = sum(
                max(line.interest_due - line.interest_paid, 0.0)
                for line in schedule
            )

            posted_repayments = rec.repayment_ids.filtered(lambda r: r.state == "posted")
            paid_charges = sum(posted_repayments.mapped("fees_component")) + sum(
                posted_repayments.mapped("penalty_component")
            )
            product_fees = (
                rec.loan_product_id.calculate_total_fees(rec.principal_amount)
                if rec.loan_product_id
                else 0.0
            )
            extra_fees = 0.0
            rec.outstanding_charges = max(product_fees + extra_fees - paid_charges, 0.0)
            rec.prepayment_amount = sum(
                rec.partial_payoff_ids.filtered(lambda p: p.state == "applied").mapped("payoff_amount")
            )
            rec.total_topup_amount = sum(
                rec.topup_ids.filtered(lambda t: t.state == "disbursed").mapped("topup_amount")
            )

    # =========================================================================
    # ORM Overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("loan_number") or vals["loan_number"] == "New":
                vals["loan_number"] = seq.next_by_code("alba.loan.seq") or "New"
        return super().create(vals_list)

    # =========================================================================
    # Business Logic
    # =========================================================================

    def action_generate_schedule(self):
        """Generate the repayment schedule based on the loan product's method."""
        for rec in self:
            if rec.schedule_generated:
                raise UserError(
                    _(
                        "A repayment schedule has already been generated for loan %s. "
                        "Please delete the existing schedule before regenerating."
                    )
                    % rec.loan_number
                )
            if not rec.disbursement_date:
                raise UserError(
                    _("Please set a disbursement date before generating the schedule.")
                )

            product = rec.loan_product_id
            if not product:
                raise UserError(_("No loan product linked to this loan."))

            schedule_data = []
            if rec.interest_method == "flat_rate":
                monthly_interest = rec.principal_amount * (rec.interest_rate / 100)
                equal_principal = round(rec.principal_amount / rec.tenure_months, 2)
                balance = rec.principal_amount
                for i in range(rec.tenure_months):
                    principal = (
                        equal_principal
                        if i < rec.tenure_months - 1
                        else round(balance, 2)
                    )
                    schedule_data.append(
                        {
                            "installment_number": i + 1,
                            "opening_balance": round(balance, 2),
                            "principal_due": principal,
                            "interest_due": round(monthly_interest, 2),
                            "closing_balance": round(balance - principal, 2),
                        }
                    )
                    balance -= principal
            else:
                schedule_data = product.calculate_reducing_schedule(
                    rec.principal_amount, rec.tenure_months
                )

            # Build due dates
            schedule_vals = []
            for row in schedule_data:
                n = row["installment_number"]
                base = rec.disbursement_date
                import calendar

                month = base.month + n
                year = base.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                last_day = calendar.monthrange(year, month)[1]
                due = date(year, month, min(base.day, last_day))
                schedule_vals.append(
                    {
                        "loan_id": rec.id,
                        "installment_number": row["installment_number"],
                        "due_date": due,
                        "opening_balance": row["opening_balance"],
                        "principal_due": row["principal_due"],
                        "interest_due": row["interest_due"],
                        "closing_balance": row.get("closing_balance", 0.0),
                    }
                )

            # Use transaction context to ensure atomicity
            # If any operation fails, all changes are rolled back
            with self.env.cr.savepoint():
                self.env["alba.repayment.schedule"].create(schedule_vals)
                rec.write({"schedule_generated": True})
                rec.message_post(
                    body=Markup(_(
                        "Repayment schedule generated: <b>%d</b> instalments from <b>%s</b> to <b>%s</b>."
                    ))
                    % (
                        len(schedule_vals),
                        schedule_vals[0]["due_date"],
                        schedule_vals[-1]["due_date"],
                    )
                )
        return True

    def action_post_disbursement_entry(self):
        """
        Post disbursement accounting journal entry:
            DR  Loan Receivable      (Principal)
            CR  Loan Clearing        (Net Amount)
            CR  Fee Income           (Total Fees)
        """
        self.ensure_one()
        if self.disbursement_move_id:
            raise UserError(_("Disbursement entry already exists for loan %s.") % self.loan_number)

        product = self.loan_product_id
        if not product.account_loan_receivable_id or not product.account_clearing_id:
            raise UserError(_("Please configure Loan Receivable and Clearing accounts on product '%s'.") % product.name)

        application = self.application_id
        total_fees = sum(application.fee_line_ids.mapped("calculated_amount"))
        net_amount = self.principal_amount - total_fees

        move_vals = {
            "journal_id": self.journal_id.id,
            "date": self.disbursement_date,
            "ref": f"DISB/{self.loan_number}",
            "move_type": "entry",
            "line_ids": [
                # DR Loan Receivable (Full Principal)
                (0, 0, {
                    "account_id": product.account_loan_receivable_id.id,
                    "name": _("Loan Principal — %s") % self.loan_number,
                    "debit": self.principal_amount,
                    "credit": 0.0,
                    "partner_id": self.customer_id.partner_id.id,
                }),
                # CR Loan Clearing (Net Amount to be paid)
                (0, 0, {
                    "account_id": product.account_clearing_id.id,
                    "name": _("Loan Disbursement Clearing — %s") % self.loan_number,
                    "debit": 0.0,
                    "credit": net_amount,
                    "partner_id": self.customer_id.partner_id.id,
                }),
            ],
        }

        # Add Fee Income lines
        for fee in application.fee_line_ids:
            income_account = fee.fee_product_id.property_account_income_id or fee.fee_product_id.categ_id.property_account_income_categ_id
            if not income_account:
                income_account = product.account_fees_income_id
            
            if not income_account:
                raise UserError(_("No income account found for fee product '%s' or loan product.") % fee.fee_product_id.name)

            move_vals["line_ids"].append((0, 0, {
                "account_id": income_account.id,
                "name": _("Fee: %s — %s") % (fee.fee_product_id.name, self.loan_number),
                "debit": 0.0,
                "credit": fee.calculated_amount,
                "partner_id": self.customer_id.partner_id.id,
            }))

        move = self.env["account.move"].create(move_vals)
        move.action_post()
        self.write({"disbursement_move_id": move.id})
        self.message_post(
            body=_("Disbursement journal entry %s posted for KES %s.")
            % (move.name, f"{self.principal_amount:,.2f}")
        )
        
        # Trigger automatic provisioning
        self.action_post_provisioning_entry()
        
        return move

    def action_post_provisioning_entry(self):
        """
        Create a provisioning journal entry for potential loan losses:
            DR  Provision Expense
            CR  Loan Loss Provision (Asset Offset)
        """
        self.ensure_one()
        if self.provision_move_id:
            return False

        product = self.loan_product_id
        if not product.account_provision_id or not product.account_provision_expense_id:
            # Provisioning is optional; skip if not configured
            return False

        # Calculate provisioning amount based on product rate
        rate = product.provision_rate / 100.0 if product.provision_rate else 0.01
        provision_amount = self.principal_amount * rate

        move_vals = {
            "journal_id": self.journal_id.id,
            "date": self.disbursement_date,
            "ref": f"PROV/{self.loan_number}",
            "move_type": "entry",
            "line_ids": [
                # DR Provision Expense
                (0, 0, {
                    "account_id": product.account_provision_expense_id.id,
                    "name": _("Loan Loss Provision Expense — %s") % self.loan_number,
                    "debit": provision_amount,
                    "credit": 0.0,
                    "partner_id": self.customer_id.partner_id.id,
                }),
                # CR Provision Account (Asset Offset)
                (0, 0, {
                    "account_id": product.account_provision_id.id,
                    "name": _("Allowance for Credit Losses — %s") % self.loan_number,
                    "debit": 0.0,
                    "credit": provision_amount,
                    "partner_id": self.customer_id.partner_id.id,
                }),
            ],
        }

        move = self.env["account.move"].create(move_vals)
        move.action_post()
        self.write({"provision_move_id": move.id})
        self.message_post(
            body=_("Automatic provisioning journal entry %s posted for KES %s.")
            % (move.name, f"{provision_amount:,.2f}")
        )
        return move

    def action_mark_npl(self):
        self.ensure_one()
        self.write({"state": "npl"})
        self.message_post(body=Markup(_("Loan marked as <b>Non-Performing (NPL)</b>.")))

    def action_write_off(self):
        self.ensure_one()
        self.write({"state": "written_off"})
        self.message_post(body=Markup(_("Loan has been <b>Written Off</b>.")))

    def action_close(self):
        self.ensure_one()
        if self.outstanding_balance > 0.01:
            raise UserError(
                _("Cannot close loan %s — outstanding balance of %s remains.")
                % (self.loan_number, f"{self.outstanding_balance:,.2f}")
            )
        self.write({"state": "closed"})
        self.message_post(body=Markup(_("Loan marked as <b>Closed / Fully Repaid</b>.")))

    def action_view_schedule(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Repayment Schedule — %s") % self.loan_number,
            "res_model": "alba.repayment.schedule",
            "view_mode": "list",
            "domain": [("loan_id", "=", self.id)],
            "context": {"default_loan_id": self.id},
        }

    def action_view_repayments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Repayments — %s") % self.loan_number,
            "res_model": "alba.loan.repayment",
            "view_mode": "list,form",
            "domain": [("loan_id", "=", self.id)],
            "context": {"default_loan_id": self.id},
        }

    def action_view_credit_life_claims(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Credit Life Insurance — %s") % self.loan_number,
            "res_model": "alba.credit.life.insurance",
            "view_mode": "list,form",
            "domain": [("loan_id", "=", self.id)],
            "context": {"default_loan_id": self.id},
        }

    def action_view_topups(self):
        """View all top-ups for this loan"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Top-Ups — %s") % self.loan_number,
            "res_model": "alba.loan.topup",
            "view_mode": "list,form",
            "domain": [("loan_id", "=", self.id)],
            "context": {"default_loan_id": self.id},
        }

    def action_request_topup(self):
        """Open wizard to request top-up"""
        self.ensure_one()
        if not self.can_request_topup:
            raise UserError(_("This loan is not eligible for top-up."))
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Request Top-Up"),
            "res_model": "alba.loan.topup.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_id": self.id,
                "active_model": "alba.loan",
            },
        }

    def action_calculate_partial_payoff(self):
        """Open wizard to calculate partial payoff"""
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("Partial payoff is only available for active loans."))
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Calculate Partial Payoff"),
            "res_model": "alba.loan.partial.payoff.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_id": self.id,
                "active_model": "alba.loan",
            },
        }

    def action_view_partial_payoffs(self):
        """View all partial payoffs for this loan"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Partial Payoffs — %s") % self.loan_number,
            "res_model": "alba.loan.partial.payoff",
            "view_mode": "list,form",
            "domain": [("loan_id", "=", self.id)],
        }

    def action_view_guarantors(self):
        """View guarantors for this loan"""
        self.ensure_one()
        if not self.application_id:
            raise UserError(_("No loan application linked."))
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Guarantors — %s") % self.loan_number,
            "res_model": "alba.loan.guarantor",
            "view_mode": "list,form",
            "domain": [("loan_application_id", "=", self.application_id.id)],
        }

    # =========================================================================
    # Scheduled action (cron) — update PAR buckets daily
    # =========================================================================

    @api.model
    def action_update_par_buckets(self):
        """Called by daily cron to refresh PAR data on all active loans."""
        active_loans = self.search([("state", "=", "active")])
        active_loans._compute_par()
        # Auto-flag NPL for loans > 90 days in arrears
        for loan in active_loans:
            if loan.days_in_arrears > 90 and loan.state == "active":
                loan.action_mark_npl()

    # =========================================================================
    # Scheduled action (cron) — NPL monitor
    # =========================================================================

    @api.model
    def cron_flag_npl_loans(self):
        """
        Daily cron: move any active loan with days_in_arrears >= 90 to
        state='npl' and fire a Django webhook so the portal is updated.

        Loans already in 'npl', 'closed', or 'written_off' are skipped.
        """
        _logger = __import__("logging").getLogger(__name__)
        active_loans = self.search([("state", "=", "active")])
        active_loans._compute_par()

        npl_threshold = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("alba.loans.npl_threshold_days", "90")
        )

        newly_npl = self.browse()
        for loan in active_loans:
            if loan.days_in_arrears >= npl_threshold:
                loan.write({"state": "npl"})
                loan.message_post(
                    body=Markup(_(
                        "Loan automatically flagged as <b>Non-Performing</b> "
                        "by the daily NPL monitor cron — "
                        "<b>%d days</b> in arrears (threshold: %d)."
                    ))
                    % (loan.days_in_arrears, npl_threshold)
                )
                newly_npl |= loan

        _logger.info("cron_flag_npl_loans: flagged %d loan(s) as NPL.", len(newly_npl))

        # Fire webhooks for newly flagged loans
        if newly_npl:
            self._fire_loan_status_webhooks(newly_npl, "loan.npl_flagged")

    # =========================================================================
    # Scheduled action (cron) — overdue payment alerts
    # =========================================================================

    @api.model
    def cron_send_overdue_alerts(self):
        """
        Daily cron: post chatter messages on loans that have instalments
        overdue by exactly 1, 3, 7, or 14 days, and log a sync event so
        the Django portal can notify the customer via email / SMS.

        Only active and NPL loans are checked.
        """
        import logging as _logging
        from datetime import timedelta

        _logger = _logging.getLogger(__name__)
        today = fields.Date.today()
        alert_days = [1, 3, 7, 14, 30]

        loans_alerted = 0
        for days_overdue in alert_days:
            target_date = today - timedelta(days=days_overdue)
            overdue_schedules = self.env["alba.repayment.schedule"].search(
                [
                    ("due_date", "=", target_date),
                    ("balance_due", ">", 0),
                    ("loan_id.state", "in", ("active", "npl")),
                ]
            )
            for schedule in overdue_schedules:
                loan = schedule.loan_id
                loan.message_post(
                    body=Markup(_(
                        "Overdue alert: instalment #<b>%d</b> "
                        "(KES <b>%.2f</b>) was due on <b>%s</b> "
                        "— now <b>%d day(s)</b> overdue."
                    ))
                    % (
                        schedule.installment_number,
                        schedule.balance_due,
                        schedule.due_date,
                        days_overdue,
                    )
                )
                loans_alerted += 1

                # Push overdue event to Django
                self._fire_loan_status_webhooks(
                    loan,
                    "loan.instalment_overdue",
                    extra={
                        "days_overdue": days_overdue,
                        "instalment_number": schedule.installment_number,
                        "balance_due": float(schedule.balance_due),
                        "due_date": str(schedule.due_date),
                    },
                )

        _logger.info(
            "cron_send_overdue_alerts: sent %d overdue alert(s).", loans_alerted
        )

    # =========================================================================
    # Scheduled action (cron) — maturity reminders
    # =========================================================================

    @api.model
    def cron_send_maturity_reminders(self):
        """
        Weekly cron: notify officers (and push to Django) for loans
        maturing within the next 30 days so customers can be contacted
        about final repayment or renewal.
        """
        import logging as _logging
        from datetime import timedelta

        _logger = _logging.getLogger(__name__)
        today = fields.Date.today()
        window_end = today + timedelta(days=30)

        maturing = self.search(
            [
                ("state", "=", "active"),
                ("maturity_date", ">=", today),
                ("maturity_date", "<=", window_end),
                ("outstanding_balance", ">", 0),
            ]
        )
        for loan in maturing:
            days_left = (loan.maturity_date - today).days
            loan.message_post(
                body=Markup(_(
                    "Maturity reminder: loan matures on <b>%s</b> "
                    "(<b>%d day(s)</b> remaining).  "
                    "Outstanding balance: <b>KES %.2f</b>."
                ))
                % (loan.maturity_date, days_left, loan.outstanding_balance)
            )

        _logger.info(
            "cron_send_maturity_reminders: %d loan(s) approaching maturity.",
            len(maturing),
        )
        if maturing:
            self._fire_loan_status_webhooks(maturing, "loan.maturing_soon")

    # =========================================================================
    # Scheduled action (cron) — auto-close fully repaid loans
    # =========================================================================

    @api.model
    def cron_close_repaid_loans(self):
        """
        Daily cron: close any active or NPL loan whose outstanding_balance
        has reached zero (i.e. the last repayment has been posted and all
        schedule entries are fully settled).
        """
        import logging as _logging

        _logger = _logging.getLogger(__name__)
        candidates = self.search([("state", "in", ("active", "npl"))])
        # Force recompute so we use fresh totals
        candidates._compute_financial_totals()

        closed = self.browse()
        for loan in candidates:
            if loan.outstanding_balance <= 0.01:  # 1-cent tolerance
                loan.write({"state": "closed"})
                loan.message_post(
                    body=Markup(_("Loan automatically <b>closed</b> — fully repaid."))
                )
                closed |= loan

        _logger.info("cron_close_repaid_loans: closed %d loan(s).", len(closed))
        if closed:
            self._fire_loan_status_webhooks(closed, "loan.closed")

    # =========================================================================
    # Scheduled action (cron) — push portfolio stats to Django
    # =========================================================================

    @api.model
    def cron_push_portfolio_stats(self):
        """
        Every-6-hours cron: compute aggregate portfolio metrics and push
        them to the Django portal via a webhook so dashboards stay current.

        Metrics pushed:
          • total_active_loans
          • total_disbursed (sum of principal_amount on active/npl loans)
          • total_outstanding (sum of outstanding_balance)
          • total_arrears
          • par_30  (outstanding balance of loans 1-30 days in arrears)
          • par_90  (outstanding balance of loans >90 days in arrears)
          • npl_count
        """
        import logging as _logging

        _logger = _logging.getLogger(__name__)

        active = self.search([("state", "in", ("active", "npl"))])
        if not active:
            return

        npl = active.filtered(lambda l: l.state == "npl")
        par_30 = active.filtered(lambda l: l.par_bucket in ("1_30",))
        par_90 = active.filtered(
            lambda l: l.par_bucket in ("61_90", "91_180", "over_180")
        )

        stats = {
            "total_active_loans": len(active.filtered(lambda l: l.state == "active")),
            "total_disbursed": float(sum(active.mapped("principal_amount"))),
            "total_outstanding": float(sum(active.mapped("outstanding_balance"))),
            "total_arrears": float(sum(active.mapped("arrears_amount"))),
            "par_30_balance": float(sum(par_30.mapped("outstanding_balance"))),
            "par_90_balance": float(sum(par_90.mapped("outstanding_balance"))),
            "npl_count": len(npl),
            "npl_balance": float(sum(npl.mapped("outstanding_balance"))),
        }

        api_key = (
            self.env["alba.api.key"].sudo().search([("is_active", "=", True)], limit=1)
        )
        if api_key:
            api_key.send_webhook("portfolio.stats_updated", stats)
            _logger.info("cron_push_portfolio_stats: stats pushed to Django.")
        else:
            _logger.warning(
                "cron_push_portfolio_stats: no active API key found — skipping."
            )

    # =========================================================================
    # Private webhook helper
    # =========================================================================

    def _fire_loan_status_webhooks(self, loans, event_type, extra=None):
        """
        Fire a webhook for each loan in *loans* with the given *event_type*.

        Args:
            loans:      alba.loan recordset.
            event_type: Dot-separated event string, e.g. 'loan.npl_flagged'.
            extra:      Optional dict of extra fields merged into the payload.
        """
        api_key = (
            self.env["alba.api.key"].sudo().search([("is_active", "=", True)], limit=1)
        )
        if not api_key:
            return

        # Support both single records and recordsets
        loan_list = loans if hasattr(loans, "__iter__") else [loans]
        for loan in loan_list:
            payload = {
                "odoo_loan_id": loan.id,
                "loan_number": loan.loan_number or "",
                "django_loan_id": loan.django_loan_id or 0,
                "state": loan.state,
                "outstanding_balance": float(loan.outstanding_balance),
                "days_in_arrears": loan.days_in_arrears,
                "par_bucket": loan.par_bucket or "",
            }
            if extra:
                payload.update(extra)
            api_key.send_webhook(event_type, payload)

    @api.model
    def _check_company(self, company_id):
        """Ensure company consistency for multi-company setup"""
        if company_id:
            self.company_id = company_id
    
    def action_sync_loan_currency_to_accounting(self):
        """Sync loan currency configuration with accounting using native Odoo 19 accounting"""
        for loan in self:
            if not loan.currency_id:
                raise UserError(_("Loan must have a currency configured"))
            
            if loan.currency_id == loan.company_id.currency_id:
                loan.message_post(body=_("Loan currency matches company currency - no sync needed"))
                continue
            
            # Create currency difference journal entry if needed
            if loan.state == 'disbursed' and loan.disbursement_date:
                # Calculate currency difference at current rate
                company_currency = loan.company_id.currency_id
                loan_currency = loan.currency_id
                
                # Get currency rate
                rate = company_currency._get_conversion_rate(loan_currency, company_currency, loan.disbursement_date)
                
                # Create journal entry for currency valuation
                move_vals = {
                    'journal_id': loan.company_id.currency_exchange_journal_id.id if loan.company_id.currency_exchange_journal_id else False,
                    'date': fields.Date.context_today(self),
                    'ref': f"Currency Sync/{loan.loan_number}",
                    'currency_id': loan_currency.id,
                    'narration': _("Currency sync for loan %s") % loan.loan_number,
                    'line_ids': [
                        (0, 0, {
                            'account_id': loan.company_id.currency_exchange_journal_id.default_account_id.id if loan.company_id.currency_exchange_journal_id and loan.company_id.currency_exchange_journal_id.default_account_id else False,
                            'name': _("Currency difference - %s") % loan.loan_number,
                            'debit': 0.0,
                            'credit': 0.0,
                            'amount_currency': 0.0,
                            'currency_id': loan_currency.id,
                        }),
                    ],
                }
                
                if move_vals['journal_id'] and move_vals['line_ids'][0][2]['account_id']:
                    self.env['account.move'].create(move_vals)
                    loan.message_post(body=_("Currency sync completed - journal entry created"))
                else:
                    loan.message_post(body=_("Currency sync skipped - no currency exchange journal configured"))
            else:
                loan.message_post(body=_("Currency sync skipped - loan not yet disbursed"))
    
    def action_create_loan_accounting_move(self):
        """Create accounting move for loan disbursement with currency integration"""
        for loan in self:
            if loan.state not in ('active', 'npl'):
                raise UserError(_("Only active/disbursed loans can create accounting moves"))
            
            if not loan.journal_id:
                raise UserError(_("Loan must have a journal configured"))
            
            # Get loan product for account configuration
            product = loan.loan_product_id
            if not product:
                raise UserError(_("Loan must have a loan product configured"))
            
            if not product.account_loan_receivable_id:
                raise UserError(_("Please configure the Loan Receivable account on product '%s'.") % product.name)
            
            company_currency = loan.company_id.currency_id
            loan_currency = loan.currency_id
            
            move_vals = {
                'journal_id': loan.journal_id.id,
                'date': loan.disbursement_date or fields.Date.context_today(self),
                'ref': f"LOAN/{loan.loan_number}",
                'currency_id': loan_currency.id,
                'narration': _("Loan disbursement — %s — %s") % (loan.loan_number, loan.customer_id.display_name),
                'line_ids': [
                    # DR Loan Receivable
                    (0, 0, {
                        'account_id': product.account_loan_receivable_id.id,
                        'name': _("Loan disbursement — %s") % loan.loan_number,
                        'debit': loan.principal_amount if loan_currency == company_currency else 0.0,
                        'credit': 0.0,
                        'amount_currency': loan.principal_amount,
                        'currency_id': loan_currency.id,
                        'partner_id': loan.customer_id.partner_id.id,
                    }),
                    # CR Bank / Cash
                    (0, 0, {
                        'account_id': loan.journal_id.default_account_id.id if loan.journal_id.default_account_id else False,
                        'name': _("Disbursement — %s") % loan.loan_number,
                        'debit': 0.0,
                        'credit': loan.principal_amount if loan_currency == company_currency else 0.0,
                        'amount_currency': -loan.principal_amount,
                        'currency_id': loan_currency.id,
                        'partner_id': loan.customer_id.partner_id.id,
                    }),
                ],
            }
            
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            loan.message_post(body=_("Accounting move created: %s") % move.name)
            return {
                'type': 'ir.actions.act_window',
                'name': _('Accounting Move'),
                'res_model': 'account.move',
                'res_id': move.id,
                'view_mode': 'form',
            }
