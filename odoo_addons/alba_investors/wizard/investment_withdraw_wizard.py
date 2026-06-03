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

            # Determine how much WHT and Interest Payable has already been posted in accrual moves.
            accrued_wht_already_posted = 0.0
            accrued_interest_payable_posted = 0.0

            posted_accruals = investment.accrual_ids.filtered(lambda a: a.state == "posted")
            for accrual in posted_accruals:
                if accrual.move_id:
                    for line in accrual.move_id.line_ids:
                        if line.account_id == investment.account_wht_payable_id:
                            accrued_wht_already_posted += abs(line.amount_currency)
                        elif line.account_id == investment.account_interest_payable_id:
                            accrued_interest_payable_posted += abs(line.amount_currency)

            # Clear whatever was posted to Interest Payable
            interest_payable_to_clear = accrued_interest_payable_posted

            # Remaining WHT to post during withdrawal
            wht_to_post = max(0.0, investment.wht_amount - accrued_wht_already_posted)

            # Net interest to offset (force-balanced to ensure DR = CR in foreign currency)
            net_interest_to_offset = interest_payable_to_clear - wht_to_post

            # Convert values to company currency
            company = investment.company_id or self.env.company
            comp_currency = company.currency_id
            inv_currency = investment.currency_id

            interest_payable_company = inv_currency._convert(
                interest_payable_to_clear, comp_currency, company, self.payment_date
            )
            wht_company = inv_currency._convert(
                wht_to_post, comp_currency, company, self.payment_date
            )
            net_interest_company = interest_payable_company - wht_company

            line_ids = []

            # 1. DR Interest Payable Account
            if interest_payable_to_clear > 0:
                line_ids.append((0, 0, {
                    'name': f"Clear Interest Payable - {investment.investment_number}",
                    'account_id': investment.account_interest_payable_id.id,
                    'debit': interest_payable_company,
                    'credit': 0.0,
                    'amount_currency': interest_payable_to_clear,
                    'currency_id': inv_currency.id,
                    'partner_id': investment.partner_id.id,
                }))

            # 2. CR Investment Liability Account
            if net_interest_to_offset > 0:
                line_ids.append((0, 0, {
                    'name': f"Investment Liability Interest Offset - {investment.investment_number}",
                    'account_id': investment.account_investment_liability_id.id,
                    'debit': 0.0,
                    'credit': net_interest_company,
                    'amount_currency': -net_interest_to_offset,
                    'currency_id': inv_currency.id,
                    'partner_id': investment.partner_id.id,
                }))

            # 3. CR WHT Payable Account
            if wht_to_post > 0:
                line_ids.append((0, 0, {
                    'name': f"Withholding Tax Payable - {investment.investment_number}",
                    'account_id': investment.account_wht_payable_id.id,
                    'debit': 0.0,
                    'credit': wht_company,
                    'amount_currency': -wht_to_post,
                    'currency_id': inv_currency.id,
                    'partner_id': investment.partner_id.id,
                }))

            if line_ids:
                move_vals = {
                    'date': self.payment_date,
                    'journal_id': investment.journal_id.id,
                    'ref': f"WHT/ADJ/{investment.investment_number}",
                    'move_type': 'entry',
                    'currency_id': inv_currency.id,
                    'line_ids': line_ids
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
