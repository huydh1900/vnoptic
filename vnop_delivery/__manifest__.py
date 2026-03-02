# -*- coding: utf-8 -*-
{
    'name': "vnop_delivery",
    'depends': ['purchase', 'stock', 'vnop_contract'],

    # always loaded
    'data': [
        'data/delivery_otk_sequence.xml',
        'security/ir.model.access.csv',
        'views/contract_arrival_views.xml',
        'views/delivery_schedule_views.xml',
        'views/delivery_otk_views.xml',
    ],
}
