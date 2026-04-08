import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AlbaSmsBatch(models.Model):
    _name = "alba.sms.batch"
    _description = "Alba SMS Batch Campaign"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "create_date desc"

    name = fields.Char(required=True, tracking=True)
    template_id = fields.Many2one(
        "alba.sms.template",
        string="Template",
        required=True,
        tracking=True,
        domain="[('is_active','=',True)]",
    )
    provider_id = fields.Many2one(
        "alba.sms.provider",
        string="Provider",
        required=True,
        tracking=True,
        domain="[('is_active','=',True)]",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("running", "Running"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    scheduled_at = fields.Datetime(string="Send At")
    target_type = fields.Selection(
        selection=[
            ("all_customers", "All Active Customers"),
            ("overdue_loans", "All Overdue Loans"),
            ("par_1_30", "PAR 1\u201330 Days"),
            ("par_31_60", "PAR 31\u201360 Days"),
            ("par_61_90", "PAR 61\u201390 Days"),
            ("npl_loans", "NPL Loans"),
            ("maturing_soon", "Maturing Within 30 Days"),
            ("all_investors", "All Active Investors"),
            ("custom_domain", "Custom Domain Filter"),
            ("manual_list", "Manual Phone Number List"),
        ],
        string="Target Type",
        required=True,
    )
    target_domain = fields.Text(string="Custom Domain (JSON)")
    manual_phones = fields.Text(string="Phone Numbers (one per line)")
    batch_line_ids = fields.One2many(
        "alba.sms.batch.line",
        "batch_id",
        string="Batch Lines",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )

    # ── Computed fields ──────────────────────────────────────────────────────

    total_count = fields.Integer(
        compute="_compute_counts",
        store=True,
    )
    sent_count = fields.Integer(
        compute="_compute_counts",
        store=True,
    )
    delivered_count = fields.Integer(
        compute="_compute_counts",
        store=True,
    )
    failed_count = fields.Integer(
        compute="_compute_counts",
        store=True,
    )
    progress_pct = fields.Float(
        string="Progress (%)",
        compute="_compute_counts",
        store=True,
    )

    @api.depends("batch_line_ids", "batch_line_ids.status")
    def _compute_counts(self):
        for batch in self:
            lines = batch.batch_line_ids
            total = len(lines)
            sent = sum(1 for l in lines if l.status == "sent")
            delivered = sum(1 for l in lines if l.status == "delivered")
            failed = sum(1 for l in lines if l.status == "failed")
            batch.total_count = total
            batch.sent_count = sent
            batch.delivered_count = delivered
            batch.failed_count = failed
            batch.progress_pct = (
                (sent + delivered + failed) / total * 100 if total else 0.0
            )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _resolve_phone(self, record):
        """Return the best available phone number for a record."""
        model = record._name
        phone = False

        if model == "alba.loan":
            customer = record.customer_id
            if customer:
                phone = (
                    getattr(customer, "mpesa_number", False)
                    or (customer.partner_id and customer.partner_id.mobile)
                    or (customer.partner_id and customer.partner_id.phone)
                )
        elif model == "alba.investor":
            phone = (
                getattr(record, "mpesa_number", False)
                or (record.partner_id and record.partner_id.mobile)
                or (record.partner_id and record.partner_id.phone)
            )
        elif model == "alba.customer":
            phone = getattr(record, "mpesa_number", False) or (
                record.partner_id and record.partner_id.mobile
            )

        return phone or False

    def _build_sms_context(self, record):
        """Return a dict of template placeholders for the given record."""
        ctx = {
            "company_name": self.env.company.name,
        }
        model = record._name

        if model == "alba.loan":
            # Nearest overdue schedule date
            due_date = False
            overdue_schedules = (
                record.mapped("schedule_ids").filtered(
                    lambda s: hasattr(s, "status") and s.status == "overdue"
                )
                if hasattr(record, "schedule_ids")
                else []
            )
            if overdue_schedules:
                due_date = min(
                    (s.due_date for s in overdue_schedules if s.due_date),
                    default=False,
                )

            ctx.update(
                {
                    "loan_number": getattr(record, "name", "") or "",
                    "customer_name": (
                        record.customer_id.partner_id.name
                        if record.customer_id and record.customer_id.partner_id
                        else ""
                    ),
                    "amount": getattr(record, "outstanding_balance", 0.0),
                    "days_overdue": getattr(record, "days_in_arrears", 0),
                    "outstanding_balance": getattr(record, "outstanding_balance", 0.0),
                    "maturity_date": getattr(record, "maturity_date", False),
                    "due_date": due_date,
                }
            )
        elif model == "alba.customer":
            ctx.update(
                {
                    "customer_name": (
                        record.partner_id.name
                        if record.partner_id
                        else getattr(record, "name", "")
                    ),
                }
            )
        elif model == "alba.investor":
            ctx.update(
                {
                    "investor_name": (
                        record.partner_id.name
                        if record.partner_id
                        else getattr(record, "name", "")
                    ),
                    "investment_number": getattr(record, "name", "") or "",
                    "interest_amount": getattr(record, "interest_amount", 0.0),
                }
            )

        return ctx

    def _render_message(self, record):
        """Render the template body using the record context.

        Delegates to :meth:`alba.sms.template.render` which uses
        ``{placeholder}`` substitution and returns the raw content
        unchanged on ``KeyError`` — so a missing placeholder can never
        silently drop the SMS.
        """
        template = self.template_id
        if not template:
            return ""
        ctx = self._build_sms_context(record)
        return template.render(ctx)

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_generate_lines(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(
                _("Lines can only be generated while the batch is in Draft state.")
            )

        # Remove existing lines
        self.batch_line_ids.unlink()

        today = fields.Date.today()
        lines_vals = []

        target = self.target_type

        if target == "all_customers":
            records = self.env["alba.customer"].search([("state", "=", "active")])
            for rec in records:
                phone = self._resolve_phone(rec)
                if not phone:
                    continue
                lines_vals.append(self._prepare_line_vals(rec, phone))

        elif target == "overdue_loans":
            records = self.env["alba.loan"].search(
                [("state", "in", ["active", "npl"]), ("days_in_arrears", ">", 0)]
            )
            for rec in records:
                phone = self._resolve_phone(rec)
                if not phone:
                    continue
                lines_vals.append(self._prepare_line_vals(rec, phone))

        elif target == "par_1_30":
            records = self.env["alba.loan"].search(
                [
                    ("state", "=", "active"),
                    ("days_in_arrears", ">=", 1),
                    ("days_in_arrears", "<=", 30),
                ]
            )
            for rec in records:
                phone = self._resolve_phone(rec)
                if not phone:
                    continue
                lines_vals.append(self._prepare_line_vals(rec, phone))

        elif target == "par_31_60":
            records = self.env["alba.loan"].search(
                [
                    ("state", "=", "active"),
                    ("days_in_arrears", ">=", 31),
                    ("days_in_arrears", "<=", 60),
                ]
            )
            for rec in records:
                phone = self._resolve_phone(rec)
                if not phone:
                    continue
                lines_vals.append(self._prepare_line_vals(rec, phone))

        elif target == "par_61_90":
            records = self.env["alba.loan"].search(
                [
                    ("state", "=", "active"),
                    ("days_in_arrears", ">=", 61),
                    ("days_in_arrears", "<=", 90),
                ]
            )
            for rec in records:
                phone = self._resolve_phone(rec)
                if not phone:
                    continue
                lines_vals.append(self._prepare_line_vals(rec, phone))

        elif target == "npl_loans":
            records = self.env["alba.loan"].search([("state", "=", "npl")])
            for rec in records:
                phone = self._resolve_phone(rec)
                if not phone:
                    continue
                lines_vals.append(self._prepare_line_vals(rec, phone))

        elif target == "maturing_soon":
            date_limit = today + timedelta(days=30)
            records = self.env["alba.loan"].search(
                [
                    ("state", "=", "active"),
                    ("maturity_date", ">=", today),
                    ("maturity_date", "<=", date_limit),
                ]
            )
            for rec in records:
                phone = self._resolve_phone(rec)
                if not phone:
                    continue
                lines_vals.append(self._prepare_line_vals(rec, phone))

        elif target == "all_investors":
            records = self.env["alba.investor"].search([("state", "=", "active")])
            for rec in records:
                phone = self._resolve_phone(rec)
                if not phone:
                    continue
                lines_vals.append(self._prepare_line_vals(rec, phone))

        elif target == "custom_domain":
            if not self.target_domain:
                raise UserError(
                    _("Please provide a Custom Domain (JSON) for this target type.")
                )
            try:
                domain = json.loads(self.target_domain)
            except (json.JSONDecodeError, TypeError) as exc:
                raise UserError(
                    _("Invalid JSON in Custom Domain field: %s") % exc
                ) from exc
            records = self.env["alba.loan"].search(domain)
            for rec in records:
                phone = self._resolve_phone(rec)
                if not phone:
                    continue
                lines_vals.append(self._prepare_line_vals(rec, phone))

        elif target == "manual_list":
            if not self.manual_phones:
                raise UserError(_("Please provide at least one phone number."))
            ctx = {"company_name": self.env.company.name}
            message = self.template_id.render(ctx) if self.template_id else ""

            for raw_phone in self.manual_phones.splitlines():
                phone = raw_phone.strip()
                if not phone:
                    continue
                lines_vals.append(
                    {
                        "batch_id": self.id,
                        "phone_number": phone,
                        "message": message,
                        "status": "queued",
                        "res_model": False,
                        "res_id": False,
                    }
                )

        if lines_vals:
            self.env["alba.sms.batch.line"].create(lines_vals)

        count = len(lines_vals)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Lines Generated"),
                "message": _("%d SMS line(s) have been generated.") % count,
                "sticky": False,
                "type": "success",
            },
        }

    def _prepare_line_vals(self, record, phone):
        """Build create-vals dict for a single batch line."""
        message = self._render_message(record)
        return {
            "batch_id": self.id,
            "phone_number": phone,
            "message": message,
            "status": "queued",
            "res_model": record._name,
            "res_id": record.id,
        }

    def action_send_now(self):
        self.ensure_one()
        self.state = "running"
        self._process_lines()

    def action_schedule(self):
        self.ensure_one()
        if not self.scheduled_at:
            raise UserError(_("Please set a Send At date/time before scheduling."))
        now = fields.Datetime.now()
        if self.scheduled_at <= now:
            raise UserError(_("The scheduled send time must be in the future."))
        self.state = "scheduled"

    def action_cancel(self):
        self.ensure_one()
        self.state = "cancelled"

    def _process_lines(self, page_size=100):
        """Send the next page of queued lines via the configured provider."""
        self.ensure_one()
        queued_lines = self.batch_line_ids.filtered(lambda l: l.status == "queued")[
            :page_size
        ]

        for line in queued_lines:
            try:
                success, msg_id, error_msg = self.provider_id.send_sms(
                    line.phone_number,
                    line.message,
                    line.res_model or "",
                    line.res_id or 0,
                    template_id=self.template_id.id if self.template_id else False,
                    batch_line_id=line.id,
                )
                if success:
                    line.status = "sent"
                    # Link back to the log entry that send_sms just created
                    sms_log = (
                        self.env["alba.sms.log"]
                        .sudo()
                        .search([("batch_line_id", "=", line.id)], limit=1)
                    )
                    if sms_log:
                        line.log_id = sms_log.id
                else:
                    line.status = "failed"
                    line.error_message = error_msg or "Unknown error"
            except Exception as exc:  # pylint: disable=broad-except
                _logger.error(
                    "SMS batch %s: unexpected error sending to %s: %s",
                    self.id,
                    line.phone_number,
                    exc,
                )
                line.status = "failed"
                line.error_message = str(exc)

        # Recompute aggregates
        self._compute_counts()

        # Check if any lines are still queued
        remaining = self.batch_line_ids.filtered(lambda l: l.status == "queued")
        if not remaining:
            self.state = "done"

    # ── Scheduled action (cron) ───────────────────────────────────────────────

    @api.model
    def cron_process_scheduled_batches(self):
        """Cron entry-point: kick off scheduled batches and continue running ones."""
        now = fields.Datetime.now()

        # Activate batches whose scheduled time has arrived
        due_batches = self.search(
            [("state", "=", "scheduled"), ("scheduled_at", "<=", now)]
        )
        for batch in due_batches:
            try:
                batch.state = "running"
                batch._process_lines()
            except Exception as exc:  # pylint: disable=broad-except
                _logger.error(
                    "cron_process_scheduled_batches: error processing batch %s: %s",
                    batch.id,
                    exc,
                )

        # Continue any batches that are still running (partial sends)
        running_batches = self.search([("state", "=", "running")])
        for batch in running_batches:
            has_queued = batch.batch_line_ids.filtered(lambda l: l.status == "queued")
            if has_queued:
                try:
                    batch._process_lines()
                except Exception as exc:  # pylint: disable=broad-except
                    _logger.error(
                        "cron_process_scheduled_batches: error continuing batch %s: %s",
                        batch.id,
                        exc,
                    )


class AlbaSmsBatchLine(models.Model):
    _name = "alba.sms.batch.line"
    _description = "Alba SMS Batch Line"
    _rec_name = "phone_number"
    _order = "id"

    batch_id = fields.Many2one(
        "alba.sms.batch",
        string="Batch",
        required=True,
        ondelete="cascade",
        index=True,
    )
    phone_number = fields.Char(string="Phone Number", required=True)
    message = fields.Text(string="Message", required=True)
    status = fields.Selection(
        selection=[
            ("queued", "Queued"),
            ("sent", "Sent"),
            ("delivered", "Delivered"),
            ("failed", "Failed"),
        ],
        default="queued",
        required=True,
        index=True,
    )
    log_id = fields.Many2one(
        "alba.sms.log",
        string="SMS Log",
        ondelete="set null",
    )
    res_model = fields.Char(string="Related Model")
    res_id = fields.Integer(string="Related Record ID")
    error_message = fields.Text(string="Error Message")
