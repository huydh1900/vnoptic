# -*- coding: utf-8 -*-
{
    'name': "vnop_purchase",
    'depends': ['purchase', 'vnop_delivery'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/purchase_order_views.xml',
        'views/import_contract_views.xml',
        'views/import_contract_wizard_views.xml',
    ],
}
