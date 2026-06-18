# -*- coding: utf-8 -*-
"""
Alba Capital — Default Interest Cron
Continues accruing penalty/default interest daily for loans in arrears or NPL state.

Referenced by cron_data.xml cron #10:
    env['alba.loan.interest.cron'].cron_continue_default_interest()
"""
import logging

from odoo import _, api, fields, models
from markupsafe import Markup

_logger = logging.getLogger(__name__)


class AlbaLoanInterestCron(models.Model):
    """
    Stub model that provides the daily default-interest continuation cron.

    This model does not store any data — it only exposes the
    ``cron_continue_default_interest`` class method so that
    ``cron_data.xml`` can reference ``alba.loan.interest.cron`` as its target.
    """

    _name = "alba.loan.interest.cron"
    _description = "Loan Default Interest Automation"

    # =========================================================================
    # Cron method
    # =========================================================================

    @api.model
    def cron_continue_default_interest(self):
        """
        Daily cron: accrue default/penalty interest for every active or
        NPL loan that has overdue instalments, according to the penalty rate
        configured on the loan product.

        Logic:
          For each overdue schedule line on an active/NPL loan:
            penalty_owed = balance_due * ((1 + daily_rate)^days_overdue - 1)

          We post a chatter note per loan summarising total accrued penalty
          and fire a Django webhook so the portal stays up-to-date.
          (Actual booking to a journal entry is handled when the repayment
          is posted via _auto_allocate_components in loan_repayment.py.)
        """
        today = fields.Date.today()

        overdue_loans = self.env["alba.loan"].search(
            [("state", "not in", ["closed", "written_off"]), ("days_in_arrears", ">", 0)]
        )

        loans_processed = 0
        for loan in overdue_loans:
            product = loan.loan_product_id
            if not product or not product.penalty_rate:
                continue

            daily_rate = product.penalty_rate / 100.0
            total_penalty = 0.0

            overdue_lines = (loan.current_repayment_schedule_ids or loan.repayment_schedule_ids).filtered(
                lambda s: s.due_date and s.due_date < today and s.balance_due > 0
            )
            for line in overdue_lines:
                days_overdue = (today - line.due_date).days
                penalty = line.balance_due * ((1 + daily_rate) ** days_overdue - 1)
                total_penalty += penalty

            if total_penalty > 0.01:
                # ENTRY 3 — Interest Accrual (Default/Penalty)
                loan.action_post_interest_accrual_entry(amount=total_penalty)

                loan.message_post(
                    body=Markup(
                        _(
                            "Default interest accrual: <b>%(currency)s %(amount).2f</b> "
                            "on <b>%(count)d</b> overdue instalment(s) "
                            "(daily rate: <b>%(rate).4f%%</b>)."
                        )
                    )
                    % {
                        "currency": loan.currency_id.name,
                        "amount": total_penalty,
                        "count": len(overdue_lines),
                        "rate": daily_rate * 100,
                    },
                    subtype_xmlid="mail.mt_note",
                )
                loans_processed += 1

        _logger.info(
            "cron_continue_default_interest: processed %d loan(s) with accrued penalty interest.",
            loans_processed,
        )
