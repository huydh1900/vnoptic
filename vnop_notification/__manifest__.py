# -*- coding: utf-8 -*-
{
    "name": "VNOP Save Notification",
    "summary": "Hiển thị thông báo khi lưu bản ghi thành công",
    "version": "18.0.1.0.0",
    "category": "Hidden",
    "author": "VNOPTIC",
    "license": "LGPL-3",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "vnop_notification/static/src/js/save_notification.esm.js",
        ],
    },
    "installable": True,
    "application": False,
}
