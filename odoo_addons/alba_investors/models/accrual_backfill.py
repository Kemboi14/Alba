from datetime import date, timedelta

from dateutil.relativedelta import relativedelta


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
    """Return the accrual recording date for a given cycle (always the 28th of the month).

    Args:
        year, month : the accrual period month
        target_day  : preferred day of month (e.g. 28)
        env         : Odoo Environment (unused, kept for signature compatibility)

    Returns:
        date: the accrual date (28th of the specified year and month)
    """
    return date(year, month, min(target_day, 28))



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
    Uses monthly rate formula: principal × (annual_rate/100) × days/30

    Every ordinary single-cycle period (28-31 days, per the 29th-to-28th
    calendar rule) charges a flat one month's interest regardless of the
    actual day count — a 28-day cycle and a 31-day cycle both earn exactly
    one month at annual_rate/12. A genuine multi-month cycle (Rule 3 payment
    deferral combining two or more calendar months into one accrual, ~58+
    days) collapses the same way to a flat N-month rate. Only a genuine
    partial/stub period that doesn't round to a whole month (e.g. the
    Day-0-exclusion first period, which can be under 30 days) is prorated
    by actual_days/30.

    Only ever called on a WHOLE period (never a top-up fragment — see
    split_period_by_topups(), which no longer fragments the base balance
    at all).
    """
    if not opening_balance or not annual_rate or not period_start or not period_end:
        return 0.00

    monthly_rate = annual_rate / 100.0 / 12.0  # Monthly rate (e.g., 36% p.a. -> 3% = 0.03, 30% p.a. -> 2.5% = 0.025)
    full_month_interest = opening_balance * monthly_rate

    actual_days = (period_end - period_start).days + 1

    months = round(actual_days / 30.0)
    if months >= 1 and abs(actual_days - months * 30) <= 3:
        return round(months * full_month_interest, 2)
    else:
        return round(full_month_interest * actual_days / 30.0, 2)


def compute_annual_accrual_interest(opening_balance, annual_rate, period_start, period_end):
    """
    Compute interest amount for an annually-compounding accrual period.

    Full cycle: opening_balance × (annual_rate / 100).
    Partial cycle (only ever the Day-0-excluded first period — see
    get_annual_period_bounds): prorated by actual_days / 365.

    A full annual cycle is 365 or 366 days (leap year) — anything within 3
    days of either is treated as exactly one year, mirroring the ±3-day
    tolerance compute_accrual_interest uses to treat 28-31 day periods as
    one full month.
    """
    if not opening_balance or not annual_rate or not period_start or not period_end:
        return 0.00

    full_year_interest = opening_balance * (annual_rate / 100.0)
    actual_days = (period_end - period_start).days + 1

    if abs(actual_days - 365) <= 3 or abs(actual_days - 366) <= 3:
        return round(full_year_interest, 2)
    return round(full_year_interest * actual_days / 365.0, 2)


def get_annual_period_bounds(investment_start, cycle_index):
    """
    Return (period_start, period_end) for annual cycle `cycle_index` (0-based)
    of an annually-compounding investment, anchored to its own start_date
    anniversary — not a fixed calendar date, unlike the monthly 29th-28th rule.

    cycle_index 0: period_start = start_date + 1 day  (Day-0 exclusion),
                   period_end   = start_date + 1 year.
    cycle_index N: period_start = start_date + N years + 1 day,
                   period_end   = start_date + (N + 1) years.
    """
    period_end = investment_start + relativedelta(years=cycle_index + 1)
    period_start = investment_start + relativedelta(years=cycle_index) + timedelta(days=1)
    return period_start, period_end


def iter_missing_annual_periods(investment_start, as_of_date):
    """
    Yield (accrual_date, period_start, period_end) for every completed annual
    cycle of an annually-compounding investment, oldest first, up to as_of_date.

    Unlike the monthly cycle, a cycle is only ever yielded once it has fully
    elapsed — annual compounding has nothing to post mid-year. accrual_date
    equals period_end: the cycle is recorded on its own closing anniversary
    rather than a fixed day-of-month.
    """
    if not investment_start:
        return
    cycle_index = 0
    while True:
        period_start, period_end = get_annual_period_bounds(investment_start, cycle_index)
        if period_end > as_of_date:
            break
        yield (period_end, period_start, period_end)
        cycle_index += 1


def split_period_by_topups(opening_balance, annual_rate, period_start, period_end, topups=None, interest_fn=None):
    """
    Compute total period interest when top-ups occur mid-period.

    The base balance is NEVER fragmented — the whole period's interest is
    computed on opening_balance exactly as any ordinary period would be
    (flat-month rule included), via interest_fn. Each top-up then adds its
    OWN separate contribution on top, independent of every other top-up in
    the period:

        topup_amount × monthly_rate × min(days, 28) / 30

    where days = the Day-0-excluded day count from (topup_date + 1)
    through period_end. The 28-day cap mirrors the fact that every
    accrual period's own natural end is the 28th — a top-up can never
    earn more than that many of the period's 30 nominal days, even when
    the actual calendar gap to period_end is longer (e.g. a top-up early
    in a 31-day cycle). Top-ups do not interact with or truncate each
    other's windows; each is measured independently against the same
    period_end.

    Args:
        opening_balance (float): Balance at period_start (prior to in-period top-ups).
        annual_rate (float): Annual interest rate percentage.
        period_start (date): Start of overall accrual period.
        period_end (date): End of overall accrual period.
        topups (iterable): Objects or dicts with date and amount for posted top-ups
                           occurring within [period_start, period_end].
        interest_fn: whole-period interest function to use for the base
                     balance, defaults to compute_accrual_interest. Pass
                     compute_annual_accrual_interest for annually-compounding
                     investments.

    Returns:
        float: Total rounded interest for the period.
    """
    if not opening_balance or not annual_rate or not period_start or not period_end:
        return 0.00

    interest_fn = interest_fn or compute_accrual_interest

    topups_by_date = {}
    for t in (topups or []):
        t_date = getattr(t, "date", None) or (t.get("date") if isinstance(t, dict) else None)
        t_amount = getattr(t, "amount", None) or (t.get("amount") if isinstance(t, dict) else 0.0)
        if t_date and period_start <= t_date <= period_end:
            topups_by_date[t_date] = topups_by_date.get(t_date, 0.0) + t_amount

    base_interest = interest_fn(opening_balance, annual_rate, period_start, period_end)

    if not topups_by_date:
        return base_interest

    monthly_rate = annual_rate / 100.0 / 12.0
    total_interest = base_interest

    for topup_date, topup_amount in topups_by_date.items():
        days = min((period_end - topup_date).days, 28)
        total_interest += topup_amount * monthly_rate * days / 30.0

    return round(total_interest, 2)




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

