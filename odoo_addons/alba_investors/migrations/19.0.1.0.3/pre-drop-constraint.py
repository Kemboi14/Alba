# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Drop the old unique constraint that prevented multiple investment products
    per type/currency/company before the module schema is updated during upgrade to 19.0.1.0.3.
    """
    cr.execute(
        """
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'alba_investment_product_type_currency_company_unique'
            ) THEN
                ALTER TABLE alba_investment_product
                    DROP CONSTRAINT alba_investment_product_type_currency_company_unique;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'alba_investment_product_investment_type_currency_id_company_id_key'
            ) THEN
                ALTER TABLE alba_investment_product
                    DROP CONSTRAINT alba_investment_product_investment_type_currency_id_company_id_key;
            END IF;
        END $$;
        """
    )
