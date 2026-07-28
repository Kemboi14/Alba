import importlib.util
import unittest
from datetime import date
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "odoo_addons" / "alba_investors" / "models" / "accrual_backfill.py"
SPEC = importlib.util.spec_from_file_location("accrual_backfill", MODULE_PATH)
accrual_backfill = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(accrual_backfill)

iter_missing_accrual_periods = accrual_backfill.iter_missing_accrual_periods
previous_month_bounds = accrual_backfill.previous_month_bounds
compute_accrual_interest = accrual_backfill.compute_accrual_interest
get_first_eligible_accrual_date = accrual_backfill.get_first_eligible_accrual_date
get_effective_period_start = accrual_backfill.get_effective_period_start
split_period_for_payout_cutoff = accrual_backfill.split_period_for_payout_cutoff


class AccrualBackfillTests(unittest.TestCase):
    def test_previous_month_bounds_for_may_run_date(self):
        run_date = date(2026, 5, 28)
        period_start, period_end = previous_month_bounds(run_date)

        self.assertEqual(period_start, date(2026, 4, 29))
        self.assertEqual(period_end, date(2026, 5, 28))

    def test_iter_missing_accrual_periods_without_investment_start(self):
        start_date = date(2026, 3, 15)
        as_of_date = date(2026, 6, 28)

        periods = list(iter_missing_accrual_periods(start_date, as_of_date, 28))

        self.assertEqual(periods[0], (date(2026, 3, 28), date(2026, 3, 1), date(2026, 3, 28)))
        self.assertEqual(periods[1], (date(2026, 4, 28), date(2026, 3, 29), date(2026, 4, 28)))
        self.assertEqual(periods[2], (date(2026, 5, 28), date(2026, 4, 29), date(2026, 5, 28)))
        self.assertEqual(periods[3], (date(2026, 6, 28), date(2026, 5, 29), date(2026, 6, 28)))

    def test_day_zero_rule_is_universal_for_post_cutoff_start(self):
        # Principal KES 2M, start_date Feb 26 (after 15th)
        start_date = date(2026, 2, 26)
        as_of_date = date(2026, 4, 28)

        periods = list(iter_missing_accrual_periods(
            start_date, as_of_date, 28, investment_start=start_date, cutoff_day=15
        ))

        self.assertEqual(len(periods), 3)

        first_accrual_date, first_period_start, first_period_end = periods[0]
        self.assertEqual(first_accrual_date, date(2026, 2, 28))
        self.assertEqual(first_period_start, date(2026, 2, 27))
        self.assertEqual(first_period_end, date(2026, 2, 28))

        second_accrual_date, second_period_start, second_period_end = periods[1]
        self.assertEqual(second_accrual_date, date(2026, 3, 28))
        self.assertEqual(second_period_start, date(2026, 3, 1))
        self.assertEqual(second_period_end, date(2026, 3, 28))

        third_accrual_date, third_period_start, third_period_end = periods[2]
        self.assertEqual(third_accrual_date, date(2026, 4, 28))
        self.assertEqual(third_period_start, date(2026, 3, 29))
        self.assertEqual(third_period_end, date(2026, 4, 28))

    def test_effective_period_start_uses_day_zero_rule_for_first_period(self):
        self.assertEqual(
            get_effective_period_start(date(2026, 2, 26), date(2026, 2, 26), is_first_period=True),
            date(2026, 2, 27),
        )
        self.assertEqual(
            get_effective_period_start(date(2026, 2, 26), date(2026, 3, 29), is_first_period=False),
            date(2026, 3, 29),
        )

    def test_split_period_for_payout_cutoff(self):
        self.assertEqual(split_period_for_payout_cutoff(date(2026, 2, 1), date(2026, 2, 10)), (10, 0))
        self.assertEqual(split_period_for_payout_cutoff(date(2026, 2, 16), date(2026, 2, 20)), (0, 5))
        self.assertEqual(split_period_for_payout_cutoff(date(2026, 2, 10), date(2026, 2, 20)), (6, 5))

    def test_rule3_within_cutoff_day(self):
        # Start date Feb 10 (on or before 15th)
        start_date = date(2026, 2, 10)
        as_of_date = date(2026, 4, 28)

        periods = list(iter_missing_accrual_periods(
            start_date, as_of_date, 28, investment_start=start_date, cutoff_day=15
        ))

        # First accrual posts on March 28
        self.assertEqual(len(periods), 2)
        self.assertEqual(periods[0], (date(2026, 3, 28), date(2026, 2, 11), date(2026, 3, 28)))
        self.assertEqual(periods[1], (date(2026, 4, 28), date(2026, 3, 29), date(2026, 4, 28)))
