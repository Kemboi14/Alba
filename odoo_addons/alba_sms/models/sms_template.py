# -*- coding: utf-8 -*-
"""
alba.sms.template — Reusable SMS message templates.

Uses simple {placeholder} substitution — intentionally NOT Jinja to keep
it safe for non-technical admins.  Available placeholders are documented
in the `content` field help text.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_DUMMY_CONTEXT = {
    "customer_name": "John Doe",
    "loan_number": "LN-0001",
    "amount": "10,000.00",
    "due_date": "2025-01-31",
    "days_overdue": "5",
    "outstanding_balance": "45,000.00",
    "maturity_date": "2025-06-30",
    "company_name": "Alba Capital",
    "investor_name": "Jane Investor",
    "investment_number": "INV-0001",
    "interest_amount": "1,250.00",
    "guarantor_name": "George Guarantor",
    "code": "123456",
}

_PLACEHOLDER_HELP = (
    "Message body. Supported placeholders:\n"
    "  {customer_name}       — borrower's full name\n"
    "  {loan_number}         — loan reference (e.g. LN-0001)\n"
    "  {amount}              — relevant monetary amount\n"
    "  {due_date}            — instalment or payment due date\n"
    "  {days_overdue}        — number of days past due\n"
    "  {outstanding_balance} — total balance still owed\n"
    "  {maturity_date}       — loan maturity / end date\n"
    "  {company_name}        — sending company name\n"
    "  {investor_name}       — investor's full name\n"
    "  {investment_number}   — investment reference (e.g. INV-0001)\n"
    "  {interest_amount}     — interest amount credited or accrued\n"
    "  {guarantor_name}      — guarantor's full name\n"
    "  {code}                — verification or confirmation code"
)

_CATEGORY_SELECTION = [
    ("loan_overdue", "Loan Overdue Reminder"),
    ("maturity_reminder", "Loan Maturity Reminder"),
    ("repayment_reminder", "Repayment Reminder"),
    ("payment_confirmation", "Payment Confirmation"),
    ("loan_disbursed", "Loan Disbursed"),
    ("application_submitted", "Application Submitted"),
    ("application_approved", "Application Approved"),
    ("application_rejected", "Application Rejected"),
    ("collection_reminder", "Collection Stage Reminder"),
    ("investor_interest", "Investor Interest Credited"),
    ("investor_statement", "Investment Statement Sent"),
    ("guarantor_confirmation", "Guarantor Confirmation Request"),
    ("loan_status_change", "Loan Status Change"),
    ("bulk_campaign", "Bulk Campaign"),
]


class AlbaSmsTemplate(models.Model):
    _name = "alba.sms.template"
    _description = "Alba SMS Template"
    _rec_name = "name"
    _order = "category, name"

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    name = fields.Char(
        string="Template Name",
        required=True,
    )
    code = fields.Char(
        string="Code",
        required=True,
        index=True,
        help=(
            "Stable machine-readable key used to look up this template from "
            "Python code (e.g. 'loan_overdue_reminder').  Must be unique."
        ),
    )
    category = fields.Selection(
        selection=_CATEGORY_SELECTION,
        string="Category",
        required=True,
        index=True,
    )
    content = fields.Text(
        string="Message Content",
        required=True,
        help=_PLACEHOLDER_HELP,
    )
    is_active = fields.Boolean(
        string="Active",
        default=True,
    )
    char_count = fields.Integer(
        string="Character Count",
        compute="_compute_char_count",
        store=False,
    )
    preview = fields.Text(
        string="Preview (dummy data)",
        compute="_compute_preview",
        store=False,
        help="Shows how the message will look when rendered with sample values.",
    )

    # ------------------------------------------------------------------
    # SQL constraints
    # ------------------------------------------------------------------

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "A template with this code already exists. The code must be unique.",
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends("content")
    def _compute_char_count(self):
        for rec in self:
            rec.char_count = len(rec.content or "")

    @api.depends("content")
    def _compute_preview(self):
        for rec in self:
            rec.preview = rec.render(_DUMMY_CONTEXT)

    # ------------------------------------------------------------------
    # Business methods
    # ------------------------------------------------------------------

    def render(self, context_dict):
        """Render *self*'s content by substituting ``context_dict`` values.

        Uses :py:meth:`str.format_map` so only the keys present in
        ``context_dict`` are replaced; unknown placeholders cause a
        :py:exc:`KeyError` which is caught and logged rather than raised,
        returning the original content unchanged so the SMS is never
        silently lost.

        :param context_dict: mapping of placeholder name → replacement value.
        :returns: rendered string.
        :rtype: str
        """
        self.ensure_one()
        content = self.content or ""
        try:
            return content.format_map(context_dict)
        except KeyError as exc:
            _logger.warning(
                "alba.sms.template [%s] render failed — unknown placeholder %s. "
                "Returning raw content.",
                self.code,
                exc,
            )
            return content

    @api.model
    def get_by_code(self, code):
        """Return the first active template whose ``code`` matches *code*.

        :param str code: the stable template code to look up.
        :returns: a singleton :class:`AlbaSmsTemplate` recordset, or
                  ``False`` when no active template is found.
        """
        template = self.search(
            [("code", "=", code), ("is_active", "=", True)],
            limit=1,
        )
        return template or False
