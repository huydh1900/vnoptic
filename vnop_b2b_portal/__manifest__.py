# -*- coding: utf-8 -*-
{
    'name': 'VNOptic B2B Portal',
    'version': '18.0.1.0.0',
    'summary': 'Portal B2B đại lý: catalog, cart, đặt đơn, công nợ',
    'category': 'Sales/Portal',
    'author': 'VNOptic',
    'depends': [
        'base',
        'mail',
        'portal',
        'sale_management',
        'account',
        'vnop_sale_channel',
    ],
    'data': [
        'security/ir_rule.xml',
        'templates/portal_layout.xml',
        'templates/portal_home.xml',
        'templates/portal_catalog.xml',
        'templates/portal_cart.xml',
        'templates/portal_financial.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
