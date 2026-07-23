from datetime import date, timedelta


def _period_start_from_accrual_date(accrual_date):
    """
    Return the period_start for a given accrual_date under the 29th-to-28th rule.

    period_end   = 28th of accrual_date.month
    period_start = 29th of previous month
                 = date(prev_year, prev_month, 28) + timedelta(days=1)

    This naturally handles short months:
      - Feb accrual  → period_start = Jan 29
      - Mar accrual (leap year 2024)    → period_start = Feb 29
      - Mar accrual (non-leap year)     → period_start = Mar 1
        (because date(year, 2, 28) + 1 day = date(year, 3, 1) in non-leap years)
    """
    prev_month = accrual_date.month - 1 or 12
    prev_year = accrual_date.year if accrual_date.month > 1 else accrual_date.year - 1
    return date(prev_year, prev_month, 28) + timedelta(days=1)


def previous_month_bounds(run_date):
    """Return the previous 29th-to-28th accrual cycle bounds for a run date."""
    if run_date.day >= 28:
        period_end_year = run_date.year
        period_end_month = run_date.month
    else:
        period_end_month = run_date.month - 1 or 12
        period_end_year = run_date.year if run_date.month > 1 else run_date.year - 1

    period_end = date(period_end_year, period_end_month, 28)
    period_start = _period_start_from_accrual_date(period_end)
    return period_start, period_end


def accrual_run_date(year, month, target_day, env=None):
    """Return the accrual recording date for a given cycle, adjusted to the next
    working day when the target falls on a weekend or public holiday.

    Args:
        year, month : the accrual period month
        target_day  : preferred day of month (e.g. 28)
        env         : Odoo Environment; when provided, weekends and entries in
                      resource.calendar.leaves (global, time_type='leave') are
                      skipped.  When None, no adjustment is made.

    Returns:
        date: the (possibly adjusted) accrual date
    """
    d = date(year, month, min(target_day, 28))
    if env is None:
        return d

    # ── Advance past weekends ─────────────────────────────────────────────────
    while d.weekday() >= 5:          # 5 = Saturday, 6 = Sunday
        d += timedelta(days=1)

    # ── Advance past global public holidays ───────────────────────────────────
    def _is_holiday(check_date):
        dt_from = "%s 00:00:00" % check_date
        dt_to   = "%s 23:59:59" % check_date
        return bool(env["resource.calendar.leaves"].search([
            ("resource_id", "=", False),
            ("time_type", "=", "leave"),
            ("date_from", "<=", dt_to),
            ("date_to",   ">=", dt_from),
        ], limit=1))

    while _is_holiday(d):
        d += timedelta(days=1)
        # Re-check weekend after advancing past a holiday
        while d.weekday() >= 5:
            d += timedelta(days=1)

    return d


def iter_missing_accrual_periods(start_date, as_of_date, target_day,
                                  investment_start=None, cutoff_day=15,
                                  env=None):
    """
    Yield (accrual_date, period_start, period_end) for every month
    from start_date up to as_of_date, in ASCENDING order (oldest first).
    This ensures journal entries are posted chronologically and
    compound interest accumulates correctly.

    Period bounds follow the 29th-to-28th rule:
        period_end   = 28th of current month (= accrual_date)
        period_start = 29th of previous month
                     = date(prev_year, prev_month, 28) + timedelta(days=1)

    Business rules applied on the FIRST period only (i == 0):

    Rule 3 — After-cutoff-day rule:
        If investment_start.day > cutoff_day, the investment does NOT earn
        interest in the month it was received.  The first eligible period is
        the following month's cycle.  The earliest (first) period is skipped.

    Rule 1 — Day 0 exclusion:
        No interest accrues on the investment receipt date itself.
        Interest begins the NEXT calendar day (investment_start + 1 day).
        The first period's period_start is clamped to investment_start + 1.
        If that would push period_start beyond period_end, the period is
        skipped entirely (edge case: investment received on the 28th).

    Args:
        start_date:       First date from which to look for missing periods.
        as_of_date:       Upper bound (inclusive); no periods beyond this date.
        target_day:       Preferred day-of-month for the accrual_date (e.g. 28).
        investment_start: Optional date; if provided, Rules 1 and 3 are applied
                          to the first period.
        cutoff_day:       Day-of-month threshold for Rule 3 (default 15).
                          Investments received AFTER this day skip the first period.
        env:              Optional Odoo Environment.  When provided, the accrual
                          date is adjusted to the next working day (Rule 6).
    """
    periods = []
    current_year = as_of_date.year
    current_month = as_of_date.month

    while (current_year, current_month) >= (start_date.year, start_date.month):
        # period_end = 28th of current month
        period_end = date(current_year, current_month, 28)
        # period_start = 29th of previous month (handles leap years automatically)
        period_start = _period_start_from_accrual_date(period_end)

        accrual_date = accrual_run_date(current_year, current_month, target_day, env=env)

        if accrual_date <= as_of_date and period_end >= start_date:
            periods.append((accrual_date, period_start, period_end))

        current_month -= 1
        if current_month == 0:
            current_month = 12
            current_year -= 1

    # Yield oldest first so journal entries post chronologically
    for i, (accrual_date, period_start, period_end) in enumerate(reversed(periods)):
        if i == 0 and investment_start is not None:
            # ── Rule 3: After-cutoff-day — skip the receipt month entirely ──
            # Investments received after the cutoff day (default: 15th) earn no
            # interest in the month of receipt.  Their first eligible payment
            # cycle starts in the following month.
            if investment_start.day > cutoff_day:
                continue  # skip this (earliest) period; next iteration = following month

            # ── Rule 1: Day 0 exclusion — interest starts the NEXT day ──────
            # The investment receipt date itself is NOT an interest-bearing day.
            interest_start = investment_start + timedelta(days=1)
            if period_start < interest_start <= period_end:
                period_start = interest_start
            elif interest_start > period_end:
                # Edge case: investment received on the last day of the period
                # (e.g. day 28).  No interest can accrue this period.
                continue

        yield (accrual_date, period_start, period_end)
