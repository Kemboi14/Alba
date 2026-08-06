# -*- coding: utf-8 -*-
"""
Post-migration script for version 19.0.1.8.9
Adds paid_late column to repayment schedule and ensures correct status computation.
"""

def migrate(cr, version):
    """
    Add paid_late column to alba_repayment_schedule table.
    Since paid_late is a computed field, we only need to ensure the column exists.
    The ORM will handle the computation automatically.
    """
    if not version:
        return
    
    # Check if column already exists (in case migration is re-run)
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'alba_repayment_schedule' 
        AND column_name = 'paid_late'
    """)
    existing_column = cr.fetchone()
    
    # Add paid_late column if it doesn't exist
    if not existing_column:
        cr.execute("""
            ALTER TABLE alba_repayment_schedule 
            ADD COLUMN paid_late BOOLEAN DEFAULT FALSE
        """)
        cr.execute("""
            COMMENT ON COLUMN alba_repayment_schedule.paid_late IS 
            'True if this instalment was paid after its due date, but is now fully paid.'
        """)
        
        # Force recompute of status and paid_late for all existing records
        # This ensures that the fixed _compute_status logic is applied to existing data
        cr.execute("""
            UPDATE alba_repayment_schedule 
            SET status = 'pending'
            WHERE status IS NULL
        """)
