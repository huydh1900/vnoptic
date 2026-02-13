# -*- coding: utf-8 -*-
{
    'name': "vnoptic_contract",
    'depends': ['purchase_stock', 'stock_picking_batch'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/contract_views.xml',
        'views/contract_line_views.xml',
        'views/stock_views.xml',
    ],
}
