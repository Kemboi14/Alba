# -*- coding: utf-8 -*-
"""
Alba Capital — Default Interest Cron
Continues accruing penalty/default interest daily for loans in arrears or NPL state.

Referenced by cron_data.xml cron #10:
    env['alba.loan.interest.cron'].cron_continue_default_interest()
"""
import logging
from datetime import timedelta

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
            penalty_owed_to_date = balance_due * ((1 + daily_rate)^days_overdue - 1)

          `penalty_owed_to_date` is the cumulative penalty accrued on that
          instalment as of today and is stored on `penalty_due`. Only the
          INCREMENTAL amount since the last run (penalty_owed_to_date minus
          the previously stored penalty_due) is posted to the GL — posting
          the full cumulative total on every run would re-book penalty
          income already recognised on prior runs.

          `penalty_due` is the single source of truth for accrued-but-unpaid
          penalty on an instalment; loan_repayment.py's
          _auto_allocate_components() collects against it (never
          recalculating penalty independently) so the schedule's
          penalty_paid stays reconciled with what was actually accrued here.
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

            # Respect grace period before calculating penalties
            grace_days = product.grace_period_days or 0
            
            # Add collection stage additional penalty rate if applicable
            collection_stage = loan.collection_stage_id
            additional_penalty = collection_stage.additional_penalty_rate if collection_stage else 0.0
            total_daily_rate = product.penalty_rate + additional_penalty
            
            daily_rate = total_daily_rate / 100.0
            total_penalty_delta = 0.0
            lines_to_update = []

            overdue_lines = (loan.current_repayment_schedule_ids or loan.repayment_schedule_ids).filtered(
                lambda s: s.due_date and s.due_date < today and s.balance_due > 0
            )
            for line in overdue_lines:
                # Calculate effective due date respecting grace period
                effective_due_date = line.due_date + timedelta(days=grace_days)

                # Only calculate penalty if grace period has passed
                if effective_due_date < today:
                    days_overdue = (today - effective_due_date).days
                    penalty_owed_to_date = line.balance_due * ((1 + daily_rate) ** days_overdue - 1)
                    # Only the incremental amount since the last accrual run
                    # is new income — penalty_due already holds what was
                    # booked on prior runs.
                    delta = penalty_owed_to_date - line.penalty_due
                    if delta > 0.0:
                        total_penalty_delta += delta
                        lines_to_update.append((line, penalty_owed_to_date))

            if total_penalty_delta > 0.01:
                for line, penalty_owed_to_date in lines_to_update:
                    line.penalty_due = round(penalty_owed_to_date, 2)
                # ENTRY 3b — Penalty Accrual (Default/Penalty) — incremental only
                loan.action_post_penalty_accrual_entry(amount=total_penalty_delta)

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
                        "amount": total_penalty_delta,
                        "count": len(lines_to_update),
                        "rate": daily_rate * 100,
                    },
                    subtype_xmlid="mail.mt_note",
                )
                loans_processed += 1

        _logger.info(
            "cron_continue_default_interest: processed %d loan(s) with accrued penalty interest.",
            loans_processed,
        )
