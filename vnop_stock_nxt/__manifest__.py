# -*- coding: utf-8 -*-
{
    'name': 'VNOptic - Báo cáo Nhập Xuất Tồn (NXT)',
    'version': '18.0.2.0.0',
    'category': 'Inventory/Reporting',
    'summary': 'Báo cáo Nhập-Xuất-Tồn theo kỳ (SL & GT) — màn OWL lọc/preview/xuất Excel',
    'author': 'VNOptic',
    'depends': ['vnop_report', 'vnop_stock', 'stock_account', 'vnop_sync'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.model.access.csv',
        'data/stock_warehouse_data.xml',
        'wizard/stock_nxt_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'vnop_stock_nxt/static/src/nxt_report/nxt_report.js',
            'vnop_stock_nxt/static/src/nxt_report/nxt_report.xml',
            'vnop_stock_nxt/static/src/nxt_report/nxt_report.scss',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'test_tags': ['vnop_stock_nxt'],
}
