# -*- coding: utf-8 -*-
{
    'name': "vnop_stock",
    'summary': "VNOptic stock master data (warehouse locations)",
    'depends': ['stock', 'vnop_sync'],
    'data': [
        'data/stock_location_data.xml',
        'views/stock_lens_matrix_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'vnop_stock/static/src/lens_stock_matrix/lens_stock_matrix.js',
            'vnop_stock/static/src/lens_stock_matrix/lens_stock_matrix.xml',
            'vnop_stock/static/src/lens_stock_matrix/lens_stock_matrix.scss',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}