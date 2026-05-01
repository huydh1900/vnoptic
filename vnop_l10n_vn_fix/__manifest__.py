# -*- coding: utf-8 -*-
{
    'name': "vnop_l10n_vn_fix",
    'summary': "Fix l10n_vn WIP account template + auto-load Chart of Accounts VN",
    'depends': ['l10n_vn'],
    'data': [],
    'post_init_hook': 'post_init_load_vn_chart',
    'installable': True,
    'auto_install': False,
}
