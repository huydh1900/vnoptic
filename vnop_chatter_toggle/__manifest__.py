# -*- coding: utf-8 -*-
{
    "name": "VNOP Chatter Toggle",
    "summary": "Collapse/expand form chatter to save space",
    "version": "18.0.1.0.0",
    "category": "Hidden",
    "author": "VNOPTIC",
    "license": "LGPL-3",
    "depends": ["web", "mail"],
    "assets": {
        "web.assets_backend": [
            "vnop_chatter_toggle/static/src/js/chatter_toggle.esm.js",
            "vnop_chatter_toggle/static/src/scss/chatter_toggle.scss",
        ],
    },
    "installable": True,
    "application": False,
}
