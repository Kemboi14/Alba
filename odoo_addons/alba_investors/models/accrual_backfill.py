from datetime import date, timedelta


def accrual_run_date(year, month, target_day):
    """Return the accrual execution/recording date for a given accrual cycle."""
    return date(year, month, min(target_day, 28))


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


def iter_missing_accrual_periods(start_date, as_of_date, target_day,
                                  investment_start=None):
    """
    Yield (accrual_date, period_start, period_end) for every month
    from start_date up to as_of_date, in ASCENDING order (oldest first).
    This ensures journal entries are posted chronologically and
    compound interest accumulates correctly.

    The accrual_date is the 28th (or target_day) of the SAME month as the
    period it covers — not the following run month — so that the journal
    entry date matches the period month.

    Period bounds follow the 29th-to-28th rule:
        period_end   = 28th of current month (= accrual_date)
        period_start = 29th of previous month
                     = date(prev_year, prev_month, 28) + timedelta(days=1)

    Args:
        start_date:        First date from which to look for missing periods.
        as_of_date:        Upper bound (inclusive); no periods beyond this date.
        target_day:        Preferred day-of-month for the accrual_date (e.g. 28).
        investment_start:  Optional date; if provided, the first period's
                           period_start is clamped to this date for pro-rata
                           first-month interest.
    """
    periods = []
    current_year = as_of_date.year
    current_month = as_of_date.month

    while (current_year, current_month) >= (start_date.year, start_date.month):
        # period_end = 28th of current month
        period_end = date(current_year, current_month, 28)
        # period_start = 29th of previous month (handles leap years automatically)
        period_start = _period_start_from_accrual_date(period_end)

        accrual_date = accrual_run_date(current_year, current_month, target_day)

        if accrual_date <= as_of_date and period_end >= start_date:
            periods.append((accrual_date, period_start, period_end))

        current_month -= 1
        if current_month == 0:
            current_month = 12
            current_year -= 1

    # Yield oldest first so journal entries post chronologically
    for i, (accrual_date, period_start, period_end) in enumerate(reversed(periods)):
        # Pro-rata first month: clamp period_start to investment_start
        if i == 0 and investment_start is not None:
            if period_start < investment_start <= period_end:
                period_start = investment_start
        yield (accrual_date, period_start, period_end)
