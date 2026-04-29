"""Migration: chuyển sản phẩm type='consu' về danh mục root 'All' và gán
classification_id tương ứng với product.classification.category_type.

Chạy qua Odoo shell:
    cd /home/huytq/vnoptic
    odoo18/odoo-bin shell -c conf/vnoptic.conf -d vnoptic82 \
        --addons-path=/home/huytq/vnoptic/vnoptic,/home/huytq/vnoptic/odoo18/addons,/home/huytq/vnoptic/enterprise

Trong shell:
    >>> exec(open('/home/huytq/vnoptic/vnoptic/vnop_sync/scripts/migrate_consu_classification.py').read())
    >>> migrate(env)
    >>> env.cr.commit()

Hoặc chạy thẳng (không tương tác):
    odoo18/odoo-bin shell -c conf/vnoptic.conf -d vnoptic82 \
        --addons-path=... \
        < vnoptic/vnop_sync/scripts/migrate_consu_classification.py
"""

import logging

_logger = logging.getLogger(__name__)


# Map từ legacy categ_code (ProductCategory.code) -> category_type của product.classification.
CATEG_CODE_TO_TYPE = {
    'TK': 'lens',
    'GK': 'frame',
    'PK': 'accessory',
    'TB': 'accessory',
    'LK': 'accessory',
}


def _resolve_legacy_categ_code(template):
    """Tìm code danh mục gốc bằng cách walk-up cây danh mục cũ."""
    categ = template.categ_id
    while categ:
        code = (getattr(categ, 'code', '') or '').strip().upper()
        if code:
            return code
        categ = categ.parent_id
    return ''


def _build_classification_cache(env):
    """Lấy classification đầu tiên (theo code) cho mỗi category_type."""
    Classification = env['product.classification']
    cache = {}
    for ctype in ('frame', 'lens', 'accessory', 'other'):
        rec = Classification.search(
            [('category_type', '=', ctype)],
            order='code',
            limit=1,
        )
        cache[ctype] = rec.id if rec else False
    return cache


def migrate(env, dry_run=False, batch_size=500):
    """Convert tất cả sản phẩm type='consu':
       - categ_id -> product.product_category_all
       - classification_id -> classification mặc định theo category_type
    """
    all_categ = env.ref('product.product_category_all', raise_if_not_found=False)
    if not all_categ:
        raise RuntimeError("Không tìm thấy product.product_category_all (root 'All').")

    classif_cache = _build_classification_cache(env)
    missing_types = [t for t, cid in classif_cache.items() if not cid]
    if missing_types:
        _logger.warning(
            "Không có product.classification cho category_type=%s. "
            "Sản phẩm thuộc các nhóm này sẽ KHÔNG được gán classification.",
            missing_types,
        )

    Template = env['product.template']
    products = Template.with_context(active_test=False).search([
        ('type', '=', 'consu'),
    ])
    total = len(products)
    _logger.info("Bắt đầu migrate %d sản phẩm consu.", total)

    counters = {'frame': 0, 'lens': 0, 'accessory': 0, 'other': 0, 'skipped': 0}

    for offset in range(0, total, batch_size):
        batch = products[offset:offset + batch_size]
        for tmpl in batch:
            legacy_code = _resolve_legacy_categ_code(tmpl)
            ctype = CATEG_CODE_TO_TYPE.get(legacy_code, 'other')
            classif_id = classif_cache.get(ctype)

            vals = {'categ_id': all_categ.id}
            if classif_id:
                vals['classification_id'] = classif_id
                counters[ctype] += 1
            else:
                counters['skipped'] += 1

            if not dry_run:
                tmpl.write(vals)

        if not dry_run:
            env.cr.commit()
        _logger.info("Đã xử lý %d/%d sản phẩm.", min(offset + batch_size, total), total)

    _logger.info(
        "Hoàn tất. Frame=%(frame)d Lens=%(lens)d Accessory=%(accessory)d "
        "Other=%(other)d Skipped(no classif)=%(skipped)d",
        counters,
    )
    return counters


# Khi chạy trực tiếp qua `odoo-bin shell < scripts/...py` thì biến `env` có
# sẵn trong global scope của shell.
_env = globals().get('env')
if _env is not None:
    migrate(_env)
    _env.cr.commit()
