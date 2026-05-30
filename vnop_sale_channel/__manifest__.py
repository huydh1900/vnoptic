# -*- coding: utf-8 -*-
{
    'name': 'VNOptic Sale Channel',
    'summary': 'Hạ tầng B2B đại lý: dealer tier, hạn mức công nợ, đặt cọc',
    'version': '18.0.3.1.0',
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
        'vnop_partner',
        'vnop_product_portal',
        'attachment_preview',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_tax_data.xml',
        'data/dealer_tier_data.xml',
        'data/pricelist_data.xml',
        'data/menu_data.xml',
        'views/dealer_tier_views.xml',
        'views/res_partner_views.xml',
        'views/product_pricelist_views.xml',
        'views/sale_order_views.xml',
        'wizard/sale_order_line_import_wizard_views.xml',
        'wizard/sale_intem_preview_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'vnop_sale_channel/static/src/scss/intem_preview.scss',
        ],
    },
    'external_dependencies': {
        'python': ['num2words'],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
