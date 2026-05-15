# -*- coding: utf-8 -*-
{
    'name': 'Internal Transfer Payments',
    'summary': 'Manage and streamline internal transfer payments between journals',
    'description': """
        Internal Transfer Payments
        ==========================
        
        This module enhances Odoo's accounting by improving the handling of internal transfer payments between journals.
        
        Key Features:
        -------------
        - Simplified internal transfer workflow
        - Better tracking between source and destination journals
        - Improved visibility of transfer operations
        - Seamless integration with accounting module
        
        Use Cases:
        ----------
        - Transfer funds between bank accounts
        - Manage internal cash movements
        - Improve financial tracking accuracy
        
        Notes:
        ------
        - Fully compatible with Odoo 18 Accounting
        - Designed for ease of use and reliability
    """,
    'author': 'Touch Business Solutions',
    'website': 'https://finaltouches.sa',
    'category': 'Accounting',
    'version': '19.0.1.0.0',
    'license': 'OPL-1',
    'price': 10.0,
    'currency': 'USD',
    'depends': ['account'],
    'data': [
        'views/journal.xml',
        'views/payment.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'images': ['static/description/banner.png'],
}