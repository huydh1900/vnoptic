# -*- coding: utf-8 -*-
{
    'name': "vnop_purchase",
    'depends': ['base', 'purchase', 'product', 'xnk_intergration', 'stock'],

    # always loaded
    'depends': ['base', 'purchase'],
    'data': [
        'views/views.xml',
        'views/templates.xml',
        'views/product_views.xml',
        'views/purchase_order_views.xml',
    ],
}

