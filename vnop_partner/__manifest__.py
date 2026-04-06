# -*- coding: utf-8 -*-
{
    'name': "vnop_partner",
    'version': '18.0.1.0.1',
    'depends': ['base', 'portal'],

    # always loaded
    'data': [
        'data/disable_server_actions.xml',
        'views/res_partner_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
}

