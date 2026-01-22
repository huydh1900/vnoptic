# -*- coding: utf-8 -*-
{
    'name': "vnop_sale",
    # any module necessary for this one to work correctly
    'depends': ['base', 'product', 'sale', 'xnk_intergration', 'stock'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        'views/product_views.xml',
    ],
}

