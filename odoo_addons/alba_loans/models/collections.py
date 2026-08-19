# -*- coding: utf-8 -*-
"""
Alba Capital Collections & Recovery Workflow
Based on Business Requirements Questionnaire Section D

Implements escalation buckets:
- 1–30 days: Reminders
- 31–60 days: Collections
- 61–90 days: Recovery
- 90+ days: Legal/NPL
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from markupsafe import Markup
from datetime import date, timedelta


class AlbaLoanCollectionStage(models.Model):
    """Track loan collection/recovery stages"""
    
    _name = "alba.loan.collection.stage"
    _description = "Loan Collection Stage"
    _order = "stage_number asc"
    
    STAGE_REMINDER = "reminder"  # 1-30 days
    STAGE_COLLECTION = "collection"  # 31-60 days
    STAGE_RECOVERY = "recovery"  # 61-90 days
    STAGE_LEGAL = "legal"  # 90+ days
    
    name = fields.Char(string="Stage Name", required=True)
    stage_code = fields.Selection([
        (STAGE_REMINDER, "1-30 Days (Reminder)"),
        (STAGE_COLLECTION, "31-60 Days (Collections)"),
        (STAGE_RECOVERY, "61-90 Days (Recovery)"),
        (STAGE_LEGAL, "90+ Days (Legal)"),
    ], string="Stage Code", required=True)
    
    stage_number = fields.Integer(string="Stage Order", required=True,
        help="Order of escalation (1=Reminder, 2=Collection, etc.)")
    
    # Days range
    min_days_overdue = fields.Integer(string="Min Days Overdue", required=True)
    max_days_overdue = fields.Integer(string="Max Days Overdue", required=True)
    
    # Actions
    auto_send_reminder = fields.Boolean(string="Auto Send Reminder", default=False)
    reminder_template_id = fields.Many2one("mail.template", string="Reminder Email Template")
    sms_template = fields.Text(string="SMS Template")
    
    # Escalation
    escalate_to = fields.Many2one("res.groups", string="Escalate To Role")
    create_activity = fields.Boolean(string="Create Activity", default=False)
    activity_type_id = fields.Many2one("mail.activity.type", string="Activity Type")
    
    # Fees
    additional_penalty_rate = fields.Float(string="Additional Penalty Rate (%)", default=0.0,
        help="Additional penalty on top of standard rate for this stage")
    
    active = fields.Boolean(default=True)


class AlbaLoanCollectionLog(models.Model):
    """Log all collection activities"""
    
    _name = "alba.loan.collection.log"
    _description = "Collection Activity Log"
    _order = "create_date desc"
    
    loan_id = fields.Many2one("alba.loan", string="Loan", required=True, ondelete="cascade")
    customer_id = fields.Many2one("alba.customer", related="loan_id.customer_id", store=True)
    
    # Activity
    activity_type = fields.Selection([
        ("call", "Phone Call"),
        ("email", "Email"),
        ("sms", "SMS"),
        ("visit", "Field Visit"),
        ("letter", "Demand Letter"),
        ("legal_notice", "Legal Notice"),
        ("employer_contact", "Employer Contact"),
        ("guarantor_contact", "Guarantor Contact"),
        ("payment", "Payment Received"),
        ("restructure", "Restructure"),
        ("write_off", "Write-Off"),
    ], string="Activity Type", required=True)
    
    # Details
    activity_date = fields.Date(string="Activity Date", required=True, default=fields.Date.today)
    description = fields.Text(string="Description")
    outcome = fields.Selection([
        ("successful", "Successful"),
        ("no_response", "No Response"),
        ("promised_payment", "Promised Payment"),
        ("disputed", "Disputed"),
        ("refused", "Refused"),
        ("escalated", "Escalated"),
    ], string="Outcome")
    
    # Follow-up
    follow_up_required = fields.Boolean(string="Follow-up Required")
    follow_up_date = fields.Date(string="Follow-up Date")
    
    # User
    user_id = fields.Many2one("res.users", string="Handled By", default=lambda self: self.env.user)
    
    # Attachments
    attachment_ids = fields.Many2many("ir.attachment", string="Attachments")
    
    # Notification
    customer_notified = fields.Boolean(string="Customer Notified")
    notification_sent = fields.Datetime(string="Notification Sent")


class AlbaLoan(models.Model):
    """Extend loans with collection workflow"""
    
    _inherit = "alba.loan"
    
    # Collection Stage
    collection_stage_id = fields.Many2one("alba.loan.collection.stage", 
        string="Collection Stage", compute="_compute_collection_stage", store=True)
    collection_stage_code = fields.Selection(related="collection_stage_id.stage_code", store=True)
    
    # Collection History
    collection_log_ids = fields.One2many("alba.loan.collection.log", "loan_id", string="Collection History")
    collection_call_count = fields.Integer(string="Collection Calls", compute="_compute_collection_stats")
    last_collection_activity = fields.Date(string="Last Collection Activity", compute="_compute_collection_stats")
    
    # Escalation
    escalated_to_legal = fields.Boolean(string="Escalated to Legal", default=False)
    legal_escalation_date = fields.Date(string="Legal Escalation Date")
    legal_remarks = fields.Text(string="Legal Remarks")
    
    # NPL
    npl_classification_date = fields.Date(string="NPL Classification Date")
    
    @api.depends("days_in_arrears")
    def _compute_collection_stage(self):
        """Auto-assign collection stage based on days overdue"""
        for rec in self:
            if rec.days_in_arrears <= 0:
                rec.collection_stage_id = False
            else:
                stage = self.env["alba.loan.collection.stage"].search([
                    ("min_days_overdue", "<=", rec.days_in_arrears),
                    ("max_days_overdue", ">=", rec.days_in_arrears),
                    ("active", "=", True),
                ], limit=1, order="stage_number asc")
                rec.collection_stage_id = stage.id if stage else False
    
    @api.depends("collection_log_ids")
    def _compute_collection_stats(self):
        """Compute collection statistics"""
        for rec in self:
            calls = rec.collection_log_ids.filtered(lambda x: x.activity_type == "call")
            rec.collection_call_count = len(calls)
            rec.last_collection_activity = rec.collection_log_ids and max(
                rec.collection_log_ids.mapped("activity_date")
            ) or False
    
    def action_log_collection_activity(self, activity_type, description, outcome=False):
        """Log a collection activity"""
        self.ensure_one()
        
        log = self.env["alba.loan.collection.log"].create({
            "loan_id": self.id,
            "activity_type": activity_type,
            "description": description,
            "outcome": outcome,
            "activity_date": fields.Date.today(),
        })
        
        # Post message to loan
        self.message_post(body=_("Collection Activity: %s - %s") % (activity_type, description))
        
        return log
    
    def action_send_collection_reminder(self):
        """Send automated collection reminder"""
        self.ensure_one()
        
        if not self.collection_stage_id or not self.collection_stage_id.auto_send_reminder:
            return False
        
        template = self.collection_stage_id.reminder_template_id
        if template:
            template.send_mail(self.id, force_send=True)
        
        # Log the activity
        self.action_log_collection_activity(
            "email",
            _("Automated %s reminder sent") % self.collection_stage_id.name,
            "successful"
        )
        
        return True
    
    def action_escalate_to_legal(self):
        """Escalate loan to legal department"""
        self.ensure_one()
        
        if self.days_in_arrears < 90:
            raise UserError(_("Loans can only be escalated to legal after 90 days overdue."))
        
        self.write({
            "escalated_to_legal": True,
            "legal_escalation_date": fields.Date.today(),
            "state": "loss",
        })
        
        # Create activity for legal team
        self.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=self.env.ref("alba_loans.group_director").users[0].id if self.env.ref("alba_loans.group_director").users else self.env.user.id,
            summary=_("Legal action required for %s") % self.loan_number,
            note=_("Loan %s is %s days overdue and has been escalated to legal.") % (self.loan_number, self.days_in_arrears),
        )
        
        # Log the escalation
        self.action_log_collection_activity(
            "legal_notice",
            _("Escalated to legal department"),
            "escalated"
        )
        
        self.message_post(body=Markup(_("<b>ESCALATED TO LEGAL</b><br/>Loan escalated to legal department after %s days overdue.")) % self.days_in_arrears)


class AlbaLoanCollectionCron(models.Model):
    """Cron job for automated collection activities"""
    
    _name = "alba.loan.collection.cron"
    _description = "Collection Automation"
    
    @api.model
    def cron_process_collection_stages(self):
        """Daily cron to process collection stages and send reminders"""
        import logging as _logging
        _logger = _logging.getLogger(__name__)

        # Fix: correct field is days_in_arrears (days_overdue does not exist)
        overdue_loans = self.env["alba.loan"].search([
            ("state", "not in", ["draft", "closed", "written_off"]),
            ("days_in_arrears", ">", 0),
        ])

        reminders_sent = 0
        for loan in overdue_loans:
            # Recompute collection stage from current arrears
            loan._compute_collection_stage()

            if not loan.collection_stage_id:
                continue

            stage = loan.collection_stage_id

            # ── Email & SMS reminders ──────────────────────────────────────────
            if stage.auto_send_reminder:
                try:
                    sent = loan.action_send_collection_reminder()
                    if sent:
                        reminders_sent += 1
                except Exception as e:
                    _logger.warning("Failed to send collection reminders for %s: %s", loan.loan_number, e)

            # ── Activity creation ─────────────────────────────────────────────
            if stage.create_activity and stage.activity_type_id:
                existing = loan.activity_ids.filtered(
                    lambda a: a.activity_type_id == stage.activity_type_id
                    and not a.date_done
                )
                if not existing:
                    responsible = (
                        stage.escalate_to.users[:1].id
                        if stage.escalate_to and stage.escalate_to.users
                        else loan.create_uid.id
                    )
                    loan.activity_schedule(
                        stage.activity_type_id.id,
                        user_id=responsible,
                        summary=_("%s follow-up required for %s") % (stage.name, loan.loan_number),
                    )

        _logger.info("cron_process_collection_stages: sent %d reminder(s).", reminders_sent)
        return True


# Default Collection Stages Data
DEFAULT_COLLECTION_STAGES = [
    {
        "name": "Reminder Stage (1-30 Days)",
        "stage_code": "reminder",
        "stage_number": 1,
        "min_days_overdue": 1,
        "max_days_overdue": 30,
        "auto_send_reminder": True,
        "sms_template": "Dear Customer, your loan payment of KES {amount} is {days} days overdue. Please pay immediately to avoid penalties. Alba Capital.",
        "create_activity": False,
    },
    {
        "name": "Collections Stage (31-60 Days)",
        "stage_code": "collection",
        "stage_number": 2,
        "min_days_overdue": 31,
        "max_days_overdue": 60,
        "auto_send_reminder": True,
        "additional_penalty_rate": 0.0,
        "escalate_to": "alba_loans.group_operations_manager",
        "create_activity": True,
    },
    {
        "name": "Recovery Stage (61-90 Days)",
        "stage_code": "recovery",
        "stage_number": 3,
        "min_days_overdue": 61,
        "max_days_overdue": 90,
        "auto_send_reminder": True,
        "additional_penalty_rate": 1.0,  # +1% penalty
        "escalate_to": "alba_loans.group_director",
        "create_activity": True,
    },
    {
        "name": "Legal Stage (90+ Days)",
        "stage_code": "legal",
        "stage_number": 4,
        "min_days_overdue": 91,
        "max_days_overdue": 9999,
        "auto_send_reminder": False,
        "escalate_to": "alba_loans.group_director",
        "create_activity": True,
    },
]
