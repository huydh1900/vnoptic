# -*- coding: utf-8 -*-
"""Thay 63 tỉnh/thành VN cũ bằng 34 đơn vị hành chính sau sáp nhập.

Migration này chạy mỗi khi module được upgrade lên phiên bản 18.0.1.0.1.
Dùng chung logic với post_init_hook trong vnop_partner/hooks.py.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.vnop_partner.hooks import post_init_hook


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    post_init_hook(env)