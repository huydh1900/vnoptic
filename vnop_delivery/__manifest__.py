# -*- coding: utf-8 -*-
{
    'name': "vnop_delivery",
    'depends': ['purchase', 'stock'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/delivery_schedule_views.xml',
    ],
}

