def safe_investment_reference(investment, default="New"):
    """Return a stable investment reference for display and accounting strings.

    When an investment has not yet been assigned its sequence number, the
    ``investment_number`` field may be empty or False. In that case we fall back
    to the record id and, if that is also unavailable, to a generic label.
    """
    if investment is None:
        return default

    number = getattr(investment, "investment_number", False)
    if number not in (None, False, ""):
        return str(number)

    record_id = getattr(investment, "id", False)
    if record_id not in (None, False, ""):
        return str(record_id)

    return default
