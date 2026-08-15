# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.tests.common import BaseCase, TransactionCase

from ..models.accrual_backfill import (
    compute_annual_accrual_interest,
    get_annual_period_bounds,
    iter_missing_annual_periods,
    split_period_by_topups,
)


class TestAnnualAccrualMath(BaseCase):
    """Pure-function tests for the annual-compounding period/interest math —
    no Odoo environment needed, mirrors the monthly equivalents these
    functions were added alongside in accrual_backfill.py."""

    def test_full_year_interest(self):
        # 100,000 @ 12% p.a., exactly one 365-day cycle.
        interest = compute_annual_accrual_interest(
            opening_balance=100000.0,
            annual_rate=12.0,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
        )
        self.assertEqual(interest, 12000.0)

    def test_leap_year_366_days_still_treated_as_full_year(self):
        interest = compute_annual_accrual_interest(
            opening_balance=100000.0,
            annual_rate=12.0,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        # 2024 is a leap year -> 366 days, but still one full annual cycle.
        actual_days = (date(2024, 12, 31) - date(2024, 1, 1)).days + 1
        self.assertEqual(actual_days, 366)
        self.assertEqual(interest, 12000.0)

    def test_partial_year_is_prorated_act_365(self):
        # Half a year (~182 days) should earn roughly half the annual interest.
        interest = compute_annual_accrual_interest(
            opening_balance=100000.0,
            annual_rate=12.0,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 7, 1),
        )
        actual_days = (date(2026, 7, 1) - date(2026, 1, 1)).days + 1
        expected = round(100000.0 * 0.12 * actual_days / 365.0, 2)
        self.assertEqual(interest, expected)
        self.assertLess(interest, 6100.0)
        self.assertGreater(interest, 5900.0)

    def test_zero_inputs_return_zero(self):
        self.assertEqual(
            compute_annual_accrual_interest(0.0, 12.0, date(2026, 1, 1), date(2026, 12, 31)),
            0.00,
        )
        self.assertEqual(
            compute_annual_accrual_interest(100000.0, 0.0, date(2026, 1, 1), date(2026, 12, 31)),
            0.00,
        )

    def test_annual_period_bounds_first_cycle_applies_day0_exclusion(self):
        start = date(2026, 3, 10)
        period_start, period_end = get_annual_period_bounds(start, cycle_index=0)
        self.assertEqual(period_start, date(2026, 3, 11))  # start_date + 1 day
        self.assertEqual(period_end, date(2027, 3, 10))    # start_date + 1 year

    def test_annual_period_bounds_subsequent_cycle_has_no_day0_gap(self):
        start = date(2026, 3, 10)
        period_start, period_end = get_annual_period_bounds(start, cycle_index=1)
        self.assertEqual(period_start, date(2027, 3, 11))
        self.assertEqual(period_end, date(2028, 3, 10))

    def test_annual_period_bounds_handles_leap_day_anchor(self):
        # Anchored on Feb 29 of a leap year — relativedelta clamps the
        # anniversary to Feb 28 in non-leap years.
        start = date(2024, 2, 29)
        period_start, period_end = get_annual_period_bounds(start, cycle_index=0)
        self.assertEqual(period_start, date(2024, 3, 1))
        self.assertEqual(period_end, date(2025, 2, 28))

    def test_iter_missing_annual_periods_no_period_before_first_anniversary(self):
        start = date(2026, 3, 10)
        periods = list(iter_missing_annual_periods(start, as_of_date=date(2027, 3, 9)))
        self.assertEqual(periods, [])

    def test_iter_missing_annual_periods_yields_one_completed_cycle(self):
        start = date(2026, 3, 10)
        periods = list(iter_missing_annual_periods(start, as_of_date=date(2027, 3, 10)))
        self.assertEqual(len(periods), 1)
        accrual_date, period_start, period_end = periods[0]
        self.assertEqual(period_start, date(2026, 3, 11))
        self.assertEqual(period_end, date(2027, 3, 10))
        self.assertEqual(accrual_date, period_end)

    def test_iter_missing_annual_periods_yields_multiple_cycles_in_order(self):
        start = date(2024, 1, 1)
        periods = list(iter_missing_annual_periods(start, as_of_date=date(2027, 1, 2)))
        self.assertEqual(len(periods), 3)
        starts = [p[1] for p in periods]
        self.assertEqual(starts, sorted(starts))  # ascending, oldest first
        self.assertEqual(periods[0][1], date(2024, 1, 2))
        self.assertEqual(periods[0][2], date(2025, 1, 1))
        self.assertEqual(periods[2][2], date(2027, 1, 1))

    def test_iter_missing_annual_periods_no_start_date_yields_nothing(self):
        self.assertEqual(list(iter_missing_annual_periods(None, date(2027, 1, 1))), [])

    def test_split_period_by_topups_uses_provided_interest_fn(self):
        # A top-up mid-year should split into two annual sub-periods, each
        # computed via compute_annual_accrual_interest (ACT/365, no
        # intra-period compounding) — not the default monthly function.
        period_start = date(2026, 1, 1)
        period_end = date(2026, 12, 31)
        topup_date = date(2026, 7, 1)
        topups = [{"date": topup_date, "amount": 50000.0}]

        total = split_period_by_topups(
            opening_balance=100000.0,
            annual_rate=12.0,
            period_start=period_start,
            period_end=period_end,
            topups=topups,
            interest_fn=compute_annual_accrual_interest,
        )

        first_leg = compute_annual_accrual_interest(100000.0, 12.0, period_start, topup_date)
        second_leg = compute_annual_accrual_interest(
            150000.0, 12.0, topup_date + timedelta(days=1), period_end
        )
        self.assertEqual(total, round(first_leg + second_leg, 2))
        # Sanity: with a mid-year top-up, blended interest should sit
        # between the pre-topup-only and post-topup-only full-year amounts.
        self.assertGreater(total, 12000.0)
        self.assertLess(total, 18000.0)

    def test_split_period_by_topups_without_interest_fn_defaults_to_monthly(self):
        # No interest_fn passed -> falls back to compute_accrual_interest
        # (monthly convention), confirming the new parameter is fully
        # backward-compatible with every existing monthly call site.
        result = split_period_by_topups(
            opening_balance=100000.0,
            annual_rate=12.0,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )
        self.assertEqual(result, 1000.0)  # 100000 * 12%/12


class TestAnnualCompoundingOrm(TransactionCase):
    """ORM-level checks that the compounding_frequency dispatch is wired up
    correctly, without requiring the full accounting setup that posting a
    journal entry needs."""

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Annual Test Investor Partner"})
        self.investor = self.env["alba.investor"].create({
            "partner_id": self.partner.id,
            "id_number": "12345678",
            "date_of_birth": date(1990, 1, 1),
            "payment_details": "Test Bank Account 0000000000",
        })
        self.currency = (
            self.env.ref("base.KES")
            if self.env.ref("base.KES", raise_if_not_found=False)
            else self.env.company.currency_id
        )
        self.product = self.env["alba.investment.product"].create({
            "name": "Annual Test Product",
            "code": "ANNUAL-TEST",
            "investment_type": "open_ended",
            "interest_rate": 12.0,
            "compounding_frequency": "annual",
            "currency_id": self.currency.id,
            "company_id": self.env.company.id,
        })
        self.investment = self.env["alba.investment"].create({
            "investor_id": self.investor.id,
            "investment_product_id": self.product.id,
            "investment_type": "open_ended",
            "principal_amount": 100000.0,
            "interest_rate": 12.0,
            "compounding_frequency": "annual",
            "start_date": date(2026, 1, 1),
            "currency_id": self.currency.id,
            "state": "active",
        })

    def test_product_and_investment_accept_annual_selection(self):
        self.assertEqual(self.product.compounding_frequency, "annual")
        self.assertEqual(self.investment.compounding_frequency, "annual")

    def test_rule3_remediation_skips_annual_investments(self):
        # Rule 3 (after-cutoff-day deferral) is monthly-cycle-specific and
        # must no-op for annually-compounding investments rather than
        # attempting (and failing) monthly-style remediation on them. The
        # real assertion is simply that it does not raise for an annual
        # investment (it would previously have run the monthly cutoff-day
        # math against a start_date it doesn't apply to).
        result = self.investment.action_remediate_rule3_violations()
        self.assertEqual(result["params"]["message"], "Successfully remediated 0 investment(s).")

    def test_backfill_produces_no_periods_before_first_anniversary(self):
        # No annual cycle has elapsed yet one day after start_date.
        self.investment.action_backfill_missing_accruals(as_of_date=date(2026, 1, 2))
        self.assertEqual(len(self.investment.accrual_ids), 0)
