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
    earliest_withdrawal_date = fields.Date(related="investment_id.earliest_withdrawal_date")
    days_to_withdrawal = fields.Integer(related="investment_id.days_to_withdrawal")

    def action_confirm_withdrawal(self):
        self.ensure_one()
        investment = self.investment_id
        if investment.state not in ("active", "matured"):
            raise UserError(_("Only active or matured investments can be withdrawn."))
        today = fields.Date.context_today(self)
        if (
            investment.state == "active"
            and investment.investment_type == "fixed_term"
            and investment.maturity_date
            and investment.maturity_date > today
        ):
            if not investment.withdrawal_notice_date:
                raise UserError(_("Please request early withdrawal notice before confirming withdrawal."))
            if investment.earliest_withdrawal_date and investment.earliest_withdrawal_date > today:
                raise UserError(
                    _("This early withdrawal can only be paid out from %s.")
                    % investment.earliest_withdrawal_date
                )

        if not investment.account_investment_liability_id:
            raise UserError(_("Please configure the Investment Liability Account on the investment."))
        
        # Create the outbound payment
        payment_vals = {
            'date': self.payment_date,
            'amount': self.amount,
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': investment.investor_id.partner_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id.id,
            'memo': f"Withdrawal - {investment.investment_number}",
            'destination_account_id': investment.account_investment_liability_id.id,
        }
        
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        
        # Update the investment
        investment.write({
            'state': 'withdrawn',
            'withdrawal_payment_id': payment.id,
        })
        
        investment.message_post(body=_(
            "Investment withdrawn via payment <b>%s</b> for %s %s."
        ) % (payment.name, self.currency_id.symbol, self.amount))
        
        return {'type': 'ir.actions.act_window_close'}
