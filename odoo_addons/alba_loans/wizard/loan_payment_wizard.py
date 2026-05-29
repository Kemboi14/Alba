# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaLoanPaymentWizard(models.TransientModel):
    _name = "alba.loan.payment.wizard"
    _description = "Loan Payment Wizard"

    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="cascade",
    )
    amount = fields.Monetary(
        string="Amount",
        required=True,
        currency_field="currency_id",
    )
    payment_date = fields.Date(string="Payment Date", default=fields.Date.today)
    payment_method = fields.Selection(
        selection=[
            ("mpesa", "M-Pesa"),
            ("bank_transfer", "Bank Transfer"),
            ("cash", "Cash"),
            ("cheque", "Cheque"),
            ("rtgs", "RTGS / EFT"),
        ],
        string="Payment Method",
        required=True,
        default="mpesa",
    )
    mpesa_transaction_id = fields.Char(string="M-Pesa Transaction ID")
    bank_transaction_id = fields.Char(string="Bank Transaction ID / Cheque No.")
    journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Journal Payment Method",
        domain="[('payment_type', '=', 'inbound'), ('journal_id', '=', journal_id)]",
        help="Specific inbound payment method for the selected journal.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="loan_id.currency_id",
        readonly=True,
    )
    payment_reference = fields.Char(string="Payment Reference")

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        for rec in self:
            if rec.payment_method_line_id and rec.payment_method_line_id.journal_id != rec.journal_id:
                rec.payment_method_line_id = False

    def _ensure_payment_method_line(self):
        self.ensure_one()
        if not self.journal_id:
            return
        if self.payment_method_line_id:
            if self.payment_method_line_id.journal_id != self.journal_id:
                raise UserError(_("Selected payment method does not belong to the payment journal."))
            if self.payment_method_line_id.payment_type != "inbound":
                raise UserError(_("Please select an inbound payment method for payment journal '%s'.") % self.journal_id.display_name)
            return

        method_line = self.env["account.payment.method.line"].search([
            ("payment_type", "=", "inbound"),
            ("journal_id", "=", self.journal_id.id),
        ], limit=1)
        if not method_line:
            raise UserError(_("Please configure an inbound Payment Method on payment journal '%s'.") % self.journal_id.display_name)
        self.payment_method_line_id = method_line

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        loan_id = ctx.get("active_id") or ctx.get("default_loan_id")
        if loan_id:
            loan = self.env["alba.loan"].browse(loan_id)
            res.setdefault("loan_id", loan.id)
            # default amount may be provided in context
            if "default_amount" not in res:
                if ctx.get("is_quick_payment"):
                    res.setdefault("amount", loan.installment_amount or 0.0)
                else:
                    res.setdefault("amount", loan.outstanding_balance or 0.0)
        return res

    def action_confirm_payment(self):
        self.ensure_one()
        if not self.loan_id:
            raise UserError(_("No loan selected."))
        if self.amount <= 0:
            raise UserError(_("Payment amount must be positive."))
        if self.env.context.get("is_quick_payment"):
            if self.amount >= self.loan_id.outstanding_balance:
                raise UserError(_(
                    "Quick payment is only for partial payments. The payment amount (%s) "
                    "must be less than the full outstanding balance (%s). "
                    "For a full payoff, please use the Full Repayment button."
                ) % (self.amount, self.loan_id.outstanding_balance))
        self._ensure_payment_method_line()

        # Create repayment record and post it using existing flow
        repayment_vals = {
            "loan_id": self.loan_id.id,
            "payment_date": self.payment_date or fields.Date.today(),
            "amount_paid": self.amount,
            "payment_method": self.payment_method,
            "mpesa_transaction_id": self.mpesa_transaction_id or False,
            "bank_transaction_id": self.bank_transaction_id or False,
            "journal_id": self.journal_id.id if self.journal_id else False,
            "payment_method_line_id": self.payment_method_line_id.id if self.payment_method_line_id else False,
            "payment_reference": self.payment_reference or False,
            "notes": _("Quick payment via wizard"),
        }

        repayment = self.env["alba.loan.repayment"].create(repayment_vals)
        repayment.action_post()

        # Return action to the created repayment
        return {
            "type": "ir.actions.act_window",
            "name": _("Repayment"),
            "res_model": "alba.loan.repayment",
            "res_id": repayment.id,
            "view_mode": "form",
            "target": "current",
        }
