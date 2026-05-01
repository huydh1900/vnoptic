# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class QueueJob(models.Model):
    _inherit = 'queue.job'

    @api.model
    def cleanup_zombie_jobs(self, started_older_than_min=30, idle_min=5):
        """Reset job kẹt ở state='started' về 'pending' để runner pick lại.

        Heuristic phát hiện zombie (worker chết giữa chừng):
          - state = 'started'
          - date_started < now() - started_older_than_min
          - write_date < now() - idle_min  (job không có update gần đây)

        Không có cách thuần SQL kiểm tra "process worker tồn tại" — dùng
        write_date làm proxy: nếu worker còn sống, mỗi batch nó sẽ ghi
        progress/state, write_date sẽ refresh.
        """
        now = fields.Datetime.now()
        started_cutoff = now - timedelta(minutes=started_older_than_min)
        idle_cutoff = now - timedelta(minutes=idle_min)
        zombies = self.search([
            ('state', '=', 'started'),
            ('date_started', '<', started_cutoff),
            ('write_date', '<', idle_cutoff),
        ])
        if not zombies:
            return 0
        zombies.write({
            'state': 'pending',
            'date_started': False,
            'exc_info': False,
            'exc_message': 'Auto-reset zombie: worker treo > %s phút, runner sẽ retry.' % started_older_than_min,
        })
        _logger.warning(
            "queue_job cleanup: reset %s zombie job(s) ids=%s",
            len(zombies), zombies.ids,
        )
        return len(zombies)
