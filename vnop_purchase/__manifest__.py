# -*- coding: utf-8 -*-
{
    'name': "vnop_purchase",
    'depends': ['purchase', 'stock_landed_costs', 'vnop_delivery', 'vnop_contract'],
    'data': [
        'security/ir.model.access.csv',
        'data/landed_cost_products.xml',
        'views/purchase_order_views.xml',
        'views/purchase_product_menus.xml',
    ],
}
