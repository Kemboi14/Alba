from odoo import models, fields, api, _
from odoo.exceptions import UserError

class InvestmentWithdrawWizard(models.TransientModel):
    _name = "alba.investment.withdraw.wizard"
    _description = "Investment Withdrawal Wizard"

    investment_id = fields.Many2one("alba.investment", string="Investment", required=True)
    currency_id = fields.Many2one(related="investment_id.currency_id")
    amount = fields.Monetary(string="Withdrawal Amount", related="investment_id.current_value", readonly=True)
    journal_id = fields.Many2one("account.journal", string="Payment Journal", required=True, domain="[('type', 'in', ('bank', 'cash'))]")
    payment_date = fields.Date(string="Withdrawal Date", required=True, default=fields.Date.context_today)

    def action_confirm_withdrawal(self):
        self.ensure_one()
        if not self.investment_id.account_investment_liability_id:
            raise UserError(_("Please configure the Investment Liability Account on the investment."))
        
        # Create the outbound payment
        payment_vals = {
            'date': self.payment_date,
            'amount': self.amount,
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.investment_id.investor_id.partner_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id.id,
            'memo': f"Withdrawal - {self.investment_id.investment_number}",
            'destination_account_id': self.investment_id.account_investment_liability_id.id,
        }
        
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        
        # Update the investment
        self.investment_id.write({
            'state': 'withdrawn',
            'payment_id': payment.id,  # Maybe we should store withdrawal_payment_id if payment_id is for receipt?
        })
        
        self.investment_id.message_post(body=_(
            "Investment withdrawn via payment <b>%s</b> for %s %s."
        ) % (payment.name, self.currency_id.symbol, self.amount))
        
        return {'type': 'ir.actions.act_window_close'}
