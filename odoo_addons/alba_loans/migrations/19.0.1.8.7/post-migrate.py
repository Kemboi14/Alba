# -*- coding: utf-8 -*-
"""
Post-migration script for version 19.0.1.8.7
Adds penalty_due and penalty_paid fields to existing repayment schedule records.
"""

def migrate(cr, version):
    """
    Add penalty_due and penalty_paid columns to alba_repayment_schedule table
    and initialize them to 0.0 for existing records.
    """
    if not version:
        return
    
    # Check if columns already exist (in case migration is re-run)
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'alba_repayment_schedule' 
        AND column_name IN ('penalty_due', 'penalty_paid')
    """)
    existing_columns = {row[0] for row in cr.fetchall()}
    
    # Add penalty_due column if it doesn't exist
    if 'penalty_due' not in existing_columns:
        cr.execute("""
            ALTER TABLE alba_repayment_schedule 
            ADD COLUMN penalty_due NUMERIC DEFAULT 0.0
        """)
        cr.execute("""
            COMMENT ON COLUMN alba_repayment_schedule.penalty_due IS 
            'Accrued penalty/late fee amount for this instalment.'
        """)
    
    # Add penalty_paid column if it doesn't exist
    if 'penalty_paid' not in existing_columns:
        cr.execute("""
            ALTER TABLE alba_repayment_schedule 
            ADD COLUMN penalty_paid NUMERIC DEFAULT 0.0
        """)
        cr.execute("""
            COMMENT ON COLUMN alba_repayment_schedule.penalty_paid IS 
            'Penalty amount paid for this instalment.'
        """)
    
    # Initialize existing records with 0.0 values (if columns were just added)
    if 'penalty_due' not in existing_columns or 'penalty_paid' not in existing_columns:
        cr.execute("""
            UPDATE alba_repayment_schedule 
            SET penalty_due = 0.0, penalty_paid = 0.0 
            WHERE penalty_due IS NULL OR penalty_paid IS NULL
        """)
