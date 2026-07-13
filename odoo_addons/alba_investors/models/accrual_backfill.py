from datetime import date


def accrual_run_date(year, month, target_day):
    """Return the accrual execution/recording date for a given accrual cycle."""
    return date(year, month, min(target_day, 28))


def previous_month_bounds(run_date):
    """Return the previous 28th-to-27th accrual cycle bounds for a run date."""
    if run_date.day >= 28:
        period_end_year = run_date.year
        period_end_month = run_date.month
    else:
        period_end_month = run_date.month - 1 or 12
        period_end_year = run_date.year if run_date.month > 1 else run_date.year - 1

    period_end = date(period_end_year, period_end_month, 27)
    start_month = period_end.month - 1 or 12
    start_year = period_end.year if period_end.month > 1 else period_end.year - 1
    period_start = date(start_year, start_month, 28)
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
        period_start = date(current_year, current_month, 28)
        if current_month == 12:
            period_end = date(current_year + 1, 1, 27)
        else:
            period_end = date(current_year, current_month + 1, 27)

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
