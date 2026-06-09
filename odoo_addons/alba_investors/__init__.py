# -*- coding: utf-8 -*-
from . import models, wizard, report


def pre_init_hook(env):
    """Drop the old unique constraint that prevented multiple investment products
    per type/currency/company before the module schema is updated.
    The new logic uses an is_default boolean flag with a Python-level constraint.
    """
    env.cr.execute(
        """
        DO $$ BEGIN
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
