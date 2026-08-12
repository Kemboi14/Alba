# -*- coding: utf-8 -*-
import logging
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from markupsafe import Markup

_logger = logging.getLogger(__name__)


class AlbaLoan(models.Model):
    _name = "alba.loan"
    _description = "Alba Capital Active Loan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "loan_number"
    _order = "disbursement_date desc, id desc"

    # ── Identification ────────────────────────────────────────────────────────
    loan_number = fields.Char(
        string="Loan Number",
        readonly=False,
        copy=False,
        store=True,
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
        index=True,
    )

    # ── Derived from application (stored for performance) ─────────────────────
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="application_id.customer_id",
        store=True,
        index=True,
        readonly=False,
        inverse="_inverse_noop",
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
        ondelete="restrict",
    )

    # ── Loan Terms ────────────────────────────────────────────────────────────
    principal_amount = fields.Monetary(
        string="Principal Amount",
        currency_field="currency_id",
        required=True,
    )
    interest_rate = fields.Float(
        string="Interest Rate (% p.m.)",
        digits=(5, 2),
        required=True,
    )
    interest_method = fields.Selection(
        selection=[
            ("flat_rate", "Flat Rate"),
            ("reducing_balance", "Reducing Balance"),
        ],
        string="Interest Method",
        required=True,
        default="reducing_balance",
    )
    tenure_months = fields.Integer(
        string="Tenure (Months)",
        required=True,
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
    )

    # ── Dates ─────────────────────────────────────────────────────────────────
    loan_date = fields.Date(
        string="Loan Date",
        required=True,
        default=fields.Date.context_today,
    )
    disbursement_date = fields.Date(
        string="Disbursement Date",
        required=True,
    )
    maturity_date = fields.Date(
        string="Maturity Date",
        compute="_compute_maturity_date",
        store=True,
        inverse="_inverse_noop",
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("normal", "Normal"),
            ("watch", "Watch (1-30 days)"),
            ("substandard", "Substandard (31-60 days)"),
            ("doubtful", "Doubtful (61-90 days)"),
            ("loss", "Loss (>90 days)"),
            ("closed", "Closed / Fully Repaid"),
            ("written_off", "Written Off"),
        ],
        string="Loan Status",
        compute="_compute_state",
        inverse="_inverse_state",
        store=True,
        required=True,
        index=True,
    )
    provision_rate = fields.Float(
        string="Provision Rate (%)",
        compute="_compute_state",
        inverse="_inverse_noop",
        store=True,
    )
    provision_amount = fields.Monetary(
        string="Provision Amount",
        compute="_compute_state",
        inverse="_inverse_noop",
        store=True,
        currency_field="currency_id",
    )
    @api.depends("days_in_arrears", "outstanding_balance", "loan_product_id.provision_rate")
    def _compute_state(self):
        for rec in self:
            if rec.state in ("closed", "written_off"):
                rec.provision_rate = 0.0
                rec.provision_amount = 0.0
                continue
            
            if rec.outstanding_balance <= 0.01 and rec.disbursement_move_id and rec.total_paid > 0:
                rec.state = "closed"
                rec.provision_rate = 0.0
                rec.provision_amount = 0.0
                continue

            d = rec.days_in_arrears
            if d <= 0:
                rec.state = "normal"
                rec.provision_rate = rec.loan_product_id.provision_rate if (rec.loan_product_id and rec.loan_product_id.provision_rate) else 1.0
            elif d <= 30:
                rec.state = "watch"
                rec.provision_rate = 5.0
            elif d <= 60:
                rec.state = "substandard"
                rec.provision_rate = 25.0
            elif d <= 90:
                rec.state = "doubtful"
                rec.provision_rate = 75.0
            else:
                rec.state = "loss"
                rec.provision_rate = 100.0
            
            rec.provision_amount = rec.outstanding_balance * (rec.provision_rate / 100.0)

    def _inverse_state(self):
        """Allow writing to state during import with label normalization."""
        for rec in self:
            if not rec.state:
                continue
            
            # Normalize common labels to technical keys
            val = rec.state.lower().strip()
            mapping = {
                "normal": "normal",
                "active": "normal",
                "watch": "watch",
                "substandard": "substandard",
                "doubtful": "doubtful",
                "loss": "loss",
                "closed": "closed",
                "written off": "written_off",
                "written-off": "written_off",
            }
            
            for key, target in mapping.items():
                if key in val:
                    rec.state = target
                    break

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
        
        icon = "📈" if new_state == "normal" else "ℹ️"
        if new_state == "closed": icon = "✅"
        if new_state == "loss": icon = "🔴"
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
        inverse="_inverse_total_repayable",
        store=True,
        currency_field="currency_id",
        help="Principal + all scheduled interest.",
        # IMPORT-EXPORT FIX
    )
    net_disbursement_amount = fields.Monetary(
        string="Net Disbursed",
        currency_field="currency_id",
        compute="_compute_net_disbursement_amount",
        inverse="_inverse_net_disbursement_amount",
        store=True,
        # IMPORT-EXPORT FIX
    )
    total_paid = fields.Monetary(
        string="Total Paid",
        compute="_compute_financial_totals",
        inverse="_inverse_total_paid",
        store=True,
        currency_field="currency_id",
        # IMPORT-EXPORT FIX
    )
    outstanding_balance = fields.Monetary(
        string="Outstanding Balance",
        compute="_compute_financial_totals",
        inverse="_inverse_outstanding_balance",
        store=True,
        currency_field="currency_id",
        # IMPORT-EXPORT FIX
    )
    arrears_amount = fields.Monetary(
        string="Arrears Amount",
        compute="_compute_par",
        inverse="_inverse_arrears_amount",
        store=True,
        currency_field="currency_id",
        help="Sum of overdue but unpaid instalments.",
        # IMPORT-EXPORT FIX
    )
    days_in_arrears = fields.Integer(
        string="Days in Arrears",
        compute="_compute_par",
        inverse="_inverse_days_in_arrears",
        store=True,
        help="Number of days since the oldest overdue unpaid instalment.",
        # IMPORT-EXPORT FIX
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
        inverse="_inverse_par_bucket",
        store=True,
    )
    days_past_maturity = fields.Integer(
        string="Days Past Maturity",
        compute="_compute_days_past_maturity",
        store=True,
        help="Number of days elapsed past the loan maturity date for unclosed loans.",
    )
    is_write_off_candidate = fields.Boolean(
        string="Write-Off Candidate",
        compute="_compute_is_write_off_candidate",
        search="_search_is_write_off_candidate",
        store=True,
        help="Flagged when loan is in Loss status or past maturity beyond the product's write-off grace period.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    repayment_schedule_ids = fields.One2many(
        "alba.repayment.schedule",
        "loan_id",
        string="Repayment Schedule",
    )
    current_repayment_schedule_ids = fields.One2many(
        "alba.repayment.schedule",
        "loan_id",
        string="Current Repayment Schedule",
        compute="_compute_current_repayment_schedule",
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
        string="Insurance Claim Details",
        help="Credit life insurance claims against this loan",
    )
    # Note: journal entries are tracked via disbursement_move_id (Many2one below)

    # ── Accounting ────────────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        "account.journal",
        string="Disbursement Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Bank or Cash journal used when disbursing this loan.",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Disbursement Payment Method",
        domain="[('payment_type', '=', 'outbound'), ('journal_id', '=', journal_id)]",
        help="Specific outbound payment method for the disbursement journal.",
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
    installments_paid_late = fields.Integer(
        string="Installments Paid Late",
        compute="_compute_repayment_count",
        help="Number of installments that were paid after their due date but are now fully paid.",
    )

    # ── UX Helpers ────────────────────────────────────────────────────────────

    repayment_progress = fields.Integer(
        string="Repayment Progress %",
        compute="_compute_ux_helpers",
        store=True,
        inverse="_inverse_noop",
    )

    def _inverse_noop(self):
        pass

    def _get_default_list_export_fields(self):
        fields = super()._get_default_list_export_fields()
        return [f for f in fields
                if f not in ('create_date', 'write_date',
                            '__last_update', 'display_name')]

    def name_get(self):
        return [
            (r.id, r.loan_number or str(r.id))
            for r in self
        ]

    @api.model
    def _name_search(self, name="", domain=None,
                     operator="ilike", limit=100, order=None):
        domain = list(domain or [])
        if name:
            domain = ["|",
                ("loan_number", "=", name),
                ("loan_number", operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)
    next_payment_due_date = fields.Date(
        string="Next Payment Due Date",
        compute="_compute_ux_helpers",
        store=True,
        inverse="_inverse_noop",
    )
    next_payment_amount = fields.Monetary(
        string="Next Payment Amount",
        currency_field="currency_id",
        compute="_compute_next_payment_amount",
    )
    days_until_due = fields.Integer(
        string="Days Until Due",
        compute="_compute_next_payment_amount",
    )
    remaining_tenure = fields.Integer(
        string="Remaining Tenure (Months)",
        compute="_compute_remaining_tenure",
        inverse="_inverse_remaining_tenure",
        store=True,
        help="Number of unpaid installments remaining",
        # IMPORT-EXPORT FIX
    )
    installment_amount = fields.Monetary(
        string="Installment Amount (EMI)",
        currency_field="currency_id",
        compute="_compute_installment_amount",
        inverse="_inverse_installment_amount",
        store=True,
        help="Equal Monthly Installment amount",
        # IMPORT-EXPORT FIX
    )
    first_installment_date = fields.Date(
        string="First Installment Date",
        compute="_compute_report_fields",
        inverse="_inverse_first_installment_date",
        store=True,
        compute_sudo=True,
        # IMPORT-EXPORT FIX
    )
    last_installment_date = fields.Date(
        string="Last Installment Date",
        compute="_compute_report_fields",
        inverse="_inverse_last_installment_date",
        store=True,
        compute_sudo=True,
        # IMPORT-EXPORT FIX
    )
    outstanding_principal = fields.Monetary(
        string="Outstanding Principal",
        currency_field="currency_id",
        compute="_compute_report_fields",
        inverse="_inverse_outstanding_principal",
        store=True,
        compute_sudo=True,
        # IMPORT-EXPORT FIX
    )
    outstanding_interest = fields.Monetary(
        string="Outstanding Interest",
        currency_field="currency_id",
        compute="_compute_report_fields",
        inverse="_inverse_outstanding_interest",
        store=True,
        compute_sudo=True,
        # IMPORT-EXPORT FIX
    )
    total_interest = fields.Monetary(
        string="Total Interest",
        currency_field="currency_id",
        compute="_compute_report_fields",
        inverse="_inverse_total_interest",
        store=True,
        compute_sudo=True,
        # IMPORT-EXPORT FIX
    )
    accrued_interest = fields.Monetary(
        string="Accrued Interest",
        currency_field="currency_id",
        compute="_compute_accrued_interest",
        compute_sudo=True,
    )
    is_accrual_pending = fields.Boolean(
        string="Interest Accrual Pending",
        compute="_compute_is_accrual_pending",
        store=False,
        help="True when no posted interest accrual exists for the current month.",
    )
    interest_amount = fields.Monetary(
        string="Interest Amount",
        compute="_compute_report_fields",
        inverse="_inverse_interest_amount",
        store=True,
        compute_sudo=True,
        help="Total interest amount scheduled for this loan.",
        # IMPORT-EXPORT FIX
    )
    outstanding_charges = fields.Monetary(
        string="Outstanding Charges",
        currency_field="currency_id",
        compute="_compute_report_fields",
        inverse="_inverse_outstanding_charges",
        store=True,
        compute_sudo=True,
        # IMPORT-EXPORT FIX
    )
    prepayment_amount = fields.Monetary(
        string="Prepayments",
        currency_field="currency_id",
        compute="_compute_report_fields",
        inverse="_inverse_prepayment_amount",
        store=True,
        compute_sudo=True,
        # IMPORT-EXPORT FIX
    )
    total_topup_amount = fields.Monetary(
        string="Top-Up Amount",
        currency_field="currency_id",
        compute="_compute_report_fields",
        inverse="_inverse_total_topup_amount",
        store=True,
        compute_sudo=True,
        # IMPORT-EXPORT FIX
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
        "state",
        "principal_amount",
        "repayment_schedule_ids.total_due",
        "repayment_ids.state",
        "repayment_ids.amount_paid",
        "fee_ids.amount",
        "fee_ids.is_posted",
    )
    def _compute_financial_totals(self):
        for rec in self:
            if rec.state == "written_off":
                rec.total_repayable = 0.0
                rec.total_paid = 0.0
                rec.outstanding_balance = 0.0
                continue
            schedule = rec.current_repayment_schedule_ids or rec.repayment_schedule_ids
            repayments = rec.repayment_ids.filtered(lambda r: r.state == "posted")
            # Posted ad-hoc fees (restructure fee, etc.) hit the loan
            # receivable account in the GL and must also count toward what
            # the customer still owes — otherwise action_post() on
            # alba.loan.fee posts real accounting entries that this
            # tracked balance never reflects.
            posted_fees = sum(
                rec.fee_ids.filtered(lambda f: f.is_posted).mapped("amount")
            )
            rec.total_repayable = (
                sum(schedule.mapped("total_due")) or rec.principal_amount
            ) + posted_fees
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
        # Second dependency path: posting a repayment must also invalidate PAR
        # so the loan state is refreshed even if the schedule-line stored fields
        # (balance_due / status) have not yet been recomputed by the ORM.
        "repayment_ids.state",
        "repayment_ids.amount_paid",
    )
    def _compute_par(self):
        """
        PAR (Portfolio at Risk) calculation - CORRECTLY ignores fully paid installments.
        
        Overdue logic: Only counts installments that are BOTH past due AND have outstanding balance.
        This ensures that late payments that are now fully paid don't count as current arrears.
        """
        today = fields.Date.today()
        for rec in self:
            if rec.state in ("written_off", "closed"):
                # Mirror _compute_financial_totals' written_off short-circuit:
                # a written-off/closed loan must not keep showing stale
                # arrears from schedule lines that were never settled on the
                # schedule itself (only credited via the write-off GL entry).
                rec.arrears_amount = 0.0
                rec.days_in_arrears = 0
                rec.par_bucket = "current"
                continue
            schedule = rec.current_repayment_schedule_ids or rec.repayment_schedule_ids
            # CORRECT: Only count as overdue if due date is strictly in the past (< today) AND balance is outstanding
            # (1-cent tolerance, matching every other balance-vs-zero comparison in this file)
            overdue = schedule.filtered(lambda s: s.due_date and s.due_date < today and s.balance_due > 0.01)
            if not overdue:
                rec.arrears_amount = 0.0
                rec.days_in_arrears = 0
                rec.par_bucket = "current"
                continue

            rec.arrears_amount = sum(overdue.mapped("balance_due"))
            oldest_due = min(overdue.mapped("due_date"))
            days = (today - oldest_due).days
            rec.days_in_arrears = max(0, days)

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

    @api.depends("maturity_date", "outstanding_balance", "state")
    def _compute_days_past_maturity(self):
        today = fields.Date.today()
        for rec in self:
            if rec.maturity_date and rec.state not in ("closed", "written_off") and rec.outstanding_balance > 0.01:
                if today > rec.maturity_date:
                    rec.days_past_maturity = (today - rec.maturity_date).days
                else:
                    rec.days_past_maturity = 0
            else:
                rec.days_past_maturity = 0

    @api.depends("state", "days_in_arrears", "days_past_maturity", "loan_product_id.write_off_grace_days")
    def _compute_is_write_off_candidate(self):
        for rec in self:
            if rec.state in ("closed", "written_off"):
                rec.is_write_off_candidate = False
                continue
            grace = rec.loan_product_id.write_off_grace_days if (rec.loan_product_id and rec.loan_product_id.write_off_grace_days) else 180
            if rec.state == "loss" and rec.days_in_arrears >= grace:
                rec.is_write_off_candidate = True
            elif rec.days_past_maturity >= grace:
                rec.is_write_off_candidate = True
            else:
                rec.is_write_off_candidate = False

    def _search_is_write_off_candidate(self, operator, value):
        loans = self.search([
            ("state", "in", ["substandard", "doubtful", "loss"]),
            ("outstanding_balance", ">", 0.01)
        ])
        candidate_ids = loans.filtered(lambda l: l.is_write_off_candidate).ids
        if (operator in ("=", "==") and value) or (operator == "!=" and not value):
            return [("id", "in", candidate_ids)]
        else:
            return [("id", "not in", candidate_ids)]

    @api.depends("repayment_ids", "repayment_schedule_ids.paid_late")
    def _compute_repayment_count(self):
        for rec in self:
            rec.repayment_count = len(rec.repayment_ids)
            schedule = rec.current_repayment_schedule_ids or rec.repayment_schedule_ids
            rec.installments_paid_late = len(schedule.filtered(lambda s: s.paid_late))

    def _compute_credit_life_insurance_count(self):
        for rec in self:
            rec.credit_life_insurance_count = len(rec.credit_life_insurance_ids)

    @api.depends("total_paid", "total_repayable", "repayment_schedule_ids.status", "repayment_schedule_ids.due_date")
    def _compute_ux_helpers(self):
        for rec in self:
            # Repayment Progress
            if rec.total_repayable > 0:
                rec.repayment_progress = min(100, int((rec.total_paid / rec.total_repayable) * 100))
            else:
                rec.repayment_progress = 0

            # Next Payment Due Date
            schedule = rec.current_repayment_schedule_ids or rec.repayment_schedule_ids
            unpaid_schedule = schedule.filtered(lambda s: s.status != "paid").sorted("due_date")
            rec.next_payment_due_date = unpaid_schedule[0].due_date if unpaid_schedule else False

    # Kept separate from _compute_ux_helpers (distinct store=True/False) —
    # sharing one compute method across stored and non-stored fields makes
    # reading either of these silently trigger a recompute+write of the
    # stored fields above as a side effect.
    @api.depends("repayment_schedule_ids.status", "repayment_schedule_ids.due_date", "repayment_schedule_ids.balance_due")
    def _compute_next_payment_amount(self):
        today = fields.Date.today()
        for rec in self:
            schedule = rec.current_repayment_schedule_ids or rec.repayment_schedule_ids
            unpaid_schedule = schedule.filtered(lambda s: s.status != "paid").sorted("due_date")
            if unpaid_schedule:
                next_item = unpaid_schedule[0]
                rec.next_payment_amount = next_item.balance_due
                rec.days_until_due = (next_item.due_date - today).days
            else:
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
                rec.state in ("normal", "watch", "substandard", "doubtful")
                and rec.days_in_arrears <= 90
                and not rec.topup_ids.filtered(lambda t: t.state in ["draft", "pending"])
            )

    @api.depends("repayment_schedule_ids", "repayment_schedule_ids.status")
    def _compute_remaining_tenure(self):
        for rec in self:
            schedule = rec.current_repayment_schedule_ids or rec.repayment_schedule_ids
            unpaid = schedule.filtered(lambda s: s.status != "paid")
            rec.remaining_tenure = len(unpaid)

    @api.depends("repayment_schedule_ids", "repayment_schedule_ids.total_due")
    def _compute_installment_amount(self):
        for rec in self:
            # Get the installment amount from the first unpaid schedule line
            schedule = rec.current_repayment_schedule_ids or rec.repayment_schedule_ids
            unpaid = schedule.filtered(lambda s: s.status != "paid")
            if unpaid:
                rec.installment_amount = unpaid[0].total_due
            elif rec.repayment_schedule_ids:
                # All paid - get from first paid
                rec.installment_amount = rec.repayment_schedule_ids[0].total_due
            else:
                rec.installment_amount = 0

    @api.depends(
        "state",
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
            schedule = (rec.current_repayment_schedule_ids or rec.repayment_schedule_ids).sorted("due_date")
            rec.first_installment_date = schedule[:1].due_date if schedule else False
            rec.last_installment_date = schedule[-1:].due_date if schedule else False

            if rec.state == "written_off":
                rec.outstanding_principal = 0.0
                rec.outstanding_interest = 0.0
                rec.outstanding_charges = 0.0
                rec.total_interest = sum(schedule.mapped("interest_due"))
                rec.interest_amount = rec.total_interest
                rec.prepayment_amount = 0.0
                rec.total_topup_amount = 0.0
                continue

            rec.outstanding_principal = sum(
                max(line.principal_due - line.principal_paid, 0.0)
                for line in schedule
            )
            rec.outstanding_interest = sum(
                max(line.interest_due - line.interest_paid, 0.0)
                for line in schedule
            )
            rec.total_interest = sum(schedule.mapped("interest_due"))
            rec.interest_amount = rec.total_interest

            # Only nets against fees_component — penalty_component is a
            # separate charge (tracked via the schedule's penalty_due/paid)
            # and must not be counted as if it were paying down the
            # origination fee. Mixing the two understated this balance
            # whenever a customer paid a penalty, and fed a wrong default
            # into loan_refinance.py's settlement_amount suggestion.
            posted_repayments = rec.repayment_ids.filtered(lambda r: r.state == "posted")
            paid_charges = sum(posted_repayments.mapped("fees_component"))
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

    @api.depends("repayment_schedule_ids.due_date", "repayment_schedule_ids.interest_due")
    def _compute_accrued_interest(self):
        today = fields.Date.today()
        for rec in self:
            schedule = rec.current_repayment_schedule_ids or rec.repayment_schedule_ids
            rec.accrued_interest = sum(
                line.interest_due for line in schedule if line.due_date <= today
            )

    def _get_posted_interest_accrual(self):
        """Sum of debit-credit already posted to the Interest Receivable
        account for this loan — the same query action_post_interest_accrual_entry()
        uses to compute the delta still owed. Shared so the "pending" flag
        and the "how much to post" logic can never disagree with each other."""
        self.ensure_one()
        product = self.loan_product_id
        if not product or not product.account_interest_receivable_id:
            return None
        posted_interest = 0.0
        moves = self.env["account.move"].search([
            ("alba_loan_id", "=", self.id),
            ("state", "=", "posted"),
        ])
        for move in moves:
            for line in move.line_ids:
                if line.account_id == product.account_interest_receivable_id:
                    posted_interest += (line.debit - line.credit)
        return posted_interest

    @api.depends("state", "accrued_interest")
    def _compute_is_accrual_pending(self):
        """
        True only when there is a real, uncollected interest delta to post —
        i.e. exactly the condition action_post_interest_accrual_entry() itself
        checks before posting. Previously this just checked "has any INT/
        entry been posted this calendar month", which could disagree with the
        delta check: a loan already over-posted in a prior run (from the old
        bug that booked the full lifetime total every click) would show the
        amber "accrual pending, please click" banner while the button itself
        correctly found nothing left to post and did nothing — a confusing,
        contradictory state.
        """
        active_states = ("normal", "watch", "substandard", "doubtful", "loss")

        for rec in self:
            if rec.state not in active_states:
                rec.is_accrual_pending = False
                continue

            try:
                posted_interest = rec._get_posted_interest_accrual()
            except Exception:
                _logger.exception(
                    "is_accrual_pending: failed checking accrual for loan %s",
                    rec.id,
                )
                rec.is_accrual_pending = True
                continue

            if posted_interest is None:
                # Interest Receivable account not configured on the product —
                # nothing actionable to nag about.
                rec.is_accrual_pending = False
                continue

            rec.is_accrual_pending = (rec.accrued_interest - posted_interest) > 0.01

    # =========================================================================
    # IMPORT-EXPORT FIX: no-op inverse methods for all computed+stored fields
    # Import can write to these; compute logic resets them on the next trigger.
    # =========================================================================
    def _inverse_total_repayable(self): pass
    def _inverse_net_disbursement_amount(self): pass
    def _inverse_total_paid(self): pass
    def _inverse_outstanding_balance(self): pass
    def _inverse_arrears_amount(self): pass
    def _inverse_days_in_arrears(self): pass
    def _inverse_remaining_tenure(self): pass
    def _inverse_installment_amount(self): pass
    def _inverse_first_installment_date(self): pass
    def _inverse_last_installment_date(self): pass
    def _inverse_outstanding_principal(self): pass
    def _inverse_outstanding_interest(self): pass
    def _inverse_total_interest(self): pass
    def _inverse_interest_amount(self): pass
    def _inverse_outstanding_charges(self): pass
    def _inverse_prepayment_amount(self): pass
    def _inverse_total_topup_amount(self): pass
    def _inverse_par_bucket(self): pass
    def _inverse_noop(self):
        pass

    def _compute_current_repayment_schedule(self):
        """Compute the active repayment schedule lines for the loan (latest active batch)."""
        for rec in self:
            Batch = self.env["alba.repayment.schedule.batch"]
            batch = Batch.search([("loan_id", "=", rec.id), ("state", "=", "active")], limit=1, order="generated_on desc")
            if batch:
                schedules = self.env["alba.repayment.schedule"].search([("loan_id", "=", rec.id), ("batch_id", "=", batch.id)], order="installment_number asc")
                rec.current_repayment_schedule_ids = schedules
            else:
                # Fallback to schedule lines not attached to archived batches
                rec.current_repayment_schedule_ids = self.env["alba.repayment.schedule"].search([
                    ("loan_id", "=", rec.id),
                    "|", ("batch_id", "=", False), ("batch_id.state", "=", "active")
                ], order="installment_number asc")

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

    def _recompute_schedule_paid_amounts(self):
        """Reset and reapply all posted repayments to schedule entries."""
        self.ensure_one()
        # 1. Reset all schedule entries
        self.repayment_schedule_ids.write({
            "principal_paid": 0.0,
            "interest_paid": 0.0,
        })
        # Trigger recompute of status and balance_due
        self.repayment_schedule_ids._compute_status()

        # 2. Get all posted repayments
        posted_repayments = self.repayment_ids.filtered(lambda r: r.state == "posted").sorted(
            key=lambda r: (r.payment_date or fields.Date.today(), r.id)
        )

        # 3. Apply each one
        for repayment in posted_repayments:
            repayment._update_schedule_entries()

    def action_generate_schedule(self):
        """
        Generate the repayment schedule based on the loan product's method.

        When called on a loan that already has repayment/accrual history
        (top-up, partial payoff, any future modification that changes
        principal/tenure on the SAME loan rather than creating a new one),
        already-elapsed installments are preserved untouched and only the
        remaining future installments are (re)built over the remaining
        tenure. Rebuilding history too — the old behaviour — retroactively
        restated past due amounts under the new principal, then replayed the
        old (smaller/larger) actual payments against those restated amounts,
        making settled installments look wrongly under/over-paid.
        """
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

            Schedule = self.env["alba.repayment.schedule"]
            Batch = self.env["alba.repayment.schedule.batch"]

            existing_lines = Schedule.search([("loan_id", "=", rec.id)])
            # A line carries real history if anything has ever been paid or
            # accrued against it — those facts must never be rewritten.
            history_lines = existing_lines.filtered(
                lambda l: l.principal_paid > 0
                or l.interest_paid > 0
                or l.penalty_paid > 0
                or l.penalty_due > 0
            )
            lines_to_replace = existing_lines - history_lines

            if history_lines:
                start_installment_number = max(history_lines.mapped("installment_number")) + 1
                remaining_principal = max(
                    rec.principal_amount - sum(history_lines.mapped("principal_paid")), 0.0
                )
                future_count = rec.tenure_months - len(history_lines)
                if future_count <= 0:
                    raise UserError(
                        _(
                            "New tenure (%(tenure)d months) must be greater than the "
                            "%(settled)d instalment(s) already settled on loan %(loan)s."
                        )
                        % {
                            "tenure": rec.tenure_months,
                            "settled": len(history_lines),
                            "loan": rec.loan_number,
                        }
                    )
            else:
                start_installment_number = 1
                remaining_principal = rec.principal_amount
                future_count = rec.tenure_months

            schedule_data = []
            if rec.interest_method == "flat_rate":
                monthly_interest = remaining_principal * (rec.interest_rate / 100)
                equal_principal = round(remaining_principal / future_count, 2)
                balance = remaining_principal
                for i in range(future_count):
                    principal = (
                        equal_principal
                        if i < future_count - 1
                        else round(balance, 2)
                    )
                    schedule_data.append(
                        {
                            "installment_number": start_installment_number + i,
                            "opening_balance": round(balance, 2),
                            "principal_due": principal,
                            "interest_due": round(monthly_interest, 2),
                            "closing_balance": round(balance - principal, 2),
                        }
                    )
                    balance -= principal
            else:
                schedule_data = product.calculate_reducing_schedule(
                    remaining_principal, future_count
                )
                for row in schedule_data:
                    row["installment_number"] = (
                        start_installment_number
                        + row.get("installment_number", row.get("installment")) - 1
                    )

            # Build due dates — installment numbering continues from the
            # existing cadence (anchored at the original disbursement_date),
            # so a regenerated future instalment lands on the same due date
            # it always would have, rather than being back-dated to "today".
            schedule_vals = []
            for row in schedule_data:
                installment_number = row.get("installment_number", row.get("installment"))
                if installment_number is None:
                    raise UserError(
                        _(
                            "Schedule row is missing an installment number for loan %s."
                        ) % rec.loan_number
                    )
                n = installment_number
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
                        "installment_number": installment_number,
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
                if history_lines:
                    # Regeneration on a loan with history: keep the current
                    # active batch (history and future instalments must stay
                    # in the same batch so _get_schedule_lines() sees both),
                    # only replace the untouched future lines.
                    batch = Batch.search(
                        [("loan_id", "=", rec.id), ("state", "=", "active")],
                        limit=1,
                        order="generated_on desc",
                    )
                    if not batch:
                        batch = Batch.create({
                            "loan_id": rec.id,
                            "notes": "Generated by action_generate_schedule (history preserved)",
                        })
                        history_lines.write({"batch_id": batch.id})
                    lines_to_replace.unlink()
                else:
                    # Fresh loan (or a loan with no repayment/accrual history
                    # yet): archive any existing active batch and rebuild
                    # the whole schedule from scratch, as before.
                    existing_batch = Batch.search([("loan_id", "=", rec.id), ("state", "=", "active")])
                    if existing_batch:
                        existing_batch.write({"state": "archived"})
                    existing_lines.unlink()
                    batch = Batch.create({
                        "loan_id": rec.id,
                        "notes": "Generated by action_generate_schedule",
                    })

                for v in schedule_vals:
                    v["batch_id"] = batch.id

                Schedule.create(schedule_vals)
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
        Consolidated Disbursement Posting:
        1. ENTRY 1 — Loan Approval (DR Rec, CR Clearing, CR Fees)
        2. ENTRY 2 — Loan Disbursement (DR Clearing, CR Outstanding Payments)
        """
        self.ensure_one()
        if not self.journal_id:
            raise UserError(_("Please select a Disbursement Journal before posting the entry."))
        if self.journal_id.type not in ("bank", "cash"):
            raise UserError(
                _(
                    "Disbursement journal '%s' must be a Bank or Cash journal."
                ) % self.journal_id.display_name
            )

        # 1. Post ENTRY 1 (if not already posted)
        self.application_id.action_post_approval_entry(journal=self.journal_id)

        # 2. Post ENTRY 2
        if self.disbursement_move_id:
            return self.disbursement_move_id

        self._ensure_disbursement_payment_method_line()

        product = self.loan_product_id
        if not product:
            raise UserError(_("Please configure a Loan Product before posting disbursement entry."))
        if not product.account_clearing_id:
            raise UserError(_("Please configure Loan Clearing account on product '%s'.") % product.name)

        outstanding_account = (
            self.payment_method_line_id.payment_account_id
            or self.journal_id.default_account_id
        )
        if not outstanding_account:
            raise UserError(
                _(
                    'Journal "%s" has no bank/cash account configured for disbursement. '
                    'Please set the journal default account or the outbound payment method account '
                    'before posting the loan disbursement.'
                ) % self.journal_id.name
            )

        application = self.application_id
        total_fees = sum(application.fee_line_ids.mapped("calculated_amount"))
        net_amount = self.principal_amount - total_fees

        move_vals = {
            "journal_id": self.journal_id.id,
            "date": self.disbursement_date,
            "ref": f"DISB/{self.loan_number}",
            "move_type": "entry",
            "alba_loan_id": self.id,
            "preferred_payment_method_line_id": self.payment_method_line_id.id if self.payment_method_line_id else False,
            "line_ids": [
                # DR Loan Clearing Account
                (0, 0, {
                    "account_id": product.account_clearing_id.id,
                    "name": _("Loan Clearing — %s") % self.loan_number,
                    "debit": net_amount,
                    "credit": 0.0,
                    "partner_id": self.customer_id.partner_id.id,
                }),
                # CR Actual Bank/Cash account used for the disbursement
                (0, 0, {
                    "account_id": outstanding_account.id,
                    "name": _("Net Disbursement — %s") % self.loan_number,
                    "debit": 0.0,
                    "credit": net_amount,
                    "partner_id": self.customer_id.partner_id.id,
                }),
            ],
        }

        move = self.env["account.move"].create(move_vals)
        move.action_post()
        self.write({"disbursement_move_id": move.id})
        self.message_post(
            body=_("Disbursement journal entry %s posted for KES %s.")
            % (move.name, f"{net_amount:,.2f}")
        )
        
        # Trigger automatic provisioning
        self.action_post_provisioning_entry()
        
        return move

    def action_post_interest_accrual_entry(self, amount=None):
        """
        ENTRY 3 — Interest Accrual:
        DR  Loan Interest Receivable       interest amount
        CR  Loan Interest Income           interest amount

        NOTE: This entry must use a General journal (type='general'), NOT the
        disbursement bank/cash journal, because it is a P&L accrual with no
        cash movement.

        `amount`, when not explicitly given, is NOT the loan's full lifetime
        interest (`total_interest`) — posting that in one shot would
        recognise interest for periods that haven't happened yet, and
        posting it again on every click/every month would re-book income
        already recognised. Instead we net against what's already been
        posted, same pattern as action_post_provisioning_entry(): compute
        interest earned to date (`accrued_interest`), subtract what's
        already posted to the Interest Receivable account for this loan,
        and post only the difference.
        """
        self.ensure_one()
        product = self.loan_product_id
        if not product.account_interest_receivable_id:
            raise UserError(_("Please configure Interest Receivable account on product '%s'.") % product.name)
        if not product.account_interest_income_id:
            raise UserError(_("Please configure Interest Income account on product '%s'.") % product.name)

        if amount is not None:
            interest_amount = amount
        else:
            posted_interest = self._get_posted_interest_accrual() or 0.0
            interest_amount = self.accrued_interest - posted_interest

        if interest_amount <= 0.01:
            self.is_accrual_pending = False
            self.message_post(body=_(
                "Interest accrual check: no new interest to post — "
                "KES %.2f already posted covers accrual to date."
            ) % (self._get_posted_interest_accrual() or 0.0))
            return False

        # Resolve a General journal — never use the bank/cash disbursement journal
        # for a pure P&L accrual entry (no cash movement involved).
        accrual_journal = (
            self.journal_id
            if self.journal_id and self.journal_id.type == "general"
            else False
        )
        if not accrual_journal:
            accrual_journal = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", self.company_id.id)],
                limit=1,
            )
        if not accrual_journal:
            raise UserError(_(
                "No General journal found for company '%s'. "
                "Please create one under Accounting > Configuration > Journals."
            ) % self.company_id.name)

        move_vals = {
            "journal_id": accrual_journal.id,
            "date": fields.Date.context_today(self),
            "ref": f"INT/{self.loan_number}",
            "move_type": "entry",
            "alba_loan_id": self.id,
            "line_ids": [
                # DR Loan Interest Receivable
                (0, 0, {
                    "account_id": product.account_interest_receivable_id.id,
                    "name": _("Interest Accrual \u2014 %s") % self.loan_number,
                    "debit": interest_amount,
                    "credit": 0.0,
                    "partner_id": self.customer_id.partner_id.id,
                }),
                # CR Loan Interest Income
                (0, 0, {
                    "account_id": product.account_interest_income_id.id,
                    "name": _("Interest Income \u2014 %s") % self.loan_number,
                    "debit": 0.0,
                    "credit": interest_amount,
                    "partner_id": self.customer_id.partner_id.id,
                }),
            ],
        }

        move = self.env["account.move"].create(move_vals)
        move.action_post()
        self.is_accrual_pending = False
        self.message_post(
            body=_("Interest accrual journal entry %s posted for KES %s.")
            % (move.name, f"{interest_amount:,.2f}")
        )
        return True

    def action_post_penalty_accrual_entry(self, amount=None):
        """
        ENTRY 3b — Penalty Accrual:
        DR  Loan Penalty Receivable       penalty amount
        CR  Loan Penalty Income           penalty amount

        NOTE: This entry must use a General journal (type='general'), NOT the
        disbursement bank/cash journal, because it is a P&L accrual with no
        cash movement.
        """
        self.ensure_one()
        product = self.loan_product_id
        # Use penalty receivable account if configured, otherwise fall back to interest receivable
        penalty_receivable_account = product.account_penalty_receivable_id or product.account_interest_receivable_id
        penalty_income_account = product.account_penalty_income_id or product.account_interest_income_id
        
        if not penalty_receivable_account:
            raise UserError(_("Please configure Penalty Receivable or Interest Receivable account on product '%s'.") % product.name)
        if not penalty_income_account:
            raise UserError(_("Please configure Penalty Income or Interest Income account on product '%s'.") % product.name)

        penalty_amount = amount if amount is not None else 0.0
        if penalty_amount <= 0:
            return False

        # Resolve a General journal — never use the bank/cash disbursement journal
        # for a pure P&L accrual entry (no cash movement involved).
        accrual_journal = (
            self.journal_id
            if self.journal_id and self.journal_id.type == "general"
            else False
        )
        if not accrual_journal:
            accrual_journal = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", self.company_id.id)],
                limit=1,
            )
        if not accrual_journal:
            raise UserError(_(
                "No General journal found for company '%s'. "
                "Please create one under Accounting > Configuration > Journals."
            ) % self.company_id.name)

        move_vals = {
            "journal_id": accrual_journal.id,
            "date": fields.Date.context_today(self),
            "ref": f"PEN/{self.loan_number}",
            "move_type": "entry",
            "alba_loan_id": self.id,
            "line_ids": [
                # DR Loan Penalty Receivable
                (0, 0, {
                    "account_id": penalty_receivable_account.id,
                    "name": _("Penalty Accrual \u2014 %s") % self.loan_number,
                    "debit": penalty_amount,
                    "credit": 0.0,
                    "partner_id": self.customer_id.partner_id.id,
                }),
                # CR Loan Penalty Income
                (0, 0, {
                    "account_id": penalty_income_account.id,
                    "name": _("Penalty Income \u2014 %s") % self.loan_number,
                    "debit": 0.0,
                    "credit": penalty_amount,
                    "partner_id": self.customer_id.partner_id.id,
                }),
            ],
        }

        move = self.env["account.move"].create(move_vals)
        move.action_post()
        self.message_post(
            body=_("Penalty accrual journal entry %s posted for KES %s.")
            % (move.name, f"{penalty_amount:,.2f}")
        )
        return True


    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        for rec in self:
            if rec.payment_method_line_id and rec.payment_method_line_id.journal_id != rec.journal_id:
                rec.payment_method_line_id = False

    def _ensure_disbursement_payment_method_line(self):
        for rec in self:
            if not rec.journal_id:
                continue
            if rec.payment_method_line_id:
                if rec.payment_method_line_id.journal_id != rec.journal_id:
                    raise UserError(_(
                        "Payment Method '%(method)s' does not belong to Disbursement Journal '%(journal)s'.",
                        method=rec.payment_method_line_id.display_name,
                        journal=rec.journal_id.display_name,
                    ))
                if rec.payment_method_line_id.payment_type != "outbound":
                    raise UserError(_("Please select an outbound payment method for disbursement journal '%s'.") % rec.journal_id.display_name)
                continue

            method_line = self.env["account.payment.method.line"].search([
                ("payment_type", "=", "outbound"),
                ("journal_id", "=", rec.journal_id.id),
            ], limit=1)
            if not method_line:
                raise UserError(_("Please configure an outbound Payment Method on disbursement journal '%s'.") % rec.journal_id.display_name)
            rec.payment_method_line_id = method_line

    def action_post_provisioning_entry(self):
        """
        Post or adjust the provisioning journal entry for potential loan losses.
        Calculates the required provision based on the loan's current state and outstanding balance,
        compares it with the already posted provisions (sum of all entries linked to this loan hitting the allowance account),
        and posts an adjusting journal entry for the difference.
        """
        self.ensure_one()
        product = self.loan_product_id
        if not product.account_provision_id or not product.account_provision_expense_id:
            return False

        # Resolve a General journal for pure accrual/non-cash entries
        accrual_journal = (
            self.journal_id
            if self.journal_id and self.journal_id.type == "general"
            else False
        )
        if not accrual_journal:
            accrual_journal = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", self.company_id.id)],
                limit=1,
            )
        if not accrual_journal:
            raise UserError(_(
                "No General journal found for company '%s'. "
                "Please create one under Accounting > Configuration > Journals."
            ) % self.company_id.name)

        required_provision = self.provision_amount or 0.0

        # Query all posted moves linked to this loan
        posted_provision = 0.0
        moves = self.env["account.move"].search([
            ("alba_loan_id", "=", self.id),
            ("state", "=", "posted")
        ])
        for move in moves:
            for line in move.line_ids:
                if line.account_id == product.account_provision_id:
                    # Credit is positive for Allowance/Contra-Asset account, Debit is negative
                    posted_provision += (line.credit - line.debit)

        adjustment = required_provision - posted_provision

        # If adjustment is tiny/zero, nothing to do
        if abs(adjustment) < 0.01:
            return False

        if adjustment > 0:
            # We need to increase provision: DR Expense, CR Contra-Asset
            line_ids = [
                # DR Provision Expense
                (0, 0, {
                    "account_id": product.account_provision_expense_id.id,
                    "name": _("Adjust Loan Loss Provision Expense [%s] — %s") % (self.state, self.loan_number),
                    "debit": adjustment,
                    "credit": 0.0,
                    "partner_id": self.customer_id.partner_id.id,
                }),
                # CR Provision Account (Asset Offset)
                (0, 0, {
                    "account_id": product.account_provision_id.id,
                    "name": _("Adjust Allowance for Credit Losses [%s] — %s") % (self.state, self.loan_number),
                    "debit": 0.0,
                    "credit": adjustment,
                    "partner_id": self.customer_id.partner_id.id,
                }),
            ]
            msg_type = _("increased")
        else:
            # We need to decrease provision (release): DR Contra-Asset, CR Expense
            release_amount = abs(adjustment)
            line_ids = [
                # DR Provision Account (Asset Offset)
                (0, 0, {
                    "account_id": product.account_provision_id.id,
                    "name": _("Release Allowance for Credit Losses [%s] — %s") % (self.state, self.loan_number),
                    "debit": release_amount,
                    "credit": 0.0,
                    "partner_id": self.customer_id.partner_id.id,
                }),
                # CR Provision Expense
                (0, 0, {
                    "account_id": product.account_provision_expense_id.id,
                    "name": _("Release Loan Loss Provision Expense [%s] — %s") % (self.state, self.loan_number),
                    "debit": 0.0,
                    "credit": release_amount,
                    "partner_id": self.customer_id.partner_id.id,
                }),
            ]
            msg_type = _("released/decreased")

        move_vals = {
            "journal_id": accrual_journal.id,
            "date": fields.Date.today(),
            "ref": f"PROV/{self.loan_number} ({self.state.upper()})",
            "move_type": "entry",
            "alba_loan_id": self.id,
            "line_ids": line_ids,
        }

        move = self.env["account.move"].create(move_vals)
        move.action_post()

        # Update provision_move_id if it's the first move
        if not self.provision_move_id:
            self.write({"provision_move_id": move.id})

        self.message_post(
            body=_("Provisioning journal entry %s posted: KES %s was %s (New Provision Balance: KES %s, Status: %s).")
            % (move.name, f"{abs(adjustment):,.2f}", msg_type, f"{required_provision:,.2f}", self.state.upper())
        )
        return move

    def action_post_write_off_entry(self):
        """
        Create a journal entry to write off the loan's outstanding principal, interest, and penalties
        by debiting the Provision/Allowance account and crediting the Loan, Interest Receivable, and Penalty Receivable accounts.
        """
        self.ensure_one()
        write_off_move = self.env["account.move"].search([
            ("alba_loan_id", "=", self.id),
            ("ref", "like", "WRT/%"),
            ("state", "=", "posted")
        ], limit=1)
        if write_off_move:
            return write_off_move

        product = self.loan_product_id
        if not product.account_loan_receivable_id or not product.account_interest_receivable_id or not product.account_provision_id:
            raise UserError(_("Please configure Loan Receivable, Interest Receivable, and Provision accounts on the product '%s' before writing off.") % product.name)

        # Calculate actual outstanding principal, interest, and penalty from the schedule
        schedule = (self.current_repayment_schedule_ids or self.repayment_schedule_ids)
        outstanding_principal = sum(max(line.principal_due - line.principal_paid, 0.0) for line in schedule)
        outstanding_interest = sum(max(line.interest_due - line.interest_paid, 0.0) for line in schedule)
        outstanding_penalty = sum(max(line.penalty_due - line.penalty_paid, 0.0) for line in schedule)
        total_write_off = outstanding_principal + outstanding_interest + outstanding_penalty

        if total_write_off <= 0:
            return False

        # Resolve a General journal
        accrual_journal = (
            self.journal_id
            if self.journal_id and self.journal_id.type == "general"
            else False
        )
        if not accrual_journal:
            accrual_journal = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", self.company_id.id)],
                limit=1,
            )
        if not accrual_journal:
            raise UserError(_("No General journal found for company '%s'.") % self.company_id.name)

        line_ids = [
            # DR Provision Account (Allowance for Credit Losses)
            (0, 0, {
                "account_id": product.account_provision_id.id,
                "name": _("Write-Off Allowance Utilization — %s") % self.loan_number,
                "debit": total_write_off,
                "credit": 0.0,
                "partner_id": self.customer_id.partner_id.id,
            })
        ]

        if outstanding_principal > 0:
            line_ids.append((0, 0, {
                "account_id": product.account_loan_receivable_id.id,
                "name": _("Write-Off Principal — %s") % self.loan_number,
                "debit": 0.0,
                "credit": outstanding_principal,
                "partner_id": self.customer_id.partner_id.id,
            }))

        if outstanding_interest > 0:
            line_ids.append((0, 0, {
                "account_id": product.account_interest_receivable_id.id,
                "name": _("Write-Off Interest — %s") % self.loan_number,
                "debit": 0.0,
                "credit": outstanding_interest,
                "partner_id": self.customer_id.partner_id.id,
            }))

        if outstanding_penalty > 0:
            # Use penalty receivable account if configured, otherwise fall back to interest receivable
            penalty_account = product.account_penalty_receivable_id or product.account_interest_receivable_id
            line_ids.append((0, 0, {
                "account_id": penalty_account.id,
                "name": _("Write-Off Penalty — %s") % self.loan_number,
                "debit": 0.0,
                "credit": outstanding_penalty,
                "partner_id": self.customer_id.partner_id.id,
            }))

        move_vals = {
            "journal_id": accrual_journal.id,
            "date": fields.Date.today(),
            "ref": f"WRT/{self.loan_number}",
            "move_type": "entry",
            "alba_loan_id": self.id,
            "line_ids": line_ids,
        }

        move = self.env["account.move"].create(move_vals)
        move.action_post()
        return move

    def action_write_off(self):
        self.ensure_one()
        self.write({"state": "written_off"})
        self.action_post_write_off_entry()
        self.action_post_provisioning_entry()

        # action_post_write_off_entry() only posts the GL entry — it never
        # touches the schedule lines themselves. Settle them here (due =
        # paid) so repayment_schedule_ids.balance_due reads 0 too; anything
        # that reads the schedule directly (reports, other modules) would
        # otherwise still see stale unpaid balances on a written-off loan.
        schedule_to_settle = self.repayment_schedule_ids.filtered(lambda s: s.balance_due > 0)
        for line in schedule_to_settle:
            line.write({
                "principal_due": line.principal_paid,
                "interest_due": line.interest_paid,
                "penalty_due": line.penalty_paid,
            })

        self.message_post(body=Markup(_("Loan has been <b>Written Off</b> as per policy (Loss classification).")))

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

    def action_view_disbursement_entry(self):
        """Open the disbursement journal entry (memo)."""
        self.ensure_one()
        if not self.disbursement_move_id:
            raise UserError(_("No disbursement journal entry has been posted yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Disbursement Entry — %s") % self.loan_number,
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.disbursement_move_id.id,
        }

    def action_view_provision_entry(self):
        """Open the provision journal entry (memo)."""
        self.ensure_one()
        if not self.provision_move_id:
            raise UserError(_("No provision journal entry found."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Provision Entry — %s") % self.loan_number,
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.provision_move_id.id,
        }

    def action_request_topup(self):
        """Open wizard to request top-up"""
        self.ensure_one()
        if not self.can_request_topup:
            raise UserError(_("This loan is not eligible for top-up."))
        # Open the refinance wizard prefilled with this loan as a Top-Up flow.
        return {
            "type": "ir.actions.act_window",
            "name": _("Refinance / Top-Up"),
            "res_model": "alba.loan.refinance.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_original_loan_id": self.id,
                "active_id": self.id,
                "active_model": "alba.loan",
                "alba_topup_mode": True,
            },
        }

    def action_quick_payment(self):
        """Open quick payment wizard for manual partial payments."""
        self.ensure_one()
        if self.state in ("closed", "written_off"):
            raise UserError(_("Payments are only allowed on active loans."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Quick Payment"),
            "res_model": "alba.loan.payment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"active_id": self.id, "is_quick_payment": True},
        }

    def action_full_repayment(self):
        """Open payment wizard prefilled to settle outstanding balance."""
        self.ensure_one()
        if self.state in ("closed", "written_off"):
            raise UserError(_("Full repayment is only allowed for active loans."))
        if self.outstanding_balance <= 0.0:
            raise UserError(_("Loan has no outstanding balance to repay."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Full Repayment"),
            "res_model": "alba.loan.payment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"active_id": self.id, "default_amount": self.outstanding_balance, "is_full_payment": True},
        }

    def action_calculate_partial_payoff(self):
        """Open wizard to calculate partial payoff"""
        self.ensure_one()
        if self.state in ("closed", "written_off"):
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
        # Active states: normal, watch, substandard, doubtful, loss
        active_loans = self.search([("state", "in", ["normal", "watch", "substandard", "doubtful", "loss"])])
        active_loans._compute_par()
        for loan in active_loans:
            loan.action_post_provisioning_entry()

    # =========================================================================
    # Scheduled action (cron) — Classification monitor
    # =========================================================================

    @api.model
    def cron_flag_npl_loans(self):
        """
        Daily cron: monitor loan classification and fire webhooks.
        """
        _logger = __import__("logging").getLogger(__name__)
        active_loans = self.search([("state", "in", ["normal", "watch", "substandard", "doubtful", "loss"])])
        active_loans._compute_par()

        # Fire webhooks for loans that moved into substandard/doubtful/loss/written_off
        watch_loans = active_loans.filtered(lambda l: l.state in ('substandard', 'doubtful', 'loss', 'written_off'))
        if watch_loans:
            self._fire_loan_status_webhooks(watch_loans, "loan.classification_updated")

        _logger.info("cron_flag_npl_loans: updated classifications for %d loan(s).", len(active_loans))

    @api.model
    def cron_flag_write_off_candidates(self):
        """Daily cron: Identify loans that meet write-off criteria and post chatter warning alerts."""
        _logger = __import__("logging").getLogger(__name__)
        candidates = self.search([("is_write_off_candidate", "=", True)])
        for loan in candidates:
            loan.message_post(
                body=Markup(_(
                    "<b>WRITE-OFF CANDIDATE WARNING</b>: Loan <b>%s</b> is %d day(s) in arrears / past maturity. "
                    "Eligible for Write-Off review under product '%s' policy."
                )) % (
                    loan.loan_number,
                    max(loan.days_in_arrears, loan.days_past_maturity),
                    loan.loan_product_id.name if loan.loan_product_id else ""
                )
            )
        _logger.info("cron_flag_write_off_candidates: identified %d write-off candidate(s).", len(candidates))

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
                    ("loan_id.state", "in", ["normal", "watch", "substandard", "doubtful"]),
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
                ("state", "in", ["normal", "watch", "substandard", "doubtful"]),
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
        candidates = self.search([("state", "in", ["normal", "watch", "substandard", "doubtful"])])
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

        # ── Send loan-closed congratulations email ──────────────────────────
        closed_template = self.env.ref(
            "alba_loans.email_template_loan_closed", raise_if_not_found=False
        )
        if closed_template:
            for loan in closed:
                if loan.customer_id.email:
                    try:
                        closed_template.send_mail(loan.id, force_send=False)
                    except Exception as exc:
                        _logger.warning(
                            "cron_close_repaid_loans: failed to send closure email for %s: %s",
                            loan.loan_number, exc,
                        )

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
          • total_disbursed (sum of principal_amount on active loans)
          • total_outstanding (sum of outstanding_balance)
          • total_arrears
          • par_30  (outstanding balance of loans 1-30 days in arrears)
          • par_90  (outstanding balance of loans >90 days in arrears - Doubtful/Loss)
          • npl_count (loans classified as substandard, doubtful or loss)
        """
        import logging as _logging

        _logger = _logging.getLogger(__name__)

        active = self.search([("state", "in", ["normal", "watch", "substandard", "doubtful"])])
        if not active:
            return

        npl = active.filtered(lambda l: l.state in ("substandard", "doubtful", "loss"))
        par_30 = active.filtered(lambda l: l.state == "watch")
        par_90 = active.filtered(
            lambda l: l.state in ("substandard", "doubtful", "loss")
        )

        stats = {
            "total_active_loans": len(active),
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
            api_key.send_webhook_with_retry(event_type, payload)

    @api.model
    def _check_company(self, company_id):
        """Ensure company consistency for multi-company setup"""
        if company_id:
            self.company_id = company_id
    
    def action_sync_loan_currency_to_accounting(self):
        """
        Revalue a foreign-currency loan's outstanding receivable against the
        company currency and book the unrealised FX gain/loss.

        Previously this computed a real conversion rate but never used it —
        it posted a single-line entry with hardcoded debit=credit=0.0, so it
        claimed success while moving nothing. This compares the outstanding
        balance's value at its original disbursement-date rate against
        today's rate and books the difference, using the company's standard
        Exchange Gain/Loss accounts and Exchange Rate journal.
        """
        for loan in self:
            if not loan.currency_id:
                raise UserError(_("Loan must have a currency configured"))

            company = loan.company_id
            company_currency = company.currency_id

            if loan.currency_id == company_currency:
                loan.message_post(body=_("Loan currency matches company currency - no sync needed"))
                continue

            if not (loan.disbursement_date and loan.state in ('normal', 'watch', 'substandard', 'doubtful', 'loss')):
                loan.message_post(body=_("Currency sync skipped - loan not yet disbursed"))
                continue

            outstanding = loan.outstanding_balance
            if outstanding <= 0.0:
                loan.message_post(body=_("Currency sync skipped - no outstanding balance to revalue"))
                continue

            loan_currency = loan.currency_id
            today = fields.Date.context_today(self)
            value_at_disbursement_rate = loan_currency._convert(
                outstanding, company_currency, company, loan.disbursement_date
            )
            value_at_today_rate = loan_currency._convert(
                outstanding, company_currency, company, today
            )
            difference = value_at_today_rate - value_at_disbursement_rate
            if abs(difference) < 0.01:
                loan.message_post(body=_("Currency sync: no material FX movement to book."))
                continue

            product = loan.loan_product_id
            if not product or not product.account_loan_receivable_id:
                raise UserError(
                    _("Please configure the Loan Receivable account on product '%s'.")
                    % (product.name if product else "Unknown")
                )

            exch_journal = company.currency_exchange_journal_id
            if not exch_journal:
                raise UserError(_(
                    "Please configure the Exchange Rate journal on company '%s' "
                    "(Accounting > Configuration > Settings)."
                ) % company.name)

            amount = abs(difference)
            if difference > 0:
                # Receivable is worth more in company currency: DR Receivable, CR Exchange Gain
                gain_account = company.income_currency_exchange_account_id
                if not gain_account:
                    raise UserError(_(
                        "Please configure the Exchange Gain account on company '%s' "
                        "(Accounting > Configuration > Settings)."
                    ) % company.name)
                line_ids = [
                    (0, 0, {
                        "account_id": product.account_loan_receivable_id.id,
                        "name": _("FX revaluation — %s") % loan.loan_number,
                        "debit": amount, "credit": 0.0,
                        "partner_id": loan.customer_id.partner_id.id,
                    }),
                    (0, 0, {
                        "account_id": gain_account.id,
                        "name": _("FX gain — %s") % loan.loan_number,
                        "debit": 0.0, "credit": amount,
                        "partner_id": loan.customer_id.partner_id.id,
                    }),
                ]
            else:
                # Receivable is worth less in company currency: DR Exchange Loss, CR Receivable
                loss_account = company.expense_currency_exchange_account_id
                if not loss_account:
                    raise UserError(_(
                        "Please configure the Exchange Loss account on company '%s' "
                        "(Accounting > Configuration > Settings)."
                    ) % company.name)
                line_ids = [
                    (0, 0, {
                        "account_id": loss_account.id,
                        "name": _("FX loss — %s") % loan.loan_number,
                        "debit": amount, "credit": 0.0,
                        "partner_id": loan.customer_id.partner_id.id,
                    }),
                    (0, 0, {
                        "account_id": product.account_loan_receivable_id.id,
                        "name": _("FX revaluation — %s") % loan.loan_number,
                        "debit": 0.0, "credit": amount,
                        "partner_id": loan.customer_id.partner_id.id,
                    }),
                ]

            move = self.env["account.move"].create({
                "journal_id": exch_journal.id,
                "date": today,
                "ref": f"FXREV/{loan.loan_number}",
                "alba_loan_id": loan.id,
                "narration": _("Currency revaluation for loan %s") % loan.loan_number,
                "line_ids": line_ids,
            })
            move.action_post()
            loan.message_post(body=_(
                "Currency sync: %(kind)s of %(currency)s %(amount).2f booked — Journal Entry: %(move)s."
            ) % {
                "kind": _("FX gain") if difference > 0 else _("FX loss"),
                "currency": company_currency.name,
                "amount": amount,
                "move": move.name,
            })
