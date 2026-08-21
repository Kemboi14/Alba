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
split_period_by_topups = accrual_backfill.split_period_by_topups


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

        self.assertEqual(len(periods), 3)
        self.assertEqual(periods[0], (date(2026, 2, 28), date(2026, 2, 11), date(2026, 2, 28)))
        self.assertEqual(periods[1], (date(2026, 3, 28), date(2026, 3, 1), date(2026, 3, 28)))
        self.assertEqual(periods[2], (date(2026, 4, 28), date(2026, 3, 29), date(2026, 4, 28)))


    def test_split_period_by_topups_single_topup_im0498(self):
        # IM-0498: Feb 4-28, 2026 (25 days total). Rate: 36% p.a. (3% monthly). Opening balance: 600,000.
        # Top-up: Feb 11 of 100,000.
        # Sub1 (Feb 4-11, 8d on 600k @ 3%): 4,800.00
        # Sub2 (Feb 12-28, 17d on 700k @ 3%): 11,900.00
        # Expected total: 16,700.00 (No intra-period compounding)
        res = split_period_by_topups(
            opening_balance=600000.0,
            annual_rate=36.0,
            period_start=date(2026, 2, 4),
            period_end=date(2026, 2, 28),
            topups=[{"date": date(2026, 2, 11), "amount": 100000.0}],
        )
        self.assertEqual(res, 16700.0)

    def test_split_period_by_topups_zero_topups(self):
        # Regression check: zero top-ups must match compute_accrual_interest directly
        op = 600000.0
        rate = 36.0
        p_start = date(2026, 2, 4)
        p_end = date(2026, 2, 28)
        direct = compute_accrual_interest(op, rate, p_start, p_end)
        split_res = split_period_by_topups(op, rate, p_start, p_end, topups=[])
        self.assertEqual(split_res, direct)
        self.assertEqual(split_res, 15000.0)

    def test_monthly_interest_30_percent_annual_rate_on_600k(self):
        # 30% per annum on 600,000 balance = 600,000 * 30% / 12 = 15,000.00 for a
        # full 30-day month. Feb 1-28, 2026 is only 28 days (an ordinary single
        # cycle, not a Rule-3 combined one), so it's prorated: 15,000 * 28/30 = 14,000.00.
        res = compute_accrual_interest(
            opening_balance=600000.0,
            annual_rate=30.0,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
        )
        self.assertEqual(res, 14000.0)

    def test_monthly_interest_31_day_cycle_is_prorated_not_flat(self):
        # An ordinary 31-day single cycle (e.g. Dec 29 - Jan 28) must earn
        # 31/30 of a month, not be capped at a flat one month: this is the
        # regression this fix targets (months >= 2, not months >= 1).
        res = compute_accrual_interest(
            opening_balance=600000.0,
            annual_rate=30.0,
            period_start=date(2025, 12, 29),
            period_end=date(2026, 1, 28),
        )
        self.assertEqual(res, 15500.0)  # 15,000 * 31/30

    def test_monthly_interest_genuine_two_month_combined_cycle_stays_flat(self):
        # A genuine Rule-3 deferred cycle combining two calendar months
        # (~60 days) must still collapse to a flat 2-month rate, not prorate
        # by actual_days/30 - that's the one case months >= 2 preserves.
        res = compute_accrual_interest(
            opening_balance=600000.0,
            annual_rate=30.0,
            period_start=date(2026, 1, 27),
            period_end=date(2026, 3, 28),  # 61 days
        )
        self.assertEqual(res, 30000.0)  # 2 x 15,000, not 15,000 * 61/30

    def test_split_period_by_topups_two_topups(self):
        # 2 top-ups: Feb 1-28. Opening 1,000,000, 36% p.a. (3% monthly).
        # Topup 1: Feb 10 (200k), Topup 2: Feb 20 (300k).
        # Sub1 (Feb 1-10, 10d @ 1.0M): 10,000.00
        # Sub2 (Feb 11-20, 10d @ 1.2M): 12,000.00
        # Sub3 (Feb 21-28, 8d @ 1.5M): 12,000.00
        # Expected total: 34,000.00
        res = split_period_by_topups(
            opening_balance=1000000.0,
            annual_rate=36.0,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            topups=[
                {"date": date(2026, 2, 10), "amount": 200000.0},
                {"date": date(2026, 2, 20), "amount": 300000.0},
            ],
        )
        self.assertEqual(res, 34000.0)

    def test_split_period_by_topups_three_topups(self):
        # 3 top-ups: Feb 1-28. Opening 1,000,000, 36% p.a. (3% monthly).
        # Topup 1: Feb 5 (100k), Topup 2: Feb 15 (200k), Topup 3: Feb 25 (300k).
        # Sub1 (Feb 1-5, 5d @ 1.0M): 5,000.00
        # Sub2 (Feb 6-15, 10d @ 1.1M): 11,000.00
        # Sub3 (Feb 16-25, 10d @ 1.3M): 13,000.00
        # Sub4 (Feb 26-28, 3d @ 1.6M): 4,800.00
        # Expected total: 33,800.00
        res = split_period_by_topups(
            opening_balance=1000000.0,
            annual_rate=36.0,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            topups=[
                {"date": date(2026, 2, 5), "amount": 100000.0},
                {"date": date(2026, 2, 15), "amount": 200000.0},
                {"date": date(2026, 2, 25), "amount": 300000.0},
            ],
        )
        self.assertEqual(res, 33800.0)


