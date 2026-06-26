from calendar import monthrange
from datetime import date


def accrual_run_date(year, month, target_day):
    """Return the accrual execution/recording date for a given calendar month.

    Used for two purposes:
      1. Scheduling: when the cron should run (e.g. the 28th of the current month).
      2. Period-month dating: the accrual_date stamped on a record should fall
         in the SAME month as the period it covers, not the following month.
    """
    last_day = monthrange(year, month)[1]
    return date(year, month, min(target_day, last_day))


def previous_month_bounds(run_date):
    """Return the previous calendar month bounds for a run date."""
    prev_year = run_date.year if run_date.month > 1 else run_date.year - 1
    prev_month = run_date.month - 1 or 12
    last_day = monthrange(prev_year, prev_month)[1]
    return date(prev_year, prev_month, 1), date(prev_year, prev_month, last_day)


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
    from calendar import monthrange
    periods = []
    current_year = as_of_date.year
    current_month = as_of_date.month

    while (current_year, current_month) >= (start_date.year, start_date.month):
        # Compute period bounds for THIS month
        last_day = monthrange(current_year, current_month)[1]
        period_start = date(current_year, current_month, 1)
        period_end = date(current_year, current_month, last_day)

        # Accrual date is target_day of THIS period month
        accrual_date = accrual_run_date(current_year, current_month, target_day)

        # Only include if accrual_date has already passed
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
