# -*- coding: utf-8 -*-
{
    'name': 'VNOptic Claim Back',
    'summary': 'Saleout reporting + tự động cấn trừ công nợ đại lý qua HĐ giảm trừ',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'depends': ['base', 'mail', 'sale', 'account', 'vnop_sale_channel'],
    'external_dependencies': {
        'python': ['openpyxl'],
    },
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/ir_sequence.xml',
        'data/ir_config_parameter.xml',
        'views/vnop_claim_back_views.xml',
        'views/dealer_tier_views.xml',
        'wizard/import_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
