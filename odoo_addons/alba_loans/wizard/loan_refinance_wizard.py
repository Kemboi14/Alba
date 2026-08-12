# -*- coding: utf-8 -*-
"""
Refinance Wizard
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaLoanRefinanceWizard(models.TransientModel):
    _name = "alba.loan.refinance.wizard"
    _description = "Loan Refinance Wizard"
    
    original_loan_id = fields.Many2one(
        "alba.loan",
        string="Original Loan",
        required=True,
        default=lambda self: self._default_loan(),
    )
    customer_id = fields.Many2one(
        "alba.customer",
        related="original_loan_id.customer_id",
        readonly=True,
    )
    original_outstanding = fields.Monetary(
        related="original_loan_id.outstanding_balance",
        currency_field="currency_id",
        readonly=True,
    )
    original_rate = fields.Float(
        related="original_loan_id.interest_rate",
        readonly=True,
    )
    
    new_product_id = fields.Many2one(
        "alba.loan.product",
        string="New Product",
        required=True,
    )
    topup_amount = fields.Monetary(
        string="Top-Up Amount",
        currency_field="currency_id",
        help="If opened in Top-Up mode, amount to add to existing principal.",
    )
    is_topup = fields.Boolean(string="Top-Up Mode", default=False)
    new_principal = fields.Monetary(
        string="New Principal",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    new_interest_rate = fields.Float(
        string="New Interest Rate (%)",
        digits=(5, 2),
        required=True,
    )
    new_tenure_months = fields.Integer(
        string="New Tenure (Months)",
        required=True,
    )
    
    currency_id = fields.Many2one(
        "res.currency",
        related="original_loan_id.currency_id",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        help="Specific payment method for the selected journal.",
    )
    
    def _default_loan(self):
        return self.env.context.get("active_id")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        # If opened in top-up mode, prefill fields from original loan/product
        if self.env.context.get("alba_topup_mode") and vals.get("original_loan_id"):
            loan = self.env["alba.loan"].browse(vals.get("original_loan_id"))
            if loan and loan.exists():
                vals["is_topup"] = True
                # default new product to original product
                if loan.loan_product_id:
                    vals["new_product_id"] = loan.loan_product_id.id
                    vals["new_interest_rate"] = loan.loan_product_id.interest_rate
                    vals["new_tenure_months"] = loan.tenure_months
                # default new_principal to settlement amount
                settlement = loan.outstanding_principal + (loan.accrued_interest or 0.0) + (loan.outstanding_charges or 0.0)
                vals["new_principal"] = settlement
        return vals

    @api.onchange("topup_amount", "is_topup")
    def _onchange_topup_amount(self):
        if self.is_topup and self.original_loan_id:
            loan = self.original_loan_id
            settlement = loan.outstanding_principal + (loan.accrued_interest or 0.0) + (loan.outstanding_charges or 0.0)
            self.new_principal = settlement + (self.topup_amount or 0.0)
            repaid_pct = (loan.total_paid / loan.total_repayable * 100.0) if loan.total_repayable > 0 else 0.0
            if repaid_pct < 50.0:
                return {
                    "warning": {
                        "title": _("Ineligible for Top-Up"),
                        "message": _(
                            "Original loan '%s' has only %.1f%% repaid. At least 50%% repayment is required before a top-up can be granted."
                        ) % (loan.loan_number, repaid_pct)
                    }
                }
    
    def action_create_refinance(self):
        self.ensure_one()
        
        if not self.new_product_id:
            raise UserError(_("Please select a new product."))
        if self.new_principal <= 0.0:
            raise UserError(_("New Principal Amount must be greater than 0.00 and is mandatory."))
        
        if self.is_topup and self.original_loan_id:
            loan = self.original_loan_id
            repaid_pct = (loan.total_paid / loan.total_repayable * 100.0) if loan.total_repayable > 0 else 0.0
            if repaid_pct < 50.0:
                raise UserError(_(
                    "Top-Up Refinance is not allowed. Customer has only repaid %.1f%% of original loan '%s' "
                    "(minimum 50%% repayment required)."
                ) % (repaid_pct, loan.loan_number))

        loan = self.original_loan_id
        # alba.loan.refinance's own form auto-fills settlement_amount via
        # _onchange_original_loan_id() as soon as a user picks the loan —
        # but onchange never fires on a programmatic create(), so without
        # this the wizard-created record would settle_amount=0, making
        # every dependent preview (cashback_to_customer/customer_to_pay)
        # wrong and failing action_settle_original_loan() later against the
        # amount_paid > 0 constraint.
        settlement_amount = (
            loan.outstanding_principal + (loan.accrued_interest or 0.0) + (loan.outstanding_charges or 0.0)
        )

        vals = {
            "original_loan_id": self.original_loan_id.id,
            "new_product_id": self.new_product_id.id,
            "new_principal": self.new_principal,
            "new_interest_rate": self.new_interest_rate,
            "new_tenure_months": self.new_tenure_months,
            "settlement_amount": settlement_amount,
        }
        if self.is_topup:
            vals.update({"is_topup": True, "topup_amount": self.topup_amount})

        refinance = self.env["alba.loan.refinance"].create(vals)
        
        refinance.action_generate_quote()
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Refinance Quote"),
            "res_model": "alba.loan.refinance",
            "res_id": refinance.id,
            "view_mode": "form",
            "target": "current",
        }
