# -*- coding: utf-8 -*-
{
    'name': "vnop_sale",
    # any module necessary for this one to work correctly
    'depends': ['base', 'product', 'sale', 'vnop_sync', 'stock'],

    # always loaded
    'data': [
        'security/groups.xml',
        'views/views.xml',
        'views/templates.xml',
        'views/product_views.xml',
    ],
}

