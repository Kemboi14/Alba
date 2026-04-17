# -*- coding: utf-8 -*-
"""
Alba Capital Approval Limits & Workflow Configuration
Based on Business Requirements Questionnaire Section B

Implements:
- Approval limits by role
- Segregation of duties rules
- Workflow stage validations
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AlbaApprovalLimit(models.Model):
    """Configure approval limits by user role"""
    
    _name = "alba.approval.limit"
    _description = "Approval Limits Configuration"
    _order = "min_amount asc"
    
    name = fields.Char(string="Rule Name", required=True)
    
    # Process Type
    process_type = fields.Selection([
        ("loan_application", "Loan Application"),
        ("loan_disbursement", "Loan Disbursement"),
        ("write_off", "Loan Write-Off"),
        ("journal_entry", "Journal Entry"),
        ("investor_withdrawal", "Investor Withdrawal"),
        ("restructure", "Loan Restructure"),
    ], string="Process Type", required=True)
    
    # Amount Range
    min_amount = fields.Monetary(string="Minimum Amount", required=True)
    max_amount = fields.Monetary(string="Maximum Amount", required=True)
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    
    # Approver Group
    approver_group_id = fields.Many2one("res.groups", string="Approver Role", required=True)
    
    # Secondary Approval (for high amounts)
    require_second_approval = fields.Boolean(string="Require Second Approval")
    second_approver_group_id = fields.Many2one("res.groups", string="Second Approver Role")
    
    # Active
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    
    _positive_amounts = models.Constraint(
        "CHECK(min_amount >= 0 AND max_amount > min_amount)",
        "Maximum amount must be greater than minimum amount.",
    )
    
    @api.model
    def get_approver_for_amount(self, process_type, amount):
        """Get the required approver group for a given amount"""
        limit = self.search([
            ("process_type", "=", process_type),
            ("min_amount", "<=", amount),
            ("max_amount", ">=", amount),
            ("active", "=", True),
        ], limit=1, order="min_amount desc")
        
        return limit


class AlbaWorkflowRule(models.Model):
    """Workflow stage transition rules"""
    
    _name = "alba.workflow.rule"
    _description = "Workflow Transition Rules"
    
    name = fields.Char(string="Rule Name", required=True)
    
    # Model and States
    model_name = fields.Selection([
        ("alba.loan.application", "Loan Application"),
        ("alba.loan", "Active Loan"),
        ("alba.investor.withdrawal", "Investor Withdrawal"),
    ], string="Process", required=True)
    
    from_state = fields.Char(string="From State", required=True)
    to_state = fields.Char(string="To State", required=True)
    
    # Required Group
    required_group_id = fields.Many2one("res.groups", string="Required Role")
    
    # Conditions
    condition_domain = fields.Char(string="Condition Domain", help="Domain filter for valid transitions")
    
    # Active
    active = fields.Boolean(default=True)


class AlbaSegregationOfDuties(models.Model):
    """Segregation of Duties Rules"""
    
    _name = "alba.segregation.of.duties"
    _description = "Segregation of Duties Configuration"
    
    name = fields.Char(string="Rule Name", required=True)
    
    process_type = fields.Selection([
        ("loan", "Loan Process"),
        ("journal", "Journal Entry"),
        ("payroll", "Payroll"),
        ("investor", "Investor Transaction"),
        ("document", "Document Approval"),
    ], string="Process Type", required=True)
    
    # Creator Group (cannot approve)
    creator_group_id = fields.Many2one("res.groups", string="Creator/Preparer Role", required=True)
    
    # Approver Group (must be different from creator)
    approver_group_id = fields.Many2one("res.groups", string="Approver Role", required=True)
    
    # Validation
    enforce_different_user = fields.Boolean(string="Enforce Different User", default=True,
        help="If checked, the approver must be a different user than the creator")

    # Groups that are allowed to bypass the SoD restriction (e.g. Director, Loan Manager Full)
    bypass_group_ids = fields.Many2many(
        "res.groups",
        "alba_sod_bypass_group_rel",
        "sod_id",
        "group_id",
        string="Bypass Groups",
        help="Users belonging to any of these groups can approve even if they submitted the loan.",
    )

    active = fields.Boolean(default=True)
    
    @api.constrains("creator_group_id", "approver_group_id")
    def _check_different_groups(self):
        for rule in self:
            if rule.creator_group_id == rule.approver_group_id:
                raise ValidationError(_("Creator and Approver roles must be different for SoD compliance."))


class ResUsers(models.Model):
    """Extend users with approval authority checks"""

    _inherit = "res.users"

    def has_approval_authority(self, process_type, amount):
        """
        Check if the current user has authority to approve a given amount.
        Returns True when no limits are configured (permissive default) so that
        the system works out of the box without mandatory approval limit setup.
        """
        self.ensure_one()
        limit = self.env["alba.approval.limit"].get_approver_for_amount(process_type, amount)
        if not limit:
            # No approval limit rule found — allow by default
            return True
        group = limit.approver_group_id
        if not group:
            return True
        # get_external_id() returns {id: 'module.xml_id'}
        external_ids = group.get_external_id()
        group_xml_id = external_ids.get(group.id, "")
        if not group_xml_id:
            # Fallback: direct group membership check using proper API
            return self.env['res.groups'].search([('id', '=', group.id), ('users', 'in', self.id)]).exists()
        return self.has_group(group_xml_id)

    def can_approve_transition(self, model_name, from_state, to_state):
        """Check if the user can drive a workflow transition."""
        self.ensure_one()
        rule = self.env["alba.workflow.rule"].search(
            [
                ("model_name", "=", model_name),
                ("from_state", "=", from_state),
                ("to_state", "=", to_state),
                ("active", "=", True),
            ],
            limit=1,
        )
        if not rule or not rule.required_group_id:
            return True  # No restrictions
        group = rule.required_group_id
        external_ids = group.get_external_id()
        group_xml_id = external_ids.get(group.id, "")
        if not group_xml_id:
            return self.env['res.groups'].search([('id', '=', group.id), ('users', 'in', self.id)]).exists()
        return self.has_group(group_xml_id)


class AlbaLoanApplication(models.Model):
    """Extend loan application with approval workflow"""
    
    _inherit = "alba.loan.application"
    
    # Approval Tracking
    approved_by_user_id = fields.Many2one("res.users", string="Approved By (User)", readonly=True, copy=False)
    approved_by_role_id = fields.Many2one("res.groups", string="Approver Role", readonly=True, copy=False)
    
    # Second Approval (for high amounts)
    second_approved_by_user_id = fields.Many2one("res.users", string="Second Approved By", readonly=True, copy=False)
    second_approved_by_role_id = fields.Many2one("res.groups", string="Second Approver Role", readonly=True, copy=False)
    
    # SoD Tracking
    submitted_by_user_id = fields.Many2one("res.users", string="Submitted By", readonly=True, copy=False)
    submitted_by_role_id = fields.Many2one("res.groups", string="Submitter Role", readonly=True, copy=False)
    
    def action_submit(self):
        """Submit application with SoD tracking"""
        for rec in self:
            rec.submitted_by_user_id = self.env.user
            rec.write({
                "state": "submitted",
                "submitted_date": fields.Datetime.now(),
            })
    
    def action_approve(self):
        """Approve with validation checks"""
        for rec in self:
            # Check SoD - approver cannot be submitter (only when rule is configured)
            sod_rule = self.env["alba.segregation.of.duties"].search(
                [("process_type", "=", "loan"), ("active", "=", True)], limit=1
            )
            if sod_rule and sod_rule.enforce_different_user:
                if rec.submitted_by_user_id and rec.submitted_by_user_id == self.env.user:
                    # Allow bypass for privileged groups (e.g. Director, Loan Manager Full)
                    user_groups = self.env['res.groups'].search([('users', 'in', self.env.user.id)])
                    user_group_ids = user_groups.ids
                    bypass_ids = sod_rule.bypass_group_ids.ids
                    if not (bypass_ids and any(g in user_group_ids for g in bypass_ids)):
                        raise UserError(
                            _("Segregation of Duties: You cannot approve a loan you submitted.")
                        )
            limit = self.env["alba.approval.limit"].get_approver_for_amount(
                "loan_application", rec.requested_amount
            )
            if not rec.approved_amount:
                rec.approved_amount = rec.requested_amount
            rec.write({
                "state": "approved",
                "approved_date": fields.Datetime.now(),
                "approved_by_user_id": self.env.user.id,
                "approved_by_role_id": limit.approver_group_id.id if limit else False,
            })
            rec.message_post(
                body=_("Application <b>approved</b> for %s %s by %s.")
                % (rec.currency_id.name, rec.approved_amount, self.env.user.name)
            )
            if limit and limit.require_second_approval:
                rec.message_post(
                    body=_("First approval by %s. Second approval required from %s.") % (
                        self.env.user.name, limit.second_approver_group_id.name
                    )
                )


class AccountMove(models.Model):
    """Extend journal entries with approval workflow"""
    
    _inherit = "account.move"
    
    prepared_by_user_id = fields.Many2one("res.users", string="Prepared By", readonly=True, copy=False)
    approved_by_user_id = fields.Many2one("res.users", string="Approved By", readonly=True, copy=False)
    
    def action_post(self):
        """Override post to enforce approval workflow.
        System-generated disbursement/repayment entries (prefixed DISB/ or RPMT/)
        bypass the approval check so automated loan processing is never blocked.
        """
        for move in self:
            # Skip system-generated entries
            ref = move.ref or ""
            if ref.startswith(("DISB/", "RPMT/", "REV/")):
                continue
            # Skip entries with no ref (auto-generated by Odoo itself)
            if not ref:
                continue
            total_amount = abs(sum(move.line_ids.mapped("balance")))
            if not self.env.user.has_approval_authority("journal_entry", total_amount):
                raise UserError(
                    _("This journal entry requires approval. "
                      "Amount KES %s exceeds your approval limit.") % f"{total_amount:,.2f}"
                )
        return super().action_post()


class AlbaLoan(models.Model):
    """Extend active loans with write-off approval"""
    
    _inherit = "alba.loan"
    
    def action_write_off(self):
        """Write-off with Director approval required"""
        for rec in self:
            if not self.env.user.has_group("alba_loans.group_director"):
                raise UserError(
                    _("Loan write-off requires Director approval. "
                      "Please request approval from a Director.")
                )
            rec.write({"state": "written_off"})
            rec.message_post(body=_("Loan written off by Director: %s") % self.env.user.name)


# Default Approval Limits Data
# This should be loaded via data file
DEFAULT_APPROVAL_LIMITS = [
    {
        "name": "Loan Application - Officer Level",
        "process_type": "loan_application",
        "min_amount": 0,
        "max_amount": 100000,
        "approver_group_id": "alba_loans.group_operations_manager",
        "require_second_approval": False,
    },
    {
        "name": "Loan Application - Manager Level",
        "process_type": "loan_application",
        "min_amount": 100001,
        "max_amount": 500000,
        "approver_group_id": "alba_loans.group_operations_manager",
        "require_second_approval": False,
    },
    {
        "name": "Loan Application - Director Level",
        "process_type": "loan_application",
        "min_amount": 500001,
        "max_amount": 999999999,
        "approver_group_id": "alba_loans.group_director",
        "require_second_approval": True,
        "second_approver_group_id": "alba_loans.group_director",
    },
    {
        "name": "Journal Entry - Standard",
        "process_type": "journal_entry",
        "min_amount": 0,
        "max_amount": 50000,
        "approver_group_id": "alba_loans.group_finance_admin",
        "require_second_approval": False,
    },
    {
        "name": "Journal Entry - Large",
        "process_type": "journal_entry",
        "min_amount": 50001,
        "max_amount": 999999999,
        "approver_group_id": "alba_loans.group_director",
        "require_second_approval": False,
    },
    {
        "name": "Write-Off - Director Only",
        "process_type": "write_off",
        "min_amount": 0,
        "max_amount": 999999999,
        "approver_group_id": "alba_loans.group_director",
        "require_second_approval": False,
    },
]
