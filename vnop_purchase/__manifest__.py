# -*- coding: utf-8 -*-
{
    'name': "vnop_purchase",
    # always loaded
    'depends': ['purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/purchase_order_views.xml',
        'views/purchase_contract_views.xml',
    ],
}
