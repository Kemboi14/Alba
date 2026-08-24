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
        # full month. Feb 1-28, 2026 is only 28 days but is an ordinary single
        # cycle, so it charges a flat one month's interest regardless: 15,000.00.
        res = compute_accrual_interest(
            opening_balance=600000.0,
            annual_rate=30.0,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
        )
        self.assertEqual(res, 15000.0)

    def test_monthly_interest_31_day_cycle_stays_flat(self):
        # An ordinary 31-day single cycle (e.g. Dec 29 - Jan 28) still earns
        # exactly one flat month's interest, not 31/30 of a month.
        res = compute_accrual_interest(
            opening_balance=600000.0,
            annual_rate=30.0,
            period_start=date(2025, 12, 29),
            period_end=date(2026, 1, 28),
        )
        self.assertEqual(res, 15000.0)  # flat one month, not 15,000 * 31/30

    def test_monthly_interest_genuine_two_month_combined_cycle_stays_flat(self):
        # A genuine Rule-3 deferred cycle combining two calendar months
        # (~60 days) collapses to a flat 2-month rate, not prorated
        # by actual_days/30.
        res = compute_accrual_interest(
            opening_balance=600000.0,
            annual_rate=30.0,
            period_start=date(2026, 1, 27),
            period_end=date(2026, 3, 28),  # 61 days
        )
        self.assertEqual(res, 30000.0)  # 2 x 15,000, not 15,000 * 61/30

    def test_split_period_by_topups_two_topups(self):
        # 2 top-ups: Feb 1-28 (28 days - flattens to a whole month on its
        # own). Opening 1,000,000, 36% p.a. (3% monthly).
        # Topup 1: Feb 10 (200k), Topup 2: Feb 20 (300k).
        # Base (whole period, flat since 28 days is within tolerance): 30,000.00
        # Topup1: 200,000 * 3% * min(18, 28)/30 = 3,600.00
        # Topup2: 300,000 * 3% * min(8, 28)/30 = 2,400.00
        # Expected total: 36,000.00
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
        self.assertEqual(res, 36000.0)

    def test_split_period_by_topups_caps_topup_window_at_28_days(self):
        # Regression, confirmed against real accountant figures for IM-0478:
        # a top-up landing early in a 31-day period must never earn more
        # than 28 of that period's days, even though the actual calendar
        # gap to period_end is longer (29 days here) - every period's own
        # natural end is the 28th, and a top-up can't exceed that.
        # Opening 100,300.00, 36% p.a. (3% monthly), period May29-Jun28 (31d).
        # Topup1 May30 (50,000): raw gap to period_end is 29 days, capped to 28.
        # Topup2 Jun22 (50,000): raw gap is 6 days, well under the cap.
        # Base (31 days, flat): 100,300 * 3% = 3,009.00
        # Topup1: 50,000 * 3% * 28/30 = 1,400.00 (NOT 50,000 * 3% * 29/30 = 1,450.00)
        # Topup2: 50,000 * 3% * 6/30 = 300.00
        # Expected total: 4,709.00
        res = split_period_by_topups(
            opening_balance=100300.0,
            annual_rate=36.0,
            period_start=date(2026, 5, 29),
            period_end=date(2026, 6, 28),
            topups=[
                {"date": date(2026, 5, 30), "amount": 50000.0},
                {"date": date(2026, 6, 22), "amount": 50000.0},
            ],
        )
        self.assertEqual(res, 4709.0)

    def test_split_period_by_topups_single_topup_under_cap_unaffected(self):
        # Confirmed against real accountant figures for IM-0442: a single
        # top-up whose own window is already under 28 days is completely
        # unaffected by the cap.
        # Opening 409,477.01, 36% p.a. (3% monthly), period May29-Jun28 (31d).
        # Topup Jun20 (130,000): gap to period_end is 8 days, under the cap.
        # Base (31 days, flat): 409,477.01 * 3% = 12,284.31
        # Topup: 130,000 * 3% * 8/30 = 1,040.00
        # Expected total: 13,324.31
        res = split_period_by_topups(
            opening_balance=409477.01,
            annual_rate=36.0,
            period_start=date(2026, 5, 29),
            period_end=date(2026, 6, 28),
            topups=[{"date": date(2026, 6, 20), "amount": 130000.0}],
        )
        self.assertEqual(res, 13324.31)

    def test_split_period_by_topups_three_topups(self):
        # 3 top-ups: Feb 1-28 (28 days - flattens to a whole month on its
        # own). Opening 1,000,000, 36% p.a. (3% monthly).
        # Topup 1: Feb 5 (100k), Topup 2: Feb 15 (200k), Topup 3: Feb 25 (300k).
        # Base (whole period, flat): 30,000.00
        # Topup1: 100,000 * 3% * min(23, 28)/30 = 2,300.00
        # Topup2: 200,000 * 3% * min(13, 28)/30 = 2,600.00
        # Topup3: 300,000 * 3% * min(3, 28)/30 = 900.00
        # Expected total: 35,800.00
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
        self.assertEqual(res, 35800.0)


