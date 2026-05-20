# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AlbaInterestAccrualReverseWizard(models.TransientModel):
    _name = "alba.interest.accrual.reverse.wizard"
    _description = "Interest Accrual Reversal Wizard"

    accrual_id = fields.Many2one(
        "alba.interest.accrual",
        string="Interest Accrual",
        required=True,
        ondelete="cascade",
    )
    reversal_reason = fields.Text(
        string="Reversal Reason",
        required=True,
        help="Please state the reason for reversing this interest accrual.",
    )

    def action_confirm_reversal(self):
        self.ensure_one()
        if not self.accrual_id:
            raise UserError(_("No accrual selected for reversal."))
        if self.accrual_id.state != "posted":
            raise UserError(_("Only posted accruals can be reversed."))
        
        # Write reason and trigger action_reverse
        self.accrual_id.write({"reversal_reason": self.reversal_reason})
        self.accrual_id.action_reverse()
        return {"type": "ir.actions.act_window_close"}
