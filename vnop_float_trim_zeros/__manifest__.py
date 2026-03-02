# -*- coding: utf-8 -*-
{
    "name": "VNOptic Float Trim Zeros",
    "summary": "Hide trailing ,00 for float values that are natural numbers",
    "version": "18.0.1.0.0",
    "category": "Hidden",
    "author": "VNOptic",
    "license": "LGPL-3",
    "depends": ["web"],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "vnop_float_trim_zeros/static/src/js/float_formatter_patch.esm.js",
        ],
    },
    "installable": True,
    "application": False,
}

