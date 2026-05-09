# -*- coding: utf-8 -*-
"""Drop cột industry_id sau khi gỡ field 'Ngành hàng' khỏi sale.order."""


def migrate(cr, version):
    cr.execute("ALTER TABLE sale_order DROP COLUMN IF EXISTS industry_id")
