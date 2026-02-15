# -*- coding: utf-8 -*-
{
    'name': "vnoptic_contract",
    'depends': ['purchase_stock', 'mail'],

    'data': [
        'security/ir.model.access.csv',
        'data/contract_otk_sequence.xml',
        'views/contract_views.xml',
        'views/contract_line_views.xml',
        'views/contract_otk_views.xml',
        'views/res_config_settings_views.xml',
        'views/stock_views.xml',
    ],


    'assets': {
        'web.assets_backend': [
            'vnop_contract/static/src/scss/contract_required.scss',
        ],
    },
}
