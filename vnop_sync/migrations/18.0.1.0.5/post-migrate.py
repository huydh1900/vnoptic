# -*- coding: utf-8 -*-
"""Dọn cron custom cũ sau khi chuyển sang queue_job.

Trước đây vnop_sync tạo `ir.cron` (xml id: ir_cron_process_sync_queue) gọi
`model._cron_process_pending_sync()`. Method này đã bị xoá khi refactor sang
queue_job, nhưng record cron cũ vẫn tồn tại trong DB vì XML data dùng
`noupdate="1"` — xoá file XML không tự gỡ record.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # 1) Unlink cron custom cũ (đã thay bằng queue_job)
    cron = env.ref(
        'vnop_sync.ir_cron_process_sync_queue', raise_if_not_found=False
    )
    if cron:
        cron.sudo().unlink()

    # 2) Reset các record product.sync đang kẹt ở 'queued'/'in_progress' do
    # cron custom cũ fail. Nếu không reset, nút sync mới sẽ bị chặn bởi
    # điều kiện "đã có job đang chạy" trong _enqueue_sync_job.
    stuck = env['product.sync'].search([
        ('sync_status', 'in', ('queued', 'in_progress')),
    ])
    if stuck:
        stuck.write({
            'sync_status': 'never',
            'sync_log': 'Đã reset trạng thái khi migrate sang queue_job. '
                        'Vui lòng bấm nút đồng bộ lại.',
        })
