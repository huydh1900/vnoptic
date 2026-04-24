# -*- coding: utf-8 -*-
{
    'name': 'VNOptic Sale Channel',
    'summary': 'Phân kênh bán buôn / bán lẻ cho khách hàng, bảng giá và đơn hàng',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'depends': [
        'base',
        'mail',
        'product',
        'account',
        'sale',
        'sale_management',
    ],
    'data': [
        'data/pricelist_data.xml',
        'data/menu_data.xml',
        'views/res_partner_views.xml',
        'views/product_pricelist_views.xml',
        'views/sale_order_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
