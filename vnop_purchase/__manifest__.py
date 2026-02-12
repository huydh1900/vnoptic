# -*- coding: utf-8 -*-
{
    'name': "vnop_purchase",
    'depends': ['purchase', 'vnop_delivery', 'vnop_contract'],
    'data': [
        'security/ir.model.access.csv',
        'views/purchase_order_views.xml',
    ],
}
