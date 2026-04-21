# -*- coding: utf-8 -*-
"""
Migration script for version 19.0.1.8.0
Creates wizard report actions and menus programmatically to avoid Odoo 19's
silent-drop of TransientModel act_window during upgrade.
"""
from odoo import api


def migrate(cr, version):
    """Create wizard report actions and menus using ORM."""
    env = api.Environment(cr, 1, {})
    
    # Import the helper function from hooks.py
    from odoo.addons.alba_loans.hooks import create_report_wizard_actions_and_menus
    
    # Create actions and menus
    create_report_wizard_actions_and_menus(env)
