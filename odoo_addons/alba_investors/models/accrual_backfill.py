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


def get_first_eligible_accrual_date(investment_start, cutoff_day=15):
    """
    Return the first accrual posting date for an investment under Rule 3 (Payment Deferral).

    Rule 3 — Payment Deferral rule:
    - If investment_start.day <= cutoff_day (e.g. Feb 10 <= 15):
        First accrual is posted in month M+1 (e.g. March 28).
    - If investment_start.day > cutoff_day (e.g. Feb 26 > 15):
        The receipt month accrual (March 28) is deferred.
        First accrual is posted in month M+2 (e.g. April 28).
    """
    if not investment_start:
        return None
    if investment_start.day <= cutoff_day:
        m = investment_start.month % 12 + 1
        y = investment_start.year + (1 if investment_start.month == 12 else 0)
        return date(y, m, 28)
    else:
        m = (investment_start.month + 1) % 12 + 1
        y = investment_start.year + ((investment_start.month + 1) // 12)
        return date(y, m, 28)


def get_first_eligible_accrual_start(investment_start, cutoff_day=15):
    """
    Return the earliest interest-bearing start date for an investment.
    Under Rule 1 (Day 0 exclusion), interest starts on investment_start + 1 day.
    """
    if not investment_start:
        return None
    return investment_start + timedelta(days=1)


def get_effective_period_start(investment_start, period_start, is_first_period=False):
    """Return the effective accrual start date after applying the universal Day-0 rule."""
    if not investment_start or not is_first_period:
        return period_start
    return max(period_start, investment_start + timedelta(days=1))


def split_period_for_payout_cutoff(period_start, period_end, interest_amount=None):
    """Split a period by the 15th cutoff for payout eligibility.

    Returns either (eligible_days, deferred_days) or, when interest_amount is provided,
    (eligible_amount, deferred_amount).
    """
    if not period_start or not period_end:
        return (0, 0) if interest_amount is None else (0.0, 0.0)

    total_days = (period_end - period_start).days + 1
    cutoff_date = date(period_end.year, period_end.month, 15)

    if period_end <= cutoff_date:
        eligible_days = total_days
        deferred_days = 0
    elif period_start > cutoff_date:
        eligible_days = 0
        deferred_days = total_days
    else:
        eligible_days = (cutoff_date - period_start).days + 1
        deferred_days = (period_end - cutoff_date).days

    if interest_amount is None:
        return eligible_days, deferred_days

    eligible_amount = round(interest_amount * eligible_days / float(total_days), 2)
    deferred_amount = round(interest_amount - eligible_amount, 2)
    return eligible_amount, deferred_amount


def compute_accrual_interest(opening_balance, annual_rate, period_start, period_end):
    """
    Compute interest amount for an accrual period.
    Supports standard 1-month cycles, partial initial cycles, and multi-month deferred cycles.
    """
    if not opening_balance or not annual_rate or not period_start or not period_end:
        return 0.00

    monthly_rate = annual_rate / 100.0 / 12.0
    full_month_interest = opening_balance * monthly_rate

    actual_days = (period_end - period_start).days + 1

    months = round(actual_days / 30.0)
    if months >= 1 and abs(actual_days - months * 30) <= 3:
        return round(months * full_month_interest, 2)
    else:
        return round(full_month_interest * actual_days / 30.0, 2)


def iter_missing_accrual_periods(start_date, as_of_date, target_day,
                                  investment_start=None, cutoff_day=15,
                                  env=None):
    """
    Yield (accrual_date, period_start, period_end) for every month
    from start_date up to as_of_date, in ASCENDING order (oldest first).

    Period bounds follow the 29th-to-28th rule.

    The universal Day-0 rule is applied to the first period only: interest
    begins on investment_start + 1 day. The 15th/16th cutoff no longer affects
    accrual periods or their boundaries.
    """
    periods = []
    current_year = as_of_date.year
    current_month = as_of_date.month

    while (current_year, current_month) >= (start_date.year, start_date.month):
        period_end = date(current_year, current_month, 28)
        period_start = _period_start_from_accrual_date(period_end)
        accrual_date = accrual_run_date(current_year, current_month, target_day, env=env)

        if accrual_date <= as_of_date and period_end >= start_date:
            periods.append((accrual_date, period_start, period_end))

        current_month -= 1
        if current_month == 0:
            current_month = 12
            current_year -= 1

    effective_periods = []
    for accrual_date, period_start, period_end in reversed(periods):
        effective_periods.append((accrual_date, period_start, period_end))

    for i, (accrual_date, period_start, period_end) in enumerate(effective_periods):
        period_start = get_effective_period_start(
            investment_start,
            period_start,
            is_first_period=(investment_start is not None and i == 0),
        )
        yield (accrual_date, period_start, period_end)

