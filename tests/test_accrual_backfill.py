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

    def test_rule3_payment_deferral_im0305(self):
        # Principal KES 2M, start_date Feb 26 (after 15th)
        start_date = date(2026, 2, 26)
        as_of_date = date(2026, 4, 28)

        # 1. First eligible accrual date is April 28
        first_date = get_first_eligible_accrual_date(start_date, cutoff_day=15)
        self.assertEqual(first_date, date(2026, 4, 28))

        # 2. Check periods generated up to April 28
        periods = list(iter_missing_accrual_periods(
            start_date, as_of_date, 28, investment_start=start_date, cutoff_day=15
        ))

        # March 28 cycle is deferred, so only 1 period is posted on April 28
        self.assertEqual(len(periods), 1)
        accrual_date, period_start, period_end = periods[0]
        self.assertEqual(accrual_date, date(2026, 4, 28))
        self.assertEqual(period_start, date(2026, 2, 27))  # Feb 26 + 1 day (Rule 1)
        self.assertEqual(period_end, date(2026, 4, 28))

        # 3. Interest calculation for combined period (Feb 27 - Apr 28)
        interest = compute_accrual_interest(
            opening_balance=2000000.0,
            annual_rate=36.0,
            period_start=period_start,
            period_end=period_end,
        )
        self.assertEqual(interest, 120000.0)  # KES 60k deferred March + KES 60k regular April

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
