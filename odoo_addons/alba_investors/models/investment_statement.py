# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AlbaInvestmentStatement(models.Model):
    _name = "alba.investment.statement"
    _description = "Alba Capital Investment Statement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "reference"
    _order = "statement_date desc, id desc"

    # ── Identification ────────────────────────────────────────────────────────
    reference = fields.Char(
        string="Statement Reference",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _("New"),
    )

    # ── Links ─────────────────────────────────────────────────────────────────
    investment_id = fields.Many2one(
        "alba.investment",
        string="Investment",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )
    investor_id = fields.Many2one(
        "alba.investor",
        string="Investor",
        related="investment_id.investor_id",
        store=True,
        readonly=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="investment_id.partner_id",
        store=True,
        readonly=True,
    )
    # ── Period ────────────────────────────────────────────────────────────────
    statement_date = fields.Date(
        string="Statement Date",
        required=True,
        tracking=True,
        default=fields.Date.today,
    )
    period_start = fields.Date(
        string="Period Start",
        required=True,
        tracking=True,
    )
    period_end = fields.Date(
        string="Closing Date",
        required=True,
        tracking=True,
    )

    # ── Financials ────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="investment_id.currency_id",
        store=True,
        readonly=True,
    )
    opening_balance = fields.Monetary(
        string="Opening Balance",
        currency_field="currency_id",
        required=True,
        default=0.0,
        tracking=True,
    )
    deposits = fields.Monetary(
        string="Deposits During Period",
        currency_field="currency_id",
        default=0.0,
    )
    withdrawals = fields.Monetary(
        string="Withdrawals During Period",
        currency_field="currency_id",
        default=0.0,
    )
    interest_accrued = fields.Monetary(
        string="Interest Accrued",
        currency_field="currency_id",
        required=True,
        default=0.0,
        tracking=True,
        help="Total compound interest accrued during the statement period.",
    )
    wht_rate = fields.Float(
        string="WHT Rate (%)",
        related="investment_id.wht_rate",
        store=True,   # IMPORT-EXPORT FIX: store=True so exported column can be matched on re-import
        readonly=True,
    )
    wht_amount = fields.Monetary(
        string="WHT Deducted",
        currency_field="currency_id",
        compute="_compute_wht_amount",
        inverse="_inverse_wht_amount",
        store=True,
        # IMPORT-EXPORT FIX
    )
    net_interest = fields.Monetary(
        string="Net Interest",
        currency_field="currency_id",
        compute="_compute_wht_amount",
        inverse="_inverse_net_interest",
        store=True,
        # IMPORT-EXPORT FIX
    )
    closing_balance = fields.Monetary(
        string="Closing Balance",
        currency_field="currency_id",
        compute="_compute_closing_balance",
        inverse="_inverse_closing_balance",
        store=True,
        tracking=True,
        # IMPORT-EXPORT FIX: inverse allows import to write; readonly removed so mapping is possible
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("sent", "Sent to Investor"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )

    # ── Accruals included in this statement ───────────────────────────────────
    accrual_ids = fields.Many2many(
        "alba.interest.accrual",
        "statement_accrual_rel",
        "statement_id",
        "accrual_id",
        string="Interest Accruals",
        domain="[('investment_id', '=', investment_id), ('state', '=', 'posted')]",
    )

    # ── Company ───────────────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        related="investment_id.company_id",
        store=True,
        readonly=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string="Notes / Remarks")

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _reference_unique = models.Constraint(
        "UNIQUE(reference)",
        "A statement with this reference already exists.",
    )

    # =========================================================================
    # Computed methods
    # =========================================================================

    @api.depends("opening_balance", "deposits", "withdrawals", "interest_accrued")
    def _compute_closing_balance(self):
        for rec in self:
            rec.closing_balance = (
                rec.opening_balance
                + rec.deposits
                - rec.withdrawals
                + rec.interest_accrued
            )

    def _inverse_closing_balance(self):
        # IMPORT-EXPORT FIX: no-op — allows import to write closing_balance;
        # compute re-derives it from opening_balance + deposits - withdrawals + interest_accrued.
        pass

    @api.depends("interest_accrued", "wht_rate")
    def _compute_wht_amount(self):
        for rec in self:
            rec.wht_amount = rec.interest_accrued * (rec.wht_rate / 100.0)
            rec.net_interest = rec.interest_accrued - rec.wht_amount

    def _inverse_wht_amount(self): pass  # IMPORT-EXPORT FIX
    def _inverse_net_interest(self): pass  # IMPORT-EXPORT FIX

    # =========================================================================
    # Business actions
    # =========================================================================

    def action_confirm(self):
        """Confirm the statement — locks figures."""
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    _("Only draft statements can be confirmed. '%s' is already %s.")
                    % (rec.reference, rec.state)
                )
            rec.write({"state": "confirmed"})
            rec.message_post(
                body=_(
                    "Statement <b>%s</b> confirmed. "
                    "Period: %s – %s. "
                    "Closing balance: <b>%s %.2f</b>."
                )
                % (
                    rec.reference,
                    rec.period_start,
                    rec.period_end,
                    rec.currency_id.name,
                    rec.closing_balance,
                )
            )
        return True

    def action_send(self):
        """
        Mark statement as sent and send an email to the investor.
        Uses the mail template if available; otherwise falls back to
        a plain chatter message.
        """
        for rec in self:
            if rec.state == "draft":
                rec.action_confirm()

            template = self.env.ref(
                "alba_investors.email_template_investment_statement",
                raise_if_not_found=False,
            )
            if template and rec.partner_id:
                template.send_mail(rec.id, force_send=True)
            else:
                rec.message_post(
                    body=_(
                        "Investment statement <b>%s</b> for period %s – %s "
                        "has been marked as sent.  "
                        "(Email template not found — please configure "
                        "'alba_investors.email_template_investment_statement'.)"
                    )
                    % (rec.reference, rec.period_start, rec.period_end),
                    partner_ids=rec.partner_id.ids if rec.partner_id else [],
                )

            rec.write({"state": "sent"})
        return True

    def action_reset_to_draft(self):
        """Reset a confirmed/sent statement back to draft for correction."""
        for rec in self:
            if rec.state == "sent":
                raise UserError(
                    _(
                        "Statement '%s' has already been sent to the investor "
                        "and cannot be reset to draft."
                    )
                    % rec.reference
                )
            rec.write({"state": "draft"})
            rec.message_post(body=_("Statement reset to <b>Draft</b>."))
        return True

    # =========================================================================
    # Scheduled action (cron) — generate monthly statements for all investments
    # =========================================================================

    @api.model
    def action_generate_monthly_statements(self):
        """
        Called by the monthly cron on the 2nd of each month.
        For every active investment, creates a statement covering the
        previous calendar month if one does not already exist.
        """
        import calendar
        from datetime import date

        today = fields.Date.today()
        # Previous month
        month = today.month - 1 or 12
        year = today.year if today.month > 1 else today.year - 1
        period_start = date(year, month, 1)
        period_end = date(year, month, calendar.monthrange(year, month)[1])

        active_investments = self.env["alba.investment"].search(
            [("state", "=", "active")]
        )

        created_count = 0
        for inv in active_investments:
            # Skip if statement already exists for this period
            existing = self.search(
                [
                    ("investment_id", "=", inv.id),
                    ("period_start", "=", period_start),
                    ("period_end", "=", period_end),
                ],
                limit=1,
            )
            if existing:
                continue

            # Collect accruals in this period
            accruals = self.env["alba.interest.accrual"].search(
                [
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("accrual_date", ">=", period_start),
                    ("accrual_date", "<=", period_end),
                ]
            )
            total_interest = sum(accruals.mapped("interest_amount"))

            # Top-ups in this period
            topups = self.env["alba.investment.topup"].search(
                [
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("date", ">=", period_start),
                    ("date", "<=", period_end),
                ]
            )
            total_deposits = sum(topups.mapped("amount"))

            # Payouts (withdrawals) in this period
            payouts = self.env["alba.interest.payout"].search(
                [
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("payout_date", ">=", period_start),
                    ("payout_date", "<=", period_end),
                ]
            )
            total_withdrawals = sum(payouts.mapped("gross_interest"))

            # Prior elements for opening balance
            prior_topups = self.env["alba.investment.topup"].search(
                [
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("date", "<", period_start),
                ]
            )
            prior_accruals = self.env["alba.interest.accrual"].search(
                [
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("accrual_date", "<", period_start),
                ]
            )
            prior_payouts = self.env["alba.interest.payout"].search(
                [
                    ("investment_id", "=", inv.id),
                    ("state", "=", "posted"),
                    ("payout_date", "<", period_start),
                ]
            )

            opening_balance = (
                inv.principal_amount
                + sum(prior_topups.mapped("amount"))
                + sum(prior_accruals.mapped("interest_amount"))
                - sum(prior_payouts.mapped("gross_interest"))
            )

            stmt_vals = {
                "investment_id": inv.id,
                "statement_date": today,
                "period_start": period_start,
                "period_end": period_end,
                "opening_balance": opening_balance,
                "deposits": total_deposits,
                "withdrawals": total_withdrawals,
                "interest_accrued": total_interest,
                "accrual_ids": [(6, 0, accruals.ids)],
            }
            stmt = self.create(stmt_vals)
            stmt.action_confirm()
            # Auto-send statement to investor
            try:
                stmt.action_send()
            except Exception as e:
                _logger.error("Failed to auto-send statement %s: %s", stmt.reference, str(e))
            created_count += 1

        _logger.info(
            "alba.investment.statement: Monthly generation complete — "
            "%d statements created for period %s – %s.",
            created_count,
            period_start,
            period_end,
        )
        return True

    @api.model
    def action_run_automated_statement_generation(self):
        """
        Called by a daily cron job to automatically generate and send statements
        for investments whose product settings match the statement generation day
        (1 day after the accrual day).
        """
        today = fields.Date.context_today(self)
        import calendar
        from datetime import date, timedelta
        
        created_count = 0
        active_investments = self.env["alba.investment"].search([("state", "=", "active")])
        
        # We determine if today is the day after the target accrual run day
        yesterday = today - timedelta(days=1)
        
        for inv in active_investments:
            product = inv.investment_product_id
            if not product:
                continue
            
            target_day = product.auto_accrual_day or 28
            yesterday_last_day = calendar.monthrange(yesterday.year, yesterday.month)[1]
            yesterday_target_run_day = min(target_day, yesterday_last_day)
            
            if yesterday.day == yesterday_target_run_day:
                # Yesterday was the accrual day, so today we generate the statement for the previous calendar month
                month = today.month - 1 or 12
                year = today.year if today.month > 1 else today.year - 1
                period_start = date(year, month, 1)
                period_end = date(year, month, calendar.monthrange(year, month)[1])
                
                existing = self.search(
                    [
                        ("investment_id", "=", inv.id),
                        ("period_start", "=", period_start),
                        ("period_end", "=", period_end),
                    ],
                    limit=1,
                )
                if existing:
                    continue

                # Collect accruals in this period
                accruals = self.env["alba.interest.accrual"].search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("accrual_date", ">=", period_start),
                        ("accrual_date", "<=", period_end),
                    ]
                )
                total_interest = sum(accruals.mapped("interest_amount"))

                # Top-ups in this period
                topups = self.env["alba.investment.topup"].search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("date", ">=", period_start),
                        ("date", "<=", period_end),
                    ]
                )
                total_deposits = sum(topups.mapped("amount"))

                # Payouts (withdrawals) in this period
                payouts = self.env["alba.interest.payout"].search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("payout_date", ">=", period_start),
                        ("payout_date", "<=", period_end),
                    ]
                )
                total_withdrawals = sum(payouts.mapped("gross_interest"))

                # Prior elements for opening balance
                prior_topups = self.env["alba.investment.topup"].search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("date", "<", period_start),
                    ]
                )
                prior_accruals = self.env["alba.interest.accrual"].search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("accrual_date", "<", period_start),
                    ]
                )
                prior_payouts = self.env["alba.interest.payout"].search(
                    [
                        ("investment_id", "=", inv.id),
                        ("state", "=", "posted"),
                        ("payout_date", "<", period_start),
                    ]
                )

                opening_balance = (
                    inv.principal_amount
                    + sum(prior_topups.mapped("amount"))
                    + sum(prior_accruals.mapped("interest_amount"))
                    - sum(prior_payouts.mapped("gross_interest"))
                )

                stmt_vals = {
                    "investment_id": inv.id,
                    "statement_date": today,
                    "period_start": period_start,
                    "period_end": period_end,
                    "opening_balance": opening_balance,
                    "deposits": total_deposits,
                    "withdrawals": total_withdrawals,
                    "interest_accrued": total_interest,
                    "accrual_ids": [(6, 0, accruals.ids)],
                }
                stmt = self.create(stmt_vals)
                stmt.action_confirm()
                try:
                    stmt.action_send()
                except Exception as e:
                    _logger.error("Failed to auto-send statement %s: %s", stmt.reference, str(e))
                created_count += 1

        if created_count > 0:
            _logger.info(
                "alba.investment.statement: Automated statement generation complete — "
                "%d statements created on %s.",
                created_count,
                today,
            )
        return True

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("reference", _("New")) == _("New"):
                vals["reference"] = seq.next_by_code(
                    "alba.investment.statement.seq"
                ) or _("New")
        return super().create(vals_list)

    def name_get(self):
        return [
            (
                rec.id,
                "%s — %s" % (rec.reference, rec.investor_id.investor_name),
            )
            for rec in self
        ]


    @api.model
    def _check_company(self, company_id):
        """Ensure company consistency for multi-company setup."""
        if company_id:
            self.company_id = company_id
