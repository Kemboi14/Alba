# -*- coding: utf-8 -*-
import os
import sys

# Mock Odoo environment if possible, or just check if the file is correctly imported.
# Since I can't easily run Odoo environment here, I'll just check for syntax errors.

try:
    from odoo_addons.alba_investors.models import currency_sync
    print("Successfully imported currency_sync")
    # Check if the class is defined
    if hasattr(currency_sync, 'AlbaCurrencyRateSync'):
        print("AlbaCurrencyRateSync class found")
    else:
        print("AlbaCurrencyRateSync class NOT found")
except Exception as e:
    print(f"Error: {e}")
