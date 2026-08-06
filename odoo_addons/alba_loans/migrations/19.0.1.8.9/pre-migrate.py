# -*- coding: utf-8 -*-
"""
Pre-migration script for version 19.0.1.8.9
Validates repayment schedule data before fixing status computation logic.
"""

def migrate(cr, version):
    """
    Validate existing repayment schedule data before fixing status computation.
    """
    if not version:
        return
    
    # Check for data anomalies that might affect the status fix
    cr.execute("""
        SELECT COUNT(*) 
        FROM alba_repayment_schedule 
        WHERE total_due < 0 OR total_paid < 0 OR balance_due < 0
    """)
    negative_count = cr.fetchone()[0]
    
    if negative_count > 0:
        # Log warning but don't fail migration
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "Found %d repayment schedule records with negative amounts. "
            "These should be reviewed for data quality.",
            negative_count
        )
    
    # Check for orphaned schedule records (no loan)
    cr.execute("""
        SELECT COUNT(*) 
        FROM alba_repayment_schedule s
        LEFT JOIN alba_loan l ON s.loan_id = l.id
        WHERE l.id IS NULL
    """)
    orphan_count = cr.fetchone()[0]
    
    if orphan_count > 0:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "Found %d orphaned repayment schedule records (no linked loan). "
            "These will not be affected by the status computation fix.",
            orphan_count
        )
