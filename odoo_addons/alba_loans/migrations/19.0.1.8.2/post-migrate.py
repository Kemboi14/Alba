# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    """
    After the module upgrade, trigger the new _compute_state logic
    to ensure all loans are in their correct classification bucket
    based on their actual days in arrears.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Search for all loans that are in a performing state and recompute
    loans = env['alba.loan'].search([('state', 'not in', ('closed', 'written_off'))])
    if loans:
        # Trigger the compute logic
        loans._compute_state()
        # Ensure it's committed to DB
        env.add_to_compute(env['alba.loan']._fields['state'], loans)
        env.flush_all()
