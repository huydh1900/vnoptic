# -*- coding: utf-8 -*-
{
    'name': "vnop_delivery",
    'depends': ['purchase', 'stock', 'vnop_contract'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/delivery_schedule_views.xml',
        'views/stock_picking_views.xml',
        'wizard/otk_wizard.xml',
    ],
}

