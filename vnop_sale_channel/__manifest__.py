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
        'sale_pdf_quote_builder',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_tax_data.xml',
        'data/pricelist_data.xml',
        'data/menu_data.xml',
        'views/res_partner_views.xml',
        'views/product_pricelist_views.xml',
        'views/sale_order_views.xml',
        'wizard/sale_order_line_import_wizard_views.xml',
    ],
    'external_dependencies': {
        'python': ['num2words'],
    },
    'assets': {
        'web.assets_backend': [
            'vnop_sale_channel/static/src/js/sale_order_stock_warning.js',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
