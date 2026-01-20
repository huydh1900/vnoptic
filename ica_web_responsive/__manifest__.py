# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'ICA Web Responsive',
    'author':"Agga, IdeaCode Academy",
    'version': '18.0.1.0',
    'depends': ['web', 'base_setup'],
    # 'auto_install': ['web'],
    'auto_install': False,
    'data': [
        'views/webclient_templates.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('after', 'web/static/src/scss/primary_variables.scss', 'ica_web_responsive/static/src/**/*.variables.scss'),
            ('before', 'web/static/src/scss/primary_variables.scss', 'ica_web_responsive/static/src/scss/primary_variables.scss'),
        ],
        'web._assets_secondary_variables': [
            ('before', 'web/static/src/scss/secondary_variables.scss', 'ica_web_responsive/static/src/scss/secondary_variables.scss'),
        ],
        'web._assets_backend_helpers': [
            ('before', 'web/static/src/scss/bootstrap_overridden.scss', 'ica_web_responsive/static/src/scss/bootstrap_overridden.scss'),
        ],
        'web.assets_frontend': [
            'ica_web_responsive/static/src/webclient/home_menu/home_menu_background.scss', # used by login page
            'ica_web_responsive/static/src/webclient/navbar/navbar.scss',
        ],
        'web.assets_backend': [
            'ica_web_responsive/static/src/webclient/**/*.scss',
            'ica_web_responsive/static/src/views/**/*.scss',

            'ica_web_responsive/static/src/core/**/*',
            'ica_web_responsive/static/src/webclient/**/*.js',
            ('after', 'web/static/src/views/list/list_renderer.xml', 'ica_web_responsive/static/src/views/list/list_renderer_desktop.xml'),
            'ica_web_responsive/static/src/webclient/**/*.xml',
            'ica_web_responsive/static/src/views/**/*.js',
            'ica_web_responsive/static/src/views/**/*.xml',
            ('remove', 'ica_web_responsive/static/src/views/pivot/**'),

            # Don't include dark mode files in light mode
            ('remove', 'ica_web_responsive/static/src/**/*.dark.scss'),
        ],
        'web.assets_backend_lazy': [
            'ica_web_responsive/static/src/views/pivot/**',
        ],
        'web.assets_backend_lazy_dark': [
            ('include', 'web.dark_mode_variables'),
            # web._assets_backend_helpers
            ('before', 'ica_web_responsive/static/src/scss/bootstrap_overridden.scss', 'ica_web_responsive/static/src/scss/bootstrap_overridden.dark.scss'),
            ('after', 'web/static/lib/bootstrap/scss/_functions.scss', 'ica_web_responsive/static/src/scss/bs_functions_overridden.dark.scss'),
        ],
        'web.assets_web': [
            ('replace', 'web/static/src/main.js', 'ica_web_responsive/static/src/main.js'),
        ],
        # ========= Dark Mode =========
        "web.dark_mode_variables": [
            # web._assets_primary_variables
            ('before', 'ica_web_responsive/static/src/scss/primary_variables.scss', 'ica_web_responsive/static/src/scss/primary_variables.dark.scss'),
            ('before', 'ica_web_responsive/static/src/**/*.variables.scss', 'ica_web_responsive/static/src/**/*.variables.dark.scss'),
            # web._assets_secondary_variables
            ('before', 'ica_web_responsive/static/src/scss/secondary_variables.scss', 'ica_web_responsive/static/src/scss/secondary_variables.dark.scss'),
        ],
        "web.assets_web_dark": [
            ('include', 'web.dark_mode_variables'),
            # web._assets_backend_helpers
            ('before', 'ica_web_responsive/static/src/scss/bootstrap_overridden.scss', 'ica_web_responsive/static/src/scss/bootstrap_overridden.dark.scss'),
            ('after', 'web/static/lib/bootstrap/scss/_functions.scss', 'ica_web_responsive/static/src/scss/bs_functions_overridden.dark.scss'),
            # assets_backend
            'ica_web_responsive/static/src/**/*.dark.scss',
        ],
    },
    'license': 'LGPL-3',

    "images":["static/description/img.png"],
}
