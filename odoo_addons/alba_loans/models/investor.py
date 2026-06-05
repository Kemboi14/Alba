# -*- coding: utf-8 -*-
"""
Alba Capital Investor Management Module
Handles investor accounts, interest calculations, and withdrawals
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta


class AlbaInvestor(models.Model):
    _name = "alba.investor"
    _description = "Alba Capital Investor"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"
    # IMPORT-EXPORT FIX: _rec_name uses display_name (store=True below) for human-readable export labels.
    # The alba_investors addon overrides this to investor_number for unambiguous import resolution.
    _rec_name = "display_name"

    # ─── Basic Information ──────────────────────────────────────────────────
    # ─── Partner link ──────────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        required=False,
        ondelete="restrict",
        index=True,
    )
    name = fields.Char(related="partner_id.name", store=True, readonly=False)
    display_name = fields.Char(
        string="Display Name",
        compute="_compute_display_name",
        store=True,   # IMPORT-EXPORT FIX: must be stored so it is searchable and exported correctly
        index=True,
    )
    investor_type = fields.Selection([
        ("individual", "Individual"),
        ("company", "Company"),
    ], string="Investor Type", required=True, default="individual")
    
    # ─── Identification (Related to Partner) ──────────────────────────────────
    id_number = fields.Char(related="partner_id.id_number", store=True, readonly=False)
    kra_pin = fields.Char(related="partner_id.kra_pin", store=True, readonly=False)
    registration_number = fields.Char(related="partner_id.registration_number", store=True, readonly=False)
    
    # ─── Contact Information (Related to Partner) ─────────────────────────────
    phone = fields.Char(related="partner_id.phone", store=True, readonly=False)
    email = fields.Char(related="partner_id.email", store=True, readonly=False)
    address = fields.Char(related="partner_id.street", string="Physical Address", readonly=False)
    
    bank_account_id = fields.Many2one(
        "res.partner.bank",
        string="Bank Account",
        domain="[('partner_id', '=', partner_id)]",
    )
    
    # ─── Investment Details ───────────────────────────────────────────────────
    investment_product = fields.Selection([
        ("fixed_deposit", "Fixed Deposit"),
        ("savings", "Savings Account"),
        ("term_deposit", "Term Deposit"),
    ], string="Investment Product", required=True, default="fixed_deposit")
    
    principal_amount = fields.Monetary(
        string="Principal Amount",
        currency_field="currency_id",
        required=False,
        default=0.0,
    )
    interest_rate = fields.Float(
        string="Annual Interest Rate (%)",
        digits=(5, 2),
        required=False,
        default=0.0,
    )
    tenure_months = fields.Integer(string="Tenure (Months)", default=12)
    
    # ─── Interest Configuration ───────────────────────────────────────────────
    interest_method = fields.Selection([
        ("simple", "Simple Interest"),
        ("compound_monthly", "Monthly Compounding"),
    ], string="Interest Method", default="simple")
    
    payout_frequency = fields.Selection([
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("at_maturity", "At Maturity"),
    ], string="Payout Frequency", default="monthly")
    
    # ─── Financial Tracking ───────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    
    accrued_interest = fields.Monetary(
        string="Accrued Interest",
        currency_field="currency_id",
        compute="_compute_interest",
        inverse="_inverse_accrued_interest",
        store=True,
        # IMPORT-EXPORT FIX
    )
    
    paid_interest = fields.Monetary(
        string="Paid Interest",
        currency_field="currency_id",
        default=0.0,
    )
    
    total_interest = fields.Monetary(
        string="Total Interest Earned",
        currency_field="currency_id",
        compute="_compute_totals",
        inverse="_inverse_total_interest",
        store=True,
        # IMPORT-EXPORT FIX
    )

    balance = fields.Monetary(
        string="Current Balance",
        currency_field="currency_id",
        compute="_compute_totals",
        inverse="_inverse_balance",
        store=True,
        # IMPORT-EXPORT FIX
    )
    
    # ─── Dates ────────────────────────────────────────────────────────────────
    start_date = fields.Date(string="Investment Start Date", required=True, default=fields.Date.today)
    maturity_date = fields.Date(string="Maturity Date", compute="_compute_maturity", store=True)
    last_interest_calculation = fields.Date(string="Last Interest Calculation")
    
    # ─── Status ───────────────────────────────────────────────────────────────
    state = fields.Selection([
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("matured", "Matured"),
        ("closed", "Closed"),
    ], string="Status", default="active")
    
    active = fields.Boolean(string="Active", default=True)
    
    # ─── Compliance ───────────────────────────────────────────────────────────
    is_pep = fields.Boolean(string="Politically Exposed Person", default=False)
    on_watchlist = fields.Boolean(string="On Watchlist", default=False)
    aml_cleared = fields.Boolean(string="AML Cleared", default=False)
    
    # ─── Relations ────────────────────────────────────────────────────────────
    transaction_ids = fields.One2many(
        "alba.investor.transaction",
        "investor_id",
        string="Transactions",
    )
    
    withdrawal_ids = fields.One2many(
        "alba.investor.withdrawal",
        "investor_id",
        string="Withdrawals",
    )
    
    # ─── Computed ─────────────────────────────────────────────────────────────
    transaction_count = fields.Integer(string="Transaction Count", compute="_compute_counts")
    
    # ─── Constraints ──────────────────────────────────────────────────────────
    _positive_principal = models.Constraint("CHECK(principal_amount >= 0)", "Principal amount must be positive or zero.")
    _positive_rate = models.Constraint("CHECK(interest_rate >= 0)", "Interest rate cannot be negative.")

    # ─── Compute Methods ──────────────────────────────────────────────────────
    @api.depends("name", "investor_type")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} ({rec.investor_type})"

    @api.model
    def _name_search(self, name, domain=None, operator="ilike", limit=None, order=None):
        # IMPORT-EXPORT FIX: search by display_name OR name so import can resolve Many2one links
        domain = domain or []
        if name:
            name_domain = ["|", ("display_name", operator, name), ("name", operator, name)]
            return self._search(name_domain + domain, limit=limit, order=order)
        return super()._name_search(name, domain=domain, operator=operator, limit=limit, order=order)
    
    @api.depends("start_date", "tenure_months")
    def _compute_maturity(self):
        for rec in self:
            if rec.start_date and rec.tenure_months:
                rec.maturity_date = rec.start_date + timedelta(days=rec.tenure_months * 30)
            else:
                rec.maturity_date = False
    
    @api.depends("principal_amount", "interest_rate", "interest_method", 
                 "start_date", "payout_frequency", "paid_interest")
    def _compute_interest(self):
        today = fields.Date.today()
        for rec in self:
            if not rec.start_date or rec.start_date > today:
                rec.accrued_interest = 0.0
                continue
            
            days_invested = (today - rec.start_date).days
            
            if rec.interest_method == "simple":
                # Simple interest: I = P × r × t
                annual_rate = rec.interest_rate / 100
                daily_rate = annual_rate / 365
                interest = rec.principal_amount * daily_rate * days_invested
            else:
                # Monthly compounding
                monthly_rate = (rec.interest_rate / 100) / 12
                months = days_invested / 30
                amount = rec.principal_amount
                interest = 0.0
                for _ in range(int(months)):
                    monthly_interest = amount * monthly_rate
                    interest += monthly_interest
                    amount += monthly_interest
            
            rec.accrued_interest = round(interest - rec.paid_interest, 2)
    
    @api.depends("principal_amount", "accrued_interest", "paid_interest")
    def _compute_totals(self):
        for rec in self:
            rec.total_interest = rec.accrued_interest + rec.paid_interest
            rec.balance = rec.principal_amount + rec.accrued_interest

    # IMPORT-EXPORT FIX: no-op inverses — import can write these; compute resets on trigger
    def _inverse_accrued_interest(self): pass
    def _inverse_total_interest(self): pass
    def _inverse_balance(self): pass
    
    def _compute_counts(self):
        for rec in self:
            rec.transaction_count = len(rec.transaction_ids)

    # ─── Actions ────────────────────────────────────────────────────────────────
    def action_post_monthly_interest(self):
        """Post monthly interest to investor account."""
        for rec in self:
            if rec.payout_frequency == "monthly" and rec.accrued_interest > 0:
                self.env["alba.investor.transaction"].create({
                    "investor_id": rec.id,
                    "transaction_type": "interest",
                    "amount": rec.accrued_interest,
                    "date": fields.Date.today(),
                    "description": f"Monthly interest payment",
                })
                rec.paid_interest += rec.accrued_interest
                rec.last_interest_calculation = fields.Date.today()
    
    def action_calculate_maturity(self):
        """Calculate and process maturity payout."""
        for rec in self:
            if rec.state == "active" and fields.Date.today() >= rec.maturity_date:
                total_payout = rec.principal_amount + rec.accrued_interest
                self.env["alba.investor.transaction"].create({
                    "investor_id": rec.id,
                    "transaction_type": "maturity",
                    "amount": total_payout,
                    "date": fields.Date.today(),
                    "description": f"Maturity payout - Principal: {rec.principal_amount}, Interest: {rec.accrued_interest}",
                })
                rec.write({"state": "matured"})
    
    def action_process_withdrawal(self, amount, withdrawal_type="partial"):
        """Process investor withdrawal with prorated interest."""
        self.ensure_one()
        if amount > self.balance:
            raise UserError(_("Withdrawal amount exceeds available balance."))
        
        # Calculate prorated interest
        prorated_interest = self.accrued_interest * (amount / self.balance)
        
        withdrawal = self.env["alba.investor.withdrawal"].create({
            "investor_id": self.id,
            "amount": amount,
            "prorated_interest": prorated_interest,
            "withdrawal_type": withdrawal_type,
            "date": fields.Date.today(),
            "state": "pending",
        })
        
        return withdrawal


class AlbaInvestorTransaction(models.Model):
    _name = "alba.investor.transaction"
    _description = "Investor Transaction"
    _order = "date desc, id desc"
    
    investor_id = fields.Many2one("alba.investor", string="Investor", required=True, ondelete="cascade")
    transaction_type = fields.Selection([
        ("deposit", "Deposit"),
        ("interest", "Interest Payment"),
        ("maturity", "Maturity Payout"),
        ("withdrawal", "Withdrawal"),
        ("top_up", "Top-up"),
    ], string="Transaction Type", required=True)
    
    amount = fields.Monetary(string="Amount", currency_field="currency_id", required=True)
    currency_id = fields.Many2one("res.currency", related="investor_id.currency_id", store=True)
    
    date = fields.Date(string="Date", required=True, default=fields.Date.today)
    description = fields.Text(string="Description")
    reference = fields.Char(string="Reference Number", copy=False)


class AlbaInvestorWithdrawal(models.Model):
    _name = "alba.investor.withdrawal"
    _description = "Investor Withdrawal Request"
    _order = "date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    
    investor_id = fields.Many2one("alba.investor", string="Investor", required=True, ondelete="cascade")
    withdrawal_type = fields.Selection([
        ("partial", "Partial Withdrawal"),
        ("full", "Full Withdrawal"),
    ], string="Withdrawal Type", required=True)
    
    amount = fields.Monetary(string="Principal Amount", currency_field="currency_id", required=True)
    prorated_interest = fields.Monetary(string="Prorated Interest", currency_field="currency_id")
    total_amount = fields.Monetary(string="Total Amount", currency_field="currency_id", compute="_compute_total")
    
    currency_id = fields.Many2one("res.currency", related="investor_id.currency_id", store=True)
    date = fields.Date(string="Request Date", default=fields.Date.today)
    
    state = fields.Selection([
        ("pending", "Pending Approval"),
        ("approved", "Approved"),
        ("processed", "Processed"),
        ("rejected", "Rejected"),
    ], string="Status", default="pending")
    
    approved_by = fields.Many2one("res.users", string="Approved By")
    processed_date = fields.Date(string="Processed Date")
    
    @api.depends("amount", "prorated_interest")
    def _compute_total(self):
        for rec in self:
            rec.total_amount = rec.amount + rec.prorated_interest
    
    def action_approve(self):
        for rec in self:
            rec.write({
                "state": "approved",
                "approved_by": self.env.uid,
            })
    
    def action_process(self):
        for rec in self:
            # Create transaction record
            self.env["alba.investor.transaction"].create({
                "investor_id": rec.investor_id.id,
                "transaction_type": "withdrawal",
                "amount": -rec.total_amount,
                "date": fields.Date.today(),
                "description": f"{rec.withdrawal_type} - Principal: {rec.amount}, Interest: {rec.prorated_interest}",
            })
            
            # Update investor
            rec.investor_id.principal_amount -= rec.amount
            rec.investor_id.paid_interest += rec.prorated_interest
            
            rec.write({
                "state": "processed",
                "processed_date": fields.Date.today(),
            })
    
    def action_reject(self):
        for rec in self:
            rec.state = "rejected"
