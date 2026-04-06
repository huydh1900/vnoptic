# -*- coding: utf-8 -*-
{
    'name': "vnoptic_contract",
    'depends': ['purchase_stock', 'stock', 'mail', 'attachment_preview'],

    'data': [
        'data/cleanup_legacy_data.xml',
        'data/contract_document_type_data.xml',
        'security/ir.model.access.csv',
        'views/contract_views.xml',
        'views/contract_line_views.xml',
        'views/stock_views.xml',
        'views/stock_quant_views.xml',
    ],


    'assets': {
        'web.assets_backend': [
            'vnop_contract/static/src/scss/contract_required.scss',
        ],
    },
}
