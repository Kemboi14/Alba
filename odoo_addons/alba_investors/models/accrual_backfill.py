from calendar import monthrange
from datetime import date


def accrual_run_date(year, month, target_day):
    """Return the accrual execution date for a given calendar month."""
    last_day = monthrange(year, month)[1]
    return date(year, month, min(target_day, last_day))


def previous_month_bounds(run_date):
    """Return the previous calendar month bounds for a run date."""
    prev_year = run_date.year if run_date.month > 1 else run_date.year - 1
    prev_month = run_date.month - 1 or 12
    last_day = monthrange(prev_year, prev_month)[1]
    return date(prev_year, prev_month, 1), date(prev_year, prev_month, last_day)


def iter_missing_accrual_periods(start_date, as_of_date, target_day):
    """
    Yield accrual run dates and their previous-month periods, from newest to oldest,
    skipping any period that ends before the investment start date.
    """
    current_year = as_of_date.year
    current_month = as_of_date.month

    while (current_year, current_month) >= (start_date.year, start_date.month):
        run_date = accrual_run_date(current_year, current_month, target_day)
        if run_date <= as_of_date:
            period_start, period_end = previous_month_bounds(run_date)
            if period_end >= start_date:
                yield run_date, period_start, period_end
        current_month -= 1
        if current_month == 0:
            current_month = 12
            current_year -= 1
