# -*- coding: utf-8 -*-
{
    'name': "vnop_delivery",
    'depends': ['purchase', 'stock', 'stock_landed_costs', 'vnop_contract', 'vnop_purchase_offer', 'vnop_stock'],

    'data': [
        'security/ir.model.access.csv',
        'data/stock_otk_sequence.xml',
        'views/contract_views.xml',
        'views/delivery_schedule_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_otk_log_views.xml',
        'wizard/stock_otk_wizard_views.xml',
    ],
}
