# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class QueueJob(models.Model):
    _inherit = 'queue.job'

    def action_force_cancel(self):
        """Cho phép user cancel job từ UI cả khi state='started'.

        UI mặc định chỉ cho cancel job pending. Khi job đang `started` mà
        worker đã chết (zombie) hoặc user muốn dừng khẩn, dùng nút này.

        Lưu ý: chỉ thay state='cancelled' ở DB. Worker còn sống (nếu có) sẽ
        tự crash khi cố commit row đã cancel — đó là behavior mong muốn.
        Để dừng MỀM (khuyến nghị) khi worker còn sống → dùng
        product.sync.action_request_stop để worker tự thoát sạch.
        """
        for job in self:
            if job.state in ('done', 'cancelled', 'failed'):
                continue
            job.write({
                'state': 'cancelled',
                'date_done': fields.Datetime.now(),
                'exc_message': 'Cancelled by user (force).',
            })
        return True

    @api.model
    def cleanup_zombie_jobs(self, started_older_than_min=60):
        """Reset job kẹt ở state='started' về 'pending' để runner pick lại.

        Heuristic zombie (worker chết giữa chừng — vd OOM, service restart,
        cron timeout `limit_time_real_cron`):
          - state = 'started'
          - date_started < now() - started_older_than_min phút
          - không có PG backend nào đang giữ row lock job đó (kiểm tra qua
            pg_stat_activity / pg_locks: nếu không có process nào reference
            queue_job.id qua xact lock → worker đã chết)

        queue.job có `_log_access = False` nên KHÔNG có `write_date`. Dùng
        date_started + check pg backend là đủ tin cậy mà không nhầm với
        job đang chạy lâu nhưng còn sống.

        Tham số mặc định 60 phút: đủ buffer cho sync ảnh full (~30-50 phút).
        Nếu sync nhỏ hơn nhiều, có thể giảm; sync lâu hơn nhiều, tăng.
        """
        now = fields.Datetime.now()
        started_cutoff = now - timedelta(minutes=started_older_than_min)
        candidates = self.search([
            ('state', '=', 'started'),
            ('date_started', '<', started_cutoff),
        ])
        if not candidates:
            return 0

        # Lọc thêm: chỉ reset job mà KHÔNG có PG backend đang process queue_job
        # row đó. Heuristic: nếu có process Odoo nào idle in transaction lâu
        # tham chiếu queue_job lock, có thể worker còn sống → bỏ qua.
        # Đơn giản: query pg_stat_activity xem có connection 'odoo-*' nào ở
        # state 'idle in transaction' / 'active' với xact_start cũ hơn job
        # date_started → khả năng cao worker đó đang chạy job.
        cr = self.env.cr
        cr.execute("""
            SELECT count(*)::int
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND application_name LIKE 'odoo%%'
              AND state IN ('active', 'idle in transaction')
              AND xact_start IS NOT NULL
              AND xact_start <= %s
        """, (started_cutoff,))
        active_old_workers = cr.fetchone()[0] or 0

        # Nếu vẫn có worker còn xact_start < cutoff → có thể đang chạy job →
        # giữ lại candidate cũ nhất tránh kill nhầm. Phương án bảo thủ:
        # chỉ reset khi KHÔNG có process Odoo nào ở idle-in-tx cũ.
        if active_old_workers > 0:
            _logger.info(
                "queue_job cleanup: bỏ qua %s zombie candidates vì có %s worker còn xact_start cũ.",
                len(candidates), active_old_workers,
            )
            return 0

        candidates.write({
            'state': 'pending',
            'date_started': False,
            'exc_info': False,
            'exc_message': (
                'Auto-reset zombie: worker không còn hoạt động sau %s phút, '
                'runner sẽ retry.' % started_older_than_min
            ),
        })
        _logger.warning(
            "queue_job cleanup: reset %s zombie job(s) ids=%s",
            len(candidates), candidates.ids,
        )
        return len(candidates)
