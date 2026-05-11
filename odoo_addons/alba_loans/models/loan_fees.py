# -*- coding: utf-8 -*-
import logging
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AlbaLoanFeeTemplate(models.Model):
    """Template for fees associated with a loan product"""
    _name = "alba.loan.fee.template"
    _description = "Loan Fee Template"
    _order = "sequence, id"

    product_id = fields.Many2one(
        "alba.loan.product",
        string="Loan Product",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    fee_product_id = fields.Many2one(
        "product.product",
        string="Fee Product",
        required=True,
        help="The product used for accounting (holds the income account).",
    )
    name = fields.Char(related="fee_product_id.name", readonly=True)

    fee_type = fields.Selection([
        ("fixed", "Fixed Amount"),
        ("percentage", "Percentage of Principal"),
    ], string="Fee Type", required=True, default="percentage")

    amount = fields.Float(
        string="Amount / Percentage",
        digits=(12, 2),
        required=True,
        help="Fixed amount or percentage (e.g. 3.5 for 3.5%).",
    )

    is_credit_life = fields.Boolean(
        string="Is Credit Life?",
        default=False,
        help="If checked, this fee will trigger a Vendor PO for Credit Life insurance.",
    )

    vendor_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        help="The vendor to whom this fee is paid (required if Credit Life).",
    )

    @api.constrains("is_credit_life", "vendor_id")
    def _check_vendor(self):
        for rec in self:
            if rec.is_credit_life and not rec.vendor_id:
                raise ValidationError(_("A Vendor is required for Credit Life fees."))


class AlbaLoanFeeLine(models.Model):
    """Actual fee lines on a loan application"""
    _name = "alba.loan.fee.line"
    _description = "Loan Fee Line"
    _order = "sequence, id"

    application_id = fields.Many2one(
        "alba.loan.application",
        string="Loan Application",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)

    fee_template_id = fields.Many2one(
        "alba.loan.fee.template",
        string="Fee Template",
        ondelete="set null",
        help="Source template this fee line was created from.",
    )

    fee_product_id = fields.Many2one(
        "product.product",
        string="Fee Product",
        required=False,  # Removed to prevent UI blockage
    )
    name = fields.Char(related="fee_product_id.name", readonly=True)

    fee_type = fields.Selection([
        ("fixed", "Fixed Amount"),
        ("percentage", "Percentage of Principal"),
    ], string="Fee Type", required=True, default="percentage")

    amount = fields.Float(
        string="Amount / Percentage",
        digits=(12, 2),
        required=False,  # Removed to prevent UI blockage
    )

    @api.constrains("fee_product_id", "amount")
    def _check_fee_data(self):
        for rec in self:
            if not rec.fee_product_id:
                raise ValidationError(_("Fee Product is required on all fee lines."))
            if not rec.amount and not rec.manual_override:
                raise ValidationError(_("Amount is required on fee line for %s.") % rec.fee_product_id.name)

    calculated_amount = fields.Monetary(
        string="Calculated Fee",
        currency_field="currency_id",
        compute="_compute_calculated_amount",
        store=True,
    )

    currency_id = fields.Many2one(
        related="application_id.currency_id",
        store=True,
        readonly=True,
    )

    is_credit_life = fields.Boolean(
        string="Is Credit Life?",
        default=False,
    )
    vendor_id = fields.Many2one(
        "res.partner",
        string="Vendor",
    )

    manual_override = fields.Boolean(
        string="Manual Override",
        default=False,
        help="If checked, you can manually set the calculated amount.",
    )
    override_amount = fields.Monetary(
        string="Override Amount",
        currency_field="currency_id",
    )

    @api.onchange("fee_template_id")
    def _onchange_fee_template_id(self):
        """Auto-populate fields from the selected fee template."""
        if self.fee_template_id:
            self.fee_product_id = self.fee_template_id.fee_product_id.id if self.fee_template_id.fee_product_id else False
            self.amount = self.fee_template_id.amount
            self.fee_type = self.fee_template_id.fee_type
            self.is_credit_life = self.fee_template_id.is_credit_life
            self.vendor_id = self.fee_template_id.vendor_id.id if self.fee_template_id.vendor_id else False
            self.sequence = self.fee_template_id.sequence

    @api.depends(
        "amount",
        "fee_type",
        "application_id.requested_amount",
        "manual_override",
        "override_amount",
    )
    def _compute_calculated_amount(self):
        for rec in self:
            if rec.manual_override:
                rec.calculated_amount = rec.override_amount
            elif rec.fee_type == "fixed":
                rec.calculated_amount = rec.amount
            else:
                principal = rec.application_id.requested_amount or 0.0
                rec.calculated_amount = principal * (rec.amount / 100.0)

    @api.constrains("is_credit_life", "vendor_id")
    def _check_credit_life_vendor(self):
        for rec in self:
            if rec.is_credit_life and not rec.vendor_id:
                raise ValidationError(
                    _("A Vendor is required for Credit Life fee lines.")
                )

    def unlink(self):
        """Harden unlink to provide better error messages if deletion is blocked."""
        for rec in self:
            _logger.info("Attempting to delete fee line %s (Product: %s) for application %s", 
                        rec.id, rec.fee_product_id.name, rec.application_id.application_number)
        try:
            return super(AlbaLoanFeeLine, self).unlink()
        except Exception as e:
            _logger.error("Failed to delete fee lines: %s", str(e))
            raise ValidationError(_(
                "Cannot delete fee lines. They might be referenced by other records (e.g. Accounting Moves or Purchase Orders). "
                "Error Details: %s"
            ) % str(e))