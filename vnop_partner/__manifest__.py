# -*- coding: utf-8 -*-
{
    'name': "vnop_partner",
    'version': '18.0.1.0.2',
    'depends': ['base', 'portal'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/disable_server_actions.xml',
        'views/res_partner_views.xml',
        'views/res_country_state_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
}
