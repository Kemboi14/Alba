# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AlbaLoanApplicationDecisionWizard(models.TransientModel):
    _name = "alba.loan.application.decision.wizard"
    _description = "Loan Application Decision Wizard"

    application_id = fields.Many2one(
        "alba.loan.application",
        string="Loan Application",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    decision = fields.Selection(
        selection=[
            ("deferred", "Deferred"),
            ("declined", "Declined"),
        ],
        required=True,
        readonly=True,
    )
    reason_id = fields.Many2one(
        "alba.loan.status.reason",
        string="Reason",
        required=True,
        domain="[('category', '=', decision), ('active', '=', True)]",
    )
    notes = fields.Text(string="Notes")

    @api.onchange("decision")
    def _onchange_decision(self):
        self.reason_id = False

    def action_apply(self):
        self.ensure_one()
        if not self.application_id:
            raise UserError(_("No loan application selected."))
        self.application_id._apply_status_decision(
            self.decision,
            self.reason_id,
            self.notes,
        )
        return {"type": "ir.actions.act_window_close"}
