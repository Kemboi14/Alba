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
from markupsafe import Markup


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
        """Extend the base action_submit (state transition, KYC, credit score,
        auto-decisioning — see loan_application.py) with SoD submitter tracking.
        Must call super(): a same-named override with no super() call silently
        replaces the base method instead of extending it, which previously
        skipped every one of those checks whenever action_submit() was called.
        """
        for rec in self:
            rec.submitted_by_user_id = self.env.user
        return super().action_submit()

    def _user_has_role(self, group):
        """True if the current user belongs to `group` (a res.groups record)."""
        if not group:
            return False
        external_ids = group.get_external_id()
        group_xml_id = external_ids.get(group.id, "")
        if not group_xml_id:
            return bool(self.env["res.groups"].search(
                [("id", "=", group.id), ("users", "in", self.env.user.id)]
            ))
        return self.env.user.has_group(group_xml_id)

    def action_approve(self):
        """Extend the base action_approve (state transition, collateral/
        guarantor checks, next-step routing — see loan_application.py) with
        approval-authority enforcement, Segregation-of-Duties, and a real
        second-approval gate. Must call super() for the same reason as
        action_submit() above.
        """
        for rec in self:
            amount = rec.approved_amount or rec.requested_amount
            limit = self.env["alba.approval.limit"].get_approver_for_amount(
                "loan_application", amount
            )
            # The auto-decisioning engine (loan_application.py action_submit)
            # already gates on credit score + KYC + collateral/guarantor
            # blockers before calling this; it isn't a human approval at all,
            # so the manual authority/SoD/dual-sign-off checks don't apply.
            # Directors/system admins get the same admin-override bypass the
            # base action_approve() already grants for collateral/guarantor.
            bypass = rec.env.context.get("alba_auto_decision") or rec._has_admin_override()

            if not bypass and not self.env.user.has_approval_authority("loan_application", amount):
                raise UserError(
                    _(
                        "You do not have approval authority for %(currency)s %(amount)s. "
                        "This amount requires approval from: %(role)s."
                    )
                    % {
                        "currency": rec.currency_id.name,
                        "amount": f"{amount:,.2f}",
                        "role": limit.approver_group_id.name if limit and limit.approver_group_id else _("a higher role"),
                    }
                )

            if not bypass:
                sod_rule = self.env["alba.segregation.of.duties"].search(
                    [("process_type", "=", "loan"), ("active", "=", True)], limit=1
                )
                if sod_rule and sod_rule.enforce_different_user:
                    if rec.submitted_by_user_id and rec.submitted_by_user_id == self.env.user:
                        # Allow bypass for privileged groups (e.g. Director, Loan Manager Full)
                        user_group_ids = self.env.user.group_ids.ids
                        bypass_ids = sod_rule.bypass_group_ids.ids
                        if not (bypass_ids and any(g in user_group_ids for g in bypass_ids)):
                            raise UserError(
                                _("Segregation of Duties: You cannot approve a loan you submitted.")
                            )

            if not bypass and limit and limit.require_second_approval and not rec.second_approved_by_user_id:
                if not rec.approved_by_user_id:
                    # First leg: record the first approval and hold — do NOT
                    # run the base transition yet, so the application stays
                    # out of the "approved" state until a second, different
                    # approver signs off.
                    rec.write({
                        "approved_amount": amount,
                        "approved_by_user_id": self.env.user.id,
                        "approved_by_role_id": limit.approver_group_id.id if limit.approver_group_id else False,
                    })
                    rec.message_post(body=_(
                        "First approval recorded by %(user)s. A second approval from "
                        "%(role)s is required before this application can move to Approved."
                    ) % {
                        "user": self.env.user.name,
                        "role": limit.second_approver_group_id.name if limit.second_approver_group_id else _("another approver"),
                    })
                    continue

                if rec.approved_by_user_id == self.env.user:
                    raise UserError(
                        _("This application requires a second approval from a different approver.")
                    )
                second_group = limit.second_approver_group_id
                if second_group and not self._user_has_role(second_group):
                    raise UserError(
                        _("Second approval must come from role '%s'.") % second_group.name
                    )
                rec.write({
                    "second_approved_by_user_id": self.env.user.id,
                    "second_approved_by_role_id": second_group.id if second_group else False,
                })
            elif not rec.approved_by_user_id:
                # No dual-approval requirement (or auto-decision bypass) —
                # record the sole approval directly.
                rec.write({
                    "approved_by_user_id": self.env.user.id,
                    "approved_by_role_id": limit.approver_group_id.id if limit and limit.approver_group_id else False,
                })

            if not rec.approved_amount:
                rec.approved_amount = amount

            super(AlbaLoanApplication, rec).action_approve()

            rec.message_post(
                body=Markup(_("Application <b>approved</b> for %s %s by %s."))
                % (rec.currency_id.name, rec.approved_amount, self.env.user.name)
            )
        return True


class AccountMove(models.Model):
    """Extend journal entries with approval workflow"""
    
    _inherit = "account.move"
    
    alba_loan_id = fields.Many2one("alba.loan", string="Alba Loan", index=True)
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
            if ref.startswith(("DISB/", "RPMT/", "REV/", "ACCR/", "PROV/", "WRT/")):
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
        return super().action_write_off()


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
