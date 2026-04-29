"""Auto-run khi -u vnop_sync lên version 18.0.1.1.0.

Convert sản phẩm type='consu':
- categ_id -> product.product_category_all
- classification_id -> classification mặc định theo category_type cũ

Logic chung đặt ở vnop_sync/scripts/migrate_consu_classification.py
để có thể chạy lại thủ công qua odoo-bin shell nếu cần.
"""

import importlib.util
import logging
import os

_logger = logging.getLogger(__name__)


def _load_migration_module():
    here = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.normpath(
        os.path.join(here, '..', '..', 'scripts', 'migrate_consu_classification.py')
    )
    spec = importlib.util.spec_from_file_location(
        'vnop_sync_migrate_consu_classification', script_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migrate(cr, version):
    """Hook upgrade — Odoo gọi tự động với (cr, version_cu)."""
    if not version:
        # Lần đầu install, không cần migrate (post_init_hook lo).
        return

    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Đảm bảo field classification_id đã tồn tại sau khi -u load model.
    if 'classification_id' not in env['product.template']._fields:
        _logger.warning(
            "vnop_sync migrate 18.0.1.1.0: bỏ qua, field classification_id chưa được khai báo."
        )
        return

    mod = _load_migration_module()
    counters = mod.migrate(env)
    _logger.info("vnop_sync migrate 18.0.1.1.0 hoàn tất: %s", counters)
