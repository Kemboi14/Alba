# -*- coding: utf-8 -*-
"""
Pre-migration script for version 19.0.1.8.8
Validates data before adding penalty fields to repayment schedule.
"""

def migrate(cr, version):
    """
    Validate existing repayment schedule data before adding penalty fields.
    """
    if not version:
        return
    
    # Check for any data inconsistencies that might affect penalty calculation
    cr.execute("""
        SELECT COUNT(*) 
        FROM alba_repayment_schedule 
        WHERE principal_due < 0 OR interest_due < 0
    """)
    inconsistent_count = cr.fetchone()[0]
    
    if inconsistent_count > 0:
        # Log warning but don't fail migration
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "Found %d repayment schedule records with negative due amounts. "
            "These will not affect penalty calculation but should be reviewed.",
            inconsistent_count
        )
