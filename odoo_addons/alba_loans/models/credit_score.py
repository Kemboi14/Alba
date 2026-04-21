# -*- coding: utf-8 -*-
"""
Alba Capital Rule-Based Credit Scoring
Manual rule-based scoring (not ML)
Score 300-850 range, auto-recommend based on thresholds
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from datetime import date, timedelta


class AlbaCreditScoreRule(models.Model):
    """Configuration for credit scoring rules"""
    
    _name = "alba.credit.score.rule"
    _description = "Credit Score Rule"
    _order = "sequence, id"
    
    name = fields.Char(string="Rule Name", required=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(default=True)
    
    # Rule Type
    rule_type = fields.Selection([
        ("age", "Age"),
        ("income", "Monthly Income"),
        ("employment_stability", "Employment Stability"),
        ("repayment_history", "Repayment History"),
        ("existing_loans", "Existing Loans"),
        ("collateral", "Collateral Available"),
        ("guarantor", "Guarantor Available"),
        ("kyc_completeness", "KYC Completeness"),
    ], string="Rule Type", required=True)
    
    # Value Range
    min_value = fields.Float(string="Minimum Value")
    max_value = fields.Float(string="Maximum Value")
    
    # Points
    points = fields.Integer(string="Points", required=True, help="Points awarded if condition is met")
    weight = fields.Integer(string="Weight", default=1, help="Importance multiplier (1-10)")
    
    # Description
    description = fields.Text(string="Description", help="Explanation of this rule")


class AlbaCreditScore(models.Model):
    """Credit Score calculation per loan application"""
    
    _name = "alba.credit.score"
    _description = "Credit Score"
    _order = "score_date desc"
    _inherit = ["mail.thread"]
    
    # Identification
    name = fields.Char(string="Reference", compute="_compute_name", store=True)
    
    # Links
    application_id = fields.Many2one(
        "alba.loan.application",
        string="Loan Application",
        required=True,
        ondelete="cascade",
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="application_id.customer_id",
        store=True,
    )
    
    # Score Date
    score_date = fields.Datetime(
        string="Scored On",
        default=lambda self: fields.Datetime.now(),
        readonly=True,
    )
    calculated_by = fields.Many2one(
        "res.users",
        string="Calculated By",
        default=lambda self: self.env.user,
        readonly=True,
    )
    
    # Scores
    total_score = fields.Integer(
        string="Total Score",
        compute="_compute_total_score",
        store=True,
    )
    max_possible_score = fields.Integer(
        string="Max Possible",
        default=100,
    )
    score_percentage = fields.Float(
        string="Score %",
        compute="_compute_total_score",
        store=True,
    )
    
    # Risk Category
    risk_category = fields.Selection([
        ("excellent", "Excellent (>80%)"),
        ("good", "Good (70-80%)"),
        ("fair", "Fair (60-70%)"),
        ("poor", "Poor (<60%)"),
    ], string="Risk Category", compute="_compute_total_score", store=True)
    
    # Recommendation
    recommendation = fields.Selection([
        ("auto_approve", "Auto-Approve"),
        ("approve", "Recommend Approval"),
        ("review", "Manual Review Required"),
        ("reject", "Recommend Rejection"),
    ], string="Recommendation", compute="_compute_total_score", store=True)
    
    # Rule Breakdown
    line_ids = fields.One2many(
        "alba.credit.score.line",
        "credit_score_id",
        string="Score Breakdown",
    )
    
    # Override
    overridden = fields.Boolean(string="Score Overridden", default=False)
    override_by = fields.Many2one("res.users", string="Overridden By")
    override_date = fields.Datetime(string="Override Date")
    override_reason = fields.Text(string="Override Reason")
    manual_risk_category = fields.Selection([
        ("excellent", "Excellent"),
        ("good", "Good"),
        ("fair", "Fair"),
        ("poor", "Poor"),
    ], string="Manual Risk Category")
    manual_recommendation = fields.Selection([
        ("auto_approve", "Auto-Approve"),
        ("approve", "Recommend Approval"),
        ("review", "Manual Review Required"),
        ("reject", "Recommend Rejection"),
    ], string="Manual Recommendation")
    
    # Final Decision (after override)
    final_risk_category = fields.Selection([
        ("excellent", "Excellent"),
        ("good", "Good"),
        ("fair", "Fair"),
        ("poor", "Poor"),
    ], string="Final Risk Category", compute="_compute_final", store=True)
    final_recommendation = fields.Selection([
        ("auto_approve", "Auto-Approve"),
        ("approve", "Recommend Approval"),
        ("review", "Manual Review Required"),
        ("reject", "Recommend Rejection"),
    ], string="Final Recommendation", compute="_compute_final", store=True)
    
    # =========================================================================
    # Compute Methods
    # =========================================================================
    
    @api.depends("application_id", "score_date")
    def _compute_name(self):
        for rec in self:
            if rec.application_id:
                rec.name = _("Credit Score - %s") % rec.application_id.application_number
            else:
                rec.name = "Credit Score"
    
    @api.depends("line_ids", "line_ids.points_earned", "overridden", "manual_risk_category")
    def _compute_total_score(self):
        for rec in self:
            if rec.overridden:
                # Use manual override
                rec.total_score = 0
                rec.score_percentage = 0
                rec.risk_category = rec.manual_risk_category
                rec.recommendation = rec.manual_recommendation
            else:
                total = sum(rec.line_ids.mapped("points_earned"))
                rec.total_score = total
                rec.max_possible_score = sum(rec.line_ids.mapped("max_points"))
                
                if rec.max_possible_score > 0:
                    rec.score_percentage = (total / rec.max_possible_score) * 100
                else:
                    rec.score_percentage = 0
                
                # Determine risk category
                pct = rec.score_percentage
                if pct >= 80:
                    rec.risk_category = "excellent"
                elif pct >= 70:
                    rec.risk_category = "good"
                elif pct >= 60:
                    rec.risk_category = "fair"
                else:
                    rec.risk_category = "poor"
                
                # Determine recommendation
                if pct >= 85:
                    rec.recommendation = "auto_approve"
                elif pct >= 70:
                    rec.recommendation = "approve"
                elif pct >= 50:
                    rec.recommendation = "review"
                else:
                    rec.recommendation = "reject"
    
    @api.depends("overridden", "risk_category", "recommendation", "manual_risk_category", "manual_recommendation")
    def _compute_final(self):
        for rec in self:
            if rec.overridden:
                rec.final_risk_category = rec.manual_risk_category
                rec.final_recommendation = rec.manual_recommendation
            else:
                rec.final_risk_category = rec.risk_category
                rec.final_recommendation = rec.recommendation
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def action_calculate(self):
        """Calculate credit score based on rules"""
        for rec in self:
            # Clear existing lines
            rec.line_ids.unlink()
            
            # Get all active rules
            rules = self.env["alba.credit.score.rule"].search([("active", "=", True)])
            
            customer = rec.customer_id
            application = rec.application_id
            
            lines = []
            for rule in rules:
                points = 0
                max_points = rule.points * rule.weight
                
                # Evaluate rule
                if rule.rule_type == "age":
                    if customer.date_of_birth:
                        age = (date.today() - customer.date_of_birth).days / 365.25
                        if rule.min_value <= age <= rule.max_value:
                            points = rule.points
                
                elif rule.rule_type == "income":
                    income = customer.monthly_income or 0
                    if rule.min_value <= income <= rule.max_value:
                        points = rule.points
                
                elif rule.rule_type == "employment_stability":
                    months = customer.months_employed or 0
                    if rule.min_value <= months <= rule.max_value:
                        points = rule.points
                
                elif rule.rule_type == "repayment_history":
                    # Count past loans and repayment history
                    past_loans = self.env["alba.loan"].search([
                        ("customer_id", "=", customer.id),
                        ("state", "=", "closed"),
                    ])
                    good_loans = len(past_loans)
                    if rule.min_value <= good_loans <= rule.max_value:
                        points = rule.points
                
                elif rule.rule_type == "existing_loans":
                    active_loans = self.env["alba.loan"].search_count([
                        ("customer_id", "=", customer.id),
                        ("state", "=", "active"),
                    ])
                    # Fewer existing loans = better score
                    if active_loans == 0 and rule.rule_type == "existing_loans":
                        points = rule.points
                
                elif rule.rule_type == "collateral":
                    # Check if collateral provided
                    collateral_count = len(application.loan_guarantor_ids)  # Simplified check
                    if collateral_count > 0:
                        points = rule.points
                
                elif rule.rule_type == "guarantor":
                    guarantor_count = len(application.loan_guarantor_ids.filtered(lambda g: g.status == "confirmed"))
                    if guarantor_count > 0:
                        points = rule.points
                
                elif rule.rule_type == "kyc_completeness":
                    # Check KYC completeness
                    kyc_fields = [customer.id_number, customer.employer_name, customer.monthly_income]
                    filled = sum(1 for f in kyc_fields if f)
                    if rule.min_value <= filled <= rule.max_value:
                        points = rule.points
                
                lines.append((0, 0, {
                    "rule_id": rule.id,
                    "rule_type": rule.rule_type,
                    "rule_name": rule.name,
                    "points_earned": points * rule.weight,
                    "max_points": max_points,
                    "description": rule.description,
                }))
            
            rec.write({"line_ids": lines})
            rec.message_post(body=_("Credit score calculated based on %s rules.") % len(rules))
    
    def action_override(self):
        """Open override wizard"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Override Credit Score"),
            "res_model": "alba.credit.score.override.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_credit_score_id": self.id,
            },
        }


