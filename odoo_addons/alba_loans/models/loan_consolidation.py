# -*- coding: utf-8 -*-
"""
Alba Capital Loan Consolidation
Merge 2-5 customer loans into single loan with blended rate
Fee: 1% of total outstanding
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from markupsafe import Markup


class AlbaLoanConsolidation(models.Model):
    """Loan Consolidation - Merge multiple loans"""
    
    _name = "alba.loan.consolidation"
    _description = "Loan Consolidation"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin", "alba.loan.modification.mixin"]
    
    # Identification
    name = fields.Char(string="Reference", required=True, copy=False, default="New")
    
    # Customer
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="customer_id.partner_id",
        store=True,
    )
    
    # Loans to Consolidate
    loan_ids = fields.Many2many(
        "alba.loan",
        string="Loans to Consolidate",
        required=True,
        domain="[('customer_id', '=', customer_id), ('state', 'in', ['active', 'overdue'])]",
        tracking=True,
    )
    loan_count = fields.Integer(
        string="Number of Loans",
        compute="_compute_loan_details",
        store=True,
    )
    
    # Current Totals
    total_outstanding = fields.Monetary(
        string="Total Outstanding",
        currency_field="currency_id",
        compute="_compute_loan_details",
        store=True,
    )
    total_principal = fields.Monetary(
        string="Total Principal",
        currency_field="currency_id",
        compute="_compute_loan_details",
        store=True,
    )
    total_arrears = fields.Monetary(
        string="Total Arrears",
        currency_field="currency_id",
        compute="_compute_loan_details",
        store=True,
    )
    max_days_in_arrears = fields.Integer(
        string="Max Days in Arrears",
        compute="_compute_loan_details",
        store=True,
    )
    old_combined_emi = fields.Monetary(
        string="Old Combined EMI",
        currency_field="currency_id",
        compute="_compute_loan_details",
        store=True,
    )
    weighted_avg_rate = fields.Float(
        string="Weighted Avg Rate (%)",
        digits=(5, 2),
        compute="_compute_loan_details",
        store=True,
    )
    
    # Consolidation Type
    consolidation_type = fields.Selection([
        ("blend", "Blend Rates (Weighted Average - 0.5% discount)"),
        ("best", "Best Rate (Lowest rate from existing loans)"),
        ("new", "New Rate (Current market rate)"),
    ], string="Rate Calculation Method", required=True, default="blend")
    
    # New Loan Terms
    consolidated_amount = fields.Monetary(
        string="Consolidated Principal",
        currency_field="currency_id",
        required=True,
        tracking=True,
        help="Can include top-up amount",
    )
    new_interest_rate = fields.Float(
        string="New Interest Rate (% p.m.)",
        digits=(5, 2),
        required=True,
        tracking=True,
    )
    new_tenure_months = fields.Integer(
        string="New Tenure (Months)",
        required=True,
        tracking=True,
    )
    new_repayment_frequency = fields.Selection([
        ("weekly", "Weekly"),
        ("fortnightly", "Fortnightly"),
        ("monthly", "Monthly"),
    ], string="Repayment Frequency", required=True, default="monthly")
    new_emi = fields.Monetary(
        string="New EMI",
        currency_field="currency_id",
        compute="_compute_new_terms",
        store=True,
    )
    new_total_repayable = fields.Monetary(
        string="New Total Repayable",
        currency_field="currency_id",
        compute="_compute_new_terms",
        store=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Settlement Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Journal used for settling the original loans",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        domain="[('payment_type', '=', 'inbound'), ('journal_id', '=', journal_id)]",
        help="Specific payment method for the selected journal.",
    )
    monthly_savings = fields.Monetary(
        string="Monthly Savings",
        currency_field="currency_id",
        compute="_compute_new_terms",
        store=True,
        help="Old combined EMI - New EMI",
    )
    
    # Fees
    consolidation_fee_rate = fields.Float(
        string="Consolidation Fee Rate (%)",
        default=1.0,
        help="Standard consolidation fee is 1%",
    )
    consolidation_fee_amount = fields.Monetary(
        string="Consolidation Fee",
        currency_field="currency_id",
        compute="_compute_fees",
        store=True,
    )
    
    # Currency
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="customer_id.currency_id",
        store=True,
    )
    
    # Status
    state = fields.Selection([
        ("draft", "Draft"),
        ("quoted", "Quoted"),
        ("approved", "Approved"),
        ("settled", "Old Loans Settled"),
        ("disbursed", "New Loan Disbursed"),
        ("completed", "Completed"),
        ("rejected", "Rejected"),
    ], string="Status", default="draft", tracking=True)
    
    # Approval
    quote_date = fields.Date(string="Quote Date")
    quote_valid_until = fields.Date(string="Quote Valid Until")
    approved_by = fields.Many2one("res.users", string="Approved By", readonly=True)
    approved_date = fields.Date(string="Approved Date")
    
    # New Loan Links
    new_loan_application_id = fields.Many2one(
        "alba.loan.application",
        string="New Loan Application",
        readonly=True,
    )
    new_loan_id = fields.Many2one(
        "alba.loan",
        string="New Consolidated Loan",
        readonly=True,
    )
    
    # Eligibility
    is_eligible = fields.Boolean(string="Eligible", compute="_compute_eligibility")
    eligibility_warnings = fields.Text(string="Eligibility Warnings", compute="_compute_eligibility")

    document_ids = fields.One2many(
        "alba.loan.document",
        "consolidation_id",
        string="Supporting Documents",
    )
    document_count = fields.Integer(
        string="Documents",
        compute="_compute_document_count",
    )

    @api.depends(
        "loan_ids",
        "total_outstanding",
        "old_combined_emi",
        "consolidated_amount",
        "new_emi",
        "consolidation_fee_amount",
        "monthly_savings",
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
        return self._build_grouped_bar_chart(
            ["Total Outstanding", "Combined EMI", "Consolidated Principal"],
            [
                self._chart_amount(self.total_outstanding),
                self._chart_amount(self.old_combined_emi),
                self._chart_amount(self.total_outstanding),
            ],
            [
                self._chart_amount(self.consolidated_amount),
                self._chart_amount(self.new_emi),
                self._chart_amount(self.consolidated_amount),
            ],
        )

    def _get_modification_impact_chart(self):
        self.ensure_one()
        if not self.loan_ids:
            return None
        labels = [loan.loan_number or "Loan" for loan in self.loan_ids[:8]]
        values = [self._chart_amount(loan.outstanding_balance) for loan in self.loan_ids[:8]]
        if self.consolidation_fee_amount:
            labels.append("Consolidation Fee")
            values.append(self._chart_amount(self.consolidation_fee_amount))
        return self._build_doughnut_chart(labels, values)
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.depends("customer_id", "loan_ids")
    def _compute_loan_details(self):
        for rec in self:
            if not rec.loan_ids:
                rec.loan_count = 0
                rec.total_outstanding = 0
                rec.total_principal = 0
                rec.total_arrears = 0
                rec.max_days_in_arrears = 0
                rec.old_combined_emi = 0
                rec.weighted_avg_rate = 0
                continue
            
            rec.loan_count = len(rec.loan_ids)
            rec.total_outstanding = sum(rec.loan_ids.mapped("outstanding_balance"))
            rec.total_principal = sum(rec.loan_ids.mapped("principal_amount"))
            rec.total_arrears = sum(rec.loan_ids.mapped("arrears_amount"))
            rec.max_days_in_arrears = max(rec.loan_ids.mapped("days_in_arrears") or [0])
            rec.old_combined_emi = sum(rec.loan_ids.mapped("installment_amount"))
            
            # Weighted average rate
            total_outstanding = rec.total_outstanding
            if total_outstanding > 0:
                weighted_sum = sum(
                    loan.outstanding_balance * loan.interest_rate 
                    for loan in rec.loan_ids
                )
                rec.weighted_avg_rate = weighted_sum / total_outstanding
            else:
                rec.weighted_avg_rate = 0
    
    @api.depends("consolidation_type", "weighted_avg_rate")
    def _compute_new_terms(self):
        for rec in self:
            if rec.consolidation_type == "blend":
                # Weighted average - 0.5% discount
                rec.new_interest_rate = max(0.1, rec.weighted_avg_rate - 0.5)
            # For "best" and "new", user enters manually
            
            # Calculate EMI and total repayable
            if rec.consolidated_amount and rec.new_tenure_months and rec.new_interest_rate:
                principal = rec.consolidated_amount
                rate = rec.new_interest_rate / 100
                months = rec.new_tenure_months
                
                interest = principal * rate * months
                rec.new_total_repayable = principal + interest
                rec.new_emi = rec.new_total_repayable / months if months > 0 else 0
                rec.monthly_savings = max(0, rec.old_combined_emi - rec.new_emi)
            else:
                rec.new_emi = 0
                rec.new_total_repayable = 0
                rec.monthly_savings = 0

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
                        "Payment Method '%(method)s' does not belong to Settlement Journal '%(journal)s'.",
                        method=rec.payment_method_line_id.display_name,
                        journal=rec.journal_id.display_name,
                    ))
                if rec.payment_method_line_id.payment_type != "inbound":
                    raise UserError(_("Please select an inbound payment method for settlement journal '%s'.") % rec.journal_id.display_name)
                continue

            method_line = self.env["account.payment.method.line"].search([
                ("payment_type", "=", "inbound"),
                ("journal_id", "=", rec.journal_id.id),
            ], limit=1)
            if not method_line:
                raise UserError(_("Please configure an inbound Payment Method on settlement journal '%s'.") % rec.journal_id.display_name)
            rec.payment_method_line_id = method_line
    
    @api.depends("total_outstanding", "consolidation_fee_rate")
    def _compute_fees(self):
        for rec in self:
            rec.consolidation_fee_amount = rec.total_outstanding * (rec.consolidation_fee_rate / 100)
    
    @api.depends("loan_ids", "customer_id", "max_days_in_arrears")
    def _compute_eligibility(self):
        for rec in self:
            if not rec.loan_ids:
                rec.is_eligible = False
                rec.eligibility_warnings = "No loans selected"
                return
            
            warnings = []
            
            # Check number of loans
            if len(rec.loan_ids) < 2:
                warnings.append("❌ Need at least 2 loans to consolidate")
            if len(rec.loan_ids) > 5:
                warnings.append("❌ Maximum 5 loans can be consolidated")
            
            # Check all loans from same customer
            different_customers = rec.loan_ids.filtered(lambda l: l.customer_id != rec.customer_id)
            if different_customers:
                warnings.append("❌ All loans must belong to the selected customer")
            
            # Check loan states
            invalid_state = rec.loan_ids.filtered(lambda l: l.state not in ["active", "overdue"])
            if invalid_state:
                warnings.append("❌ All loans must be active or overdue (not closed/NPL)")
            
            # Check arrears
            if rec.max_days_in_arrears > 90:
                warnings.append("❌ Cannot consolidate - one or more loans >90 days overdue")
            
            # Check total outstanding limit
            if rec.total_outstanding > 1000000:  # 1M KES limit
                warnings.append("⚠️ Total outstanding exceeds 1M limit - director approval needed")
            
            if warnings:
                rec.is_eligible = False
                rec.eligibility_warnings = "\n".join(warnings)
            else:
                rec.is_eligible = True
                rec.eligibility_warnings = "✅ Eligible for consolidation"
    
    # =========================================================================
    # ORM Overrides
    # =========================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("alba.loan.consolidation") or "New"
        return super().create(vals_list)
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_generate_quote(self):
        """Generate consolidation quote"""
        for rec in self:
            from datetime import date, timedelta
            
            if not rec.is_eligible:
                raise UserError(_("Not eligible:\n%s") % rec.eligibility_warnings)
            
            rec.write({
                "state": "quoted",
                "quote_date": date.today(),
                "quote_valid_until": date.today() + timedelta(days=7),
                # Auto-populate amounts if not set
                "consolidated_amount": rec.consolidated_amount or rec.total_outstanding,
                "new_tenure_months": rec.new_tenure_months or max(rec.loan_ids.mapped("remaining_tenure")),
            })
            
            rec.message_post(body=_(
                "<b>CONSOLIDATION QUOTE</b>: %s loans. Total: %s %s. Fee: %s %s."
            ) % (
                len(rec.loan_ids),
                rec.currency_id.symbol, rec.total_outstanding,
                rec.currency_id.symbol, rec.consolidation_fee_amount,
            ))
    
    def action_approve(self):
        """Approve consolidation"""
        for rec in self:
            if not self.env.user.has_group("alba_loans.group_operations_manager"):
                raise UserError(_("Only Operations Manager can approve consolidations."))
            
            rec.write({
                "state": "approved",
                "approved_by": self.env.user.id,
                "approved_date": fields.Date.today(),
            })
            rec.message_post(body=_("Consolidation approved."))
    
    def action_settle_loans(self):
        """Settle all old loans"""
        for rec in self:
            if rec.state != "approved":
                raise UserError(_("Must be approved first."))
            
            # Auto-select journal if not set
            if not rec.journal_id:
                rec.journal_id = self.env["account.journal"].search([
                    ("type", "=", "bank"),
                ], limit=1)
            
            if not rec.journal_id:
                raise UserError(_("Please select a Settlement Journal before settling the loans."))
            rec._ensure_payment_method_line()
            
            for loan in rec.loan_ids:
                # Create repayment to settle
                repayment = self.env["alba.loan.repayment"].create({
                    "loan_id": loan.id,
                    "payment_date": fields.Date.today(),
                    "amount_paid": loan.outstanding_balance,
                    "payment_method": "bank_transfer",
                    "payment_reference": _("Consolidation settlement - %s") % rec.name,
                    "journal_id": rec.journal_id.id,
                    "payment_method_line_id": rec.payment_method_line_id.id,
                    "notes": _("Loan consolidated into %s") % rec.name,
                })
                repayment.action_post()
                
                # Close loan
                loan.write({"state": "closed"})
                loan.message_post(body=Markup(_("<b>CONSOLIDATED</b>: Settlement Ref: %s")) % rec.name)
            
            rec.write({"state": "settled"})
            rec.message_post(body=_("All %s loans settled.") % len(rec.loan_ids))
    
    def action_create_consolidated_loan(self):
        """Create and disburse new consolidated loan"""
        for rec in self:
            if rec.state != "settled":
                raise UserError(_("Old loans must be settled first."))
            
            # Create application
            application = self.env["alba.loan.application"].create({
                "customer_id": rec.customer_id.id,
                "loan_product_id": rec.loan_ids[0].loan_product_id.id,  # Use first loan's product
                "requested_amount": rec.consolidated_amount,
                "approved_amount": rec.consolidated_amount,
                "tenure_months": rec.new_tenure_months,
                "repayment_frequency": rec.new_repayment_frequency,
                "purpose": _("Consolidation of %s loans") % len(rec.loan_ids),
                "state": "approved",
                "approved_date": fields.Datetime.now(),
                "approved_by": self.env.uid,
            })
            
            rec.write({"new_loan_application_id": application.id})
            
            # Create loan
            loan = self.env["alba.loan"].create({
                "application_id": application.id,
                "loan_number": self.env["ir.sequence"].next_by_code("alba.loan.seq"),
                "principal_amount": rec.consolidated_amount,
                "interest_rate": rec.new_interest_rate,
                "interest_method": "flat_rate",  # Use flat rate for simplicity
                "tenure_months": rec.new_tenure_months,
                "repayment_frequency": rec.new_repayment_frequency,
                "disbursement_date": fields.Date.today(),
                "installment_amount": rec.new_emi,
                "outstanding_balance": rec.consolidated_amount,
                "state": "active",
                "journal_id": rec.journal_id.id,
            })
            
            loan.action_generate_schedule()
            loan.action_post_disbursement_entry()
            
            rec.write({
                "state": "disbursed",
                "new_loan_id": loan.id,
            })
            
            rec.message_post(body=_(
                "<b>CONSOLIDATED LOAN DISBURSED</b>: %s (Principal: %s %s)"
            ) % (loan.loan_number, rec.currency_id.symbol, rec.consolidated_amount))
    
    def action_complete(self):
        """Complete consolidation"""
        for rec in self:
            if rec.state != "disbursed":
                raise UserError(_("New loan must be disbursed first."))
            
            rec.write({"state": "completed"})
            
            # Send Email
            template = self.env.ref('alba_loans.email_template_consolidation', raise_if_not_found=False)
            if template:
                template.send_mail(rec.id, force_send=True)

            rec.message_post(body=Markup(_("<b>CONSOLIDATION COMPLETED</b>")))
    
    def action_reject(self):
        """Reject consolidation"""
        for rec in self:
            rec.write({"state": "rejected"})
            rec.message_post(body=_("Consolidation rejected."))

    def action_view_customer(self):
        """Navigate to the customer"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer"),
            "res_model": "alba.customer",
            "view_mode": "form",
            "res_id": self.customer_id.id,
        }

    def action_view_loans(self):
        """Navigate to the loans being consolidated"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loans"),
            "res_model": "alba.loan",
            "view_mode": "list,form",
            "domain": [("id", "in", self.loan_ids.ids)],
        }
