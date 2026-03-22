# -*- coding: utf-8 -*-
"""
Migration 18.0.1.0.1
Mục đích: Bỏ NOT NULL constraint của cột `diameter` trong bảng `product_lens`
          vì dữ liệu sync từ API có thể không chứa giá trị diameter.
"""
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT is_nullable
        FROM information_schema.columns
        WHERE table_name = 'product_lens' AND column_name = 'diameter'
    """)
    row = cr.fetchone()
    if row and row[0] == 'NO':
        _logger.info("Migration: Dropping NOT NULL constraint on product_lens.diameter")
        cr.execute("ALTER TABLE product_lens ALTER COLUMN diameter DROP NOT NULL;")
        _logger.info("Migration: Done.")
    else:
        _logger.info("Migration: product_lens.diameter already nullable, skipping.")