class AlbaCreditScoreLine(models.Model):
    """Individual scoring rule results"""
    
    _name = "alba.credit.score.line"
    _description = "Credit Score Line"
    _order = "id"
    
    credit_score_id = fields.Many2one(
        "alba.credit.score",
        string="Credit Score",
        required=True,
        ondelete="cascade",
    )
    
    rule_id = fields.Many2one("alba.credit.score.rule", string="Rule")
    rule_type = fields.Selection(related="rule_id.rule_type", store=True)
    rule_name = fields.Char(string="Rule Name")
    
    points_earned = fields.Integer(string="Points Earned")
    max_points = fields.Integer(string="Max Points")
    percentage = fields.Float(
        string="Percentage",
        compute="_compute_percentage",
        store=True,
    )
    
    description = fields.Text(string="Details")
    
    @api.depends("points_earned", "max_points")
    def _compute_percentage(self):
        for rec in self:
            if rec.max_points > 0:
                rec.percentage = (rec.points_earned / rec.max_points) * 100
            else:
                rec.percentage = 0


class AlbaCreditScoreOverrideWizard(models.TransientModel):
    """Wizard to override credit score"""
    
    _name = "alba.credit.score.override.wizard"
    _description = "Credit Score Override Wizard"
    
    credit_score_id = fields.Many2one(
        "alba.credit.score",
        string="Credit Score",
        required=True,
    )
    
    current_score = fields.Integer(
        string="Current Score",
        related="credit_score_id.total_score",
        readonly=True,
    )
    current_risk = fields.Selection(
        related="credit_score_id.risk_category",
        string="Current Risk",
        readonly=True,
    )
    current_recommendation = fields.Selection(
        related="credit_score_id.recommendation",
        string="Current Recommendation",
        readonly=True,
    )
    
    override_reason = fields.Text(
        string="Override Reason",
        required=True,
    )
    
    manual_risk_category = fields.Selection([
        ("excellent", "Excellent"),
        ("good", "Good"),
        ("fair", "Fair"),
        ("poor", "Poor"),
    ], string="Manual Risk Category", required=True)
    
    manual_recommendation = fields.Selection([
        ("auto_approve", "Auto-Approve"),
        ("approve", "Recommend Approval"),
        ("review", "Manual Review Required"),
        ("reject", "Recommend Rejection"),
    ], string="Manual Recommendation", required=True)
    
    def action_confirm_override(self):
        """Confirm the override"""
        self.ensure_one()
        
        self.credit_score_id.write({
            "overridden": True,
            "override_by": self.env.user.id,
            "override_date": fields.Datetime.now(),
            "override_reason": self.override_reason,
            "manual_risk_category": self.manual_risk_category,
            "manual_recommendation": self.manual_recommendation,
        })
        
        self.credit_score_id.message_post(body=_(
            "<b>SCORE OVERRIDDEN</b><br/>"
            "Original: %s / %s<br/>"
            "Override: %s / %s<br/>"
            "Reason: %s"
        ) % (
            dict(self.credit_score_id._fields["risk_category"].selection).get(self.current_risk),
            dict(self.credit_score_id._fields["recommendation"].selection).get(self.current_recommendation),
            dict(self.credit_score_id._fields["risk_category"].selection).get(self.manual_risk_category),
            dict(self.credit_score_id._fields["recommendation"].selection).get(self.manual_recommendation),
            self.override_reason,
        ))
        
        return {"type": "ir.actions.act_window_close"}
