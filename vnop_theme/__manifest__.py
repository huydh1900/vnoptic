# -*- coding: utf-8 -*-
{
    "name": "vnop_theme",
    "version": "18.0.1.0.0",
    "category": "Theme",
    "summary": "Custom login interface for VNOPTIC",
    "depends": ["web", "auth_signup"],
    "data": [
        "views/login_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "vnop_theme/static/src/scss/login.scss",
            "vnop_theme/static/src/js/password_toggle.js",
        ],
        "web.assets_backend": [
            "vnop_theme/static/src/scss/view_backend.scss",
        ],
    },

    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
