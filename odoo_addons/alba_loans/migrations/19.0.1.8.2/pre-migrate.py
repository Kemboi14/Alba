# -*- coding: utf-8 -*-

def migrate(cr, version):
    """
    Migration: map legacy 'active' and 'npl' states to the new classification
    model so they appear correctly in filters and groupings.
    """
    # 1. Map 'active' to 'normal'
    cr.execute("UPDATE alba_loan SET state = 'normal' WHERE state = 'active'")
    # 2. Map 'npl' to 'substandard' (safest bet for 90+ days or manual NPL)
    cr.execute("UPDATE alba_loan SET state = 'substandard' WHERE state = 'npl'")
