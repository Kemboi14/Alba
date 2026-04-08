# -*- coding: utf-8 -*-

from . import (
    # Base models first (no dependencies)
    loan_product,
    customer,
    mpesa_config,
    loan_document,
    # Models with dependencies
    loan_application,
    loan,
    loan_repayment,
    repayment_schedule,
    loan_rules,
    collections,
    approval_workflow,
    investor,
    mpesa_transaction,
    report_financials,
)
