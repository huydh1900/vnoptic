# -*- coding: utf-8 -*-
{
    'name': "vnop_purchase",
    'depends': ['purchase', 'stock_landed_costs', 'vnop_delivery', 'vnop_contract'],
    'pre_init_hook': 'pre_init_hook',
    'data': [
        'data/landed_cost_products.xml',
        'data/menu_hide.xml',
        'views/purchase_order_views.xml',
        'views/purchase_product_menus.xml',
        'views/res_partner_views.xml',
    ],
}
