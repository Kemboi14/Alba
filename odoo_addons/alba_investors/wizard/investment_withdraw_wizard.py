from odoo import models, fields, api, _
from odoo.exceptions import UserError

class InvestmentWithdrawWizard(models.TransientModel):
    _name = "alba.investment.withdraw.wizard"
    _description = "Investment Withdrawal Wizard"

    investment_id = fields.Many2one("alba.investment", string="Investment", required=True)
    currency_id = fields.Many2one(related="investment_id.currency_id")
    
    # Break down the payout components
    principal_amount = fields.Monetary(string="Principal Amount", related="investment_id.principal_amount", readonly=True)
    total_interest_accrued = fields.Monetary(string="Accrued Interest", related="investment_id.total_interest_accrued", readonly=True)
    wht_rate = fields.Float(string="WHT Rate (%)", related="investment_id.wht_rate", readonly=True)
    wht_amount = fields.Monetary(string="Withholding Tax Amount", related="investment_id.wht_amount", readonly=True)
    net_interest_payable = fields.Monetary(string="Net Interest", related="investment_id.net_interest_payable", readonly=True)
    amount = fields.Monetary(string="Net Payout Amount", related="investment_id.net_payout_amount", readonly=True)
    
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
        
        # Create the adjustment journal entry for interest and WHT if interest is accrued
        if investment.total_interest_accrued > 0:
            if not investment.account_interest_payable_id:
                raise UserError(_("Please configure the Interest Payable Account on the investment."))
            if not investment.account_wht_payable_id:
                raise UserError(_("Please configure the WHT Payable Account on the investment."))
            if not investment.journal_id:
                raise UserError(_("Please configure the Accrual Journal on the investment."))

            move_vals = {
                'date': self.payment_date,
                'journal_id': investment.journal_id.id,
                'ref': f"WHT/ADJ/{investment.investment_number}",
                'move_type': 'entry',
                'line_ids': [
                    # DR Interest Payable Account
                    (0, 0, {
                        'name': f"Clear Interest Payable - {investment.investment_number}",
                        'account_id': investment.account_interest_payable_id.id,
                        'debit': investment.total_interest_accrued,
                        'credit': 0.0,
                    }),
                    # CR Investment Liability Account (offsetting interest part of payout)
                    (0, 0, {
                        'name': f"Investment Liability Interest Offset - {investment.investment_number}",
                        'account_id': investment.account_investment_liability_id.id,
                        'debit': 0.0,
                        'credit': investment.net_interest_payable,
                    }),
                    # CR WHT Payable Account
                    (0, 0, {
                        'name': f"Withholding Tax Payable - {investment.investment_number}",
                        'account_id': investment.account_wht_payable_id.id,
                        'debit': 0.0,
                        'credit': investment.wht_amount,
                    }),
                ]
            }
            move = self.env['account.move'].create(move_vals)
            move.action_post()

        # Update the investment
        investment.write({
            'state': 'withdrawn',
            'withdrawal_payment_id': payment.id,
        })
        
        investment.message_post(body=_(
            "Investment withdrawn via payment <b>%s</b> for %s %s."
        ) % (payment.name, self.currency_id.symbol, self.amount))
        
        return {'type': 'ir.actions.act_window_close'}
