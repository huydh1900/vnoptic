# -*- coding: utf-8 -*-
"""Post-init hook: tự động cài Sơ đồ tài khoản (Chart of Accounts) Việt Nam.

Lý do: trong Odoo 18, module `l10n_vn` chỉ định nghĩa template (Python
`@template('vn')`); chart không tự áp dụng cho company nào — phải bấm tay
ở Settings → Accounting → Chart Template, hoặc gọi `try_loading('vn', company)`.

Nếu chưa load chart, mở POS sẽ báo:
    'Không có sơ đồ tài khoản nào được cấu hình...'

Hook này chạy 1 lần khi cài module trên company mặc định nếu company đó
chưa có chart_template, tránh conflict với company đã cấu hình thủ công.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_load_vn_chart(env):
    """Load chart 'vn' cho company mặc định nếu chưa có chart_template."""
    company = env.company or env['res.company'].search([], limit=1)
    if not company:
        _logger.info("vnop_l10n_vn_fix: không tìm thấy company, bỏ qua load chart.")
        return

    if company.chart_template:
        _logger.info(
            "vnop_l10n_vn_fix: company %s đã có chart_template=%s, bỏ qua.",
            company.name, company.chart_template,
        )
        return

    try:
        env['account.chart.template'].try_loading('vn', company=company, install_demo=False)
        _logger.info("vnop_l10n_vn_fix: đã load Sơ đồ tài khoản VN cho company %s.", company.name)
    except Exception as e:
        _logger.warning(
            "vnop_l10n_vn_fix: load chart 'vn' cho %s thất bại: %s. "
            "Vui lòng vào Settings → Accounting → Chart Template để cài thủ công.",
            company.name, e,
        )
