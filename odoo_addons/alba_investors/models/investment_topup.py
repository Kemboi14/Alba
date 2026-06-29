# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .reference_utils import safe_investment_reference


class AlbaInvestmentTopup(models.Model):
    """
    Records every incremental deposit (top-up) on an active investment.

    Journal entry when posted (via inbound payment):
        DR  Bank / Cash              [amount]   ← funds received
        CR  Investment Liability     [amount]   ← investor liability increases
    """
    _name = "alba.investment.topup"
    _description = "Alba Capital Investment Top-Up"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "date desc, id desc"

    # ── Reference ─────────────────────────────────────────────────────────────
    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=False,          # writable so CSV import can map it
        default=lambda self: _("New"),
        index=True,
        tracking=True,
    )

    # ── Investment ────────────────────────────────────────────────────────────
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
        readonly=False,
        inverse="_inverse_readonly_import",
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        related="investment_id.investor_id.partner_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="investment_id.company_id",
        store=True,
        readonly=True,
    )

    # ── Currency ──────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="investment_id.currency_id",
        store=True,
        readonly=True,
    )

    # ── Date & Amount ─────────────────────────────────────────────────────────
    date = fields.Date(
        string="Top-Up Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        help="Date the investor deposited the additional funds.",
    )
    amount = fields.Monetary(
        string="Top-Up Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
        help="Gross amount deposited by the investor.",
    )

    # ── Accounting ────────────────────────────────────────────────────────────
    payment_id = fields.Many2one(
        "account.payment",
        string="Receipt",
        readonly=True,
        copy=False,
        help="Inbound payment: DR Bank / CR Investment Liability.",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Receipt Journal",
        domain="[('type', 'in', ('bank', 'cash'))]",
        tracking=True,
        help="Bank/Cash journal used to receive the top-up funds.",
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string="Notes")

    # =========================================================================
    # SQL Constraints
    # =========================================================================
    _topup_amount_positive = models.Constraint(
        "CHECK(amount > 0)",
        "Top-up amount must be greater than zero.",
    )

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("alba.investment.topup.seq")
                    or _("New")
                )
        return super().create(vals_list)

    # =========================================================================
    # Import / Export helpers
    # =========================================================================

    def _inverse_readonly_import(self):
        """No-op inverse — allows import to map read-only related fields."""
        pass

    @api.model
    def _get_default_list_export_fields(self):
        return [
            "name",
            "investment_id/investment_number",
            "investor_id/investor_number",
            "date",
            "amount",
            "journal_id/name",
            "state",
            "notes",
        ]

    @api.model
    def _name_search(self, name="", domain=None, operator="ilike", limit=100, order=None):
        domain = list(domain or [])
        if name:
            domain = [
                "|",
                ("name", operator, name),
                ("investment_id.investment_number", "=", name),
            ] + domain
        return self._search(domain, limit=limit, order=order)

    # =========================================================================
    # Business Logic
    # =========================================================================

    def action_post(self):
        """Post the top-up — create an inbound payment and mark as posted."""
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft top-ups can be posted."))

            investment = rec.investment_id
            if investment.state != "active":
                raise UserError(
                    _("Top-ups can only be posted on active investments (currently '%s').")
                    % investment.state
                )
            if not investment.account_investment_liability_id:
                raise UserError(
                    _("Please configure the Investment Liability Account on investment '%s'.")
                    % investment.investment_number
                )

            journal = rec.journal_id or investment.payment_journal_id
            if not journal:
                raise UserError(
                    _("Please select a Receipt Journal for top-up '%s'.") % rec.name
                )

            inv_currency = investment.currency_id

            # ── Inbound Payment: DR Bank / CR Investment Liability ────────────
            payment_vals = {
                "date": rec.date,
                "amount": rec.amount,
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": investment.partner_id.id,
                "journal_id": journal.id,
                "currency_id": inv_currency.id,
                "memo": "Top-Up %s — %s" % (rec.name, safe_investment_reference(investment)),
                "destination_account_id": investment.account_investment_liability_id.id,
            }
            payment = self.env["account.payment"].create(payment_vals)
            payment.action_post()

            rec.write({
                "state": "posted",
                "payment_id": payment.id,
                "journal_id": journal.id,
            })

            # Invalidate subsequent posted/draft accruals and run backfill
            investment._invalidate_subsequent_accruals(rec.date)
            investment.action_backfill_missing_accruals()

            investment.message_post(
                body=_(
                    "Top-up <b>%(ref)s</b> posted: "
                    "<b>%(currency)s %(amount).2f</b> received. "
                    "Receipt: <b>%(payment)s</b>. "
                    "New effective principal: "
                    "<b>%(currency)s %(new_principal).2f</b>.",
                    ref=rec.name,
                    currency=inv_currency.symbol,
                    amount=rec.amount,
                    payment=payment.name,
                    new_principal=investment.principal_amount + investment.total_topup_amount,
                )
            )

    def action_reset_to_draft(self):
        """Reset a posted top-up to draft (only if the linked payment can be cancelled)."""
        for rec in self:
            if rec.state != "posted":
                raise UserError(_("Only posted top-ups can be reset to draft."))
            if rec.payment_id and rec.payment_id.state == "posted":
                rec.payment_id.action_cancel()
            rec.write({"state": "draft", "payment_id": False})

            # Invalidate subsequent posted/draft accruals and run backfill
            investment = rec.investment_id
            investment._invalidate_subsequent_accruals(rec.date)
            investment.action_backfill_missing_accruals()

    def action_view_payment(self):
        """Open the linked receipt."""
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_("No payment receipt has been linked to this top-up yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Receipt"),
            "res_model": "account.payment",
            "view_mode": "form",
            "res_id": self.payment_id.id,
        }
