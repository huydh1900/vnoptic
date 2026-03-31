# -*- coding: utf-8 -*-
{
    'name': 'VNOP Currency Rate',
    'version': '1.0',
    'summary': 'Tự động cập nhật tỷ giá từ API (Vietcombank / SBV)',
    'depends': ['base', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'data/default_provider_data.xml',
        'views/currency_rate_provider_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
