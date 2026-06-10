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


class AccrualBackfillTests(unittest.TestCase):
    def test_previous_month_bounds_for_may_run_date(self):
        run_date = date(2026, 5, 28)
        period_start, period_end = previous_month_bounds(run_date)

        self.assertEqual(period_start, date(2026, 4, 1))
        self.assertEqual(period_end, date(2026, 4, 30))

    def test_iter_missing_accrual_periods_skips_before_start_date(self):
        start_date = date(2026, 3, 15)
        as_of_date = date(2026, 6, 28)

        periods = list(iter_missing_accrual_periods(start_date, as_of_date, 28))

        self.assertEqual(periods[0], (date(2026, 4, 28), date(2026, 3, 1), date(2026, 3, 31)))
        self.assertEqual(periods[1], (date(2026, 5, 28), date(2026, 4, 1), date(2026, 4, 30)))
        self.assertEqual(periods[2], (date(2026, 6, 28), date(2026, 5, 1), date(2026, 5, 31)))

        self.assertTrue(all(period_end >= start_date for _, _, period_end in periods))
