# -*- coding: utf-8 -*-
import calendar

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class VnopSaleTarget(models.Model):
    _name = 'vnop.sale.target'
    _inherit = ['mail.thread']
    _description = 'Mục tiêu doanh số'
    _order = 'date_from desc, user_id'

    name = fields.Char(
        string='Tên',
        compute='_compute_name',
        store=True,
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Nhân viên',
        required=True,
        domain=[('share', '=', False)],
        tracking=True,
    )
    period_type = fields.Selection(
        selection=[
            ('month', 'Tháng'),
            ('quarter', 'Quý'),
            ('year', 'Năm'),
        ],
        string='Loại kỳ',
        required=True,
        default='month',
        tracking=True,
    )
    period_ref_date = fields.Date(
        string='Ngày tham chiếu kỳ',
        required=True,
        default=fields.Date.today,
        help='Ngày trong kỳ dùng để tính ngày bắt đầu và kết thúc.',
    )
    date_from = fields.Date(
        string='Từ ngày',
        compute='_compute_period_dates',
        store=True,
    )
    date_to = fields.Date(
        string='Đến ngày',
        compute='_compute_period_dates',
        store=True,
    )
    target_amount = fields.Monetary(
        string='Mục tiêu doanh số',
        required=True,
        tracking=True,
    )
    actual_amount = fields.Monetary(
        string='Doanh số thực tế',
        compute='_compute_actual_amount',
        store=True,
    )
    achievement_pct = fields.Float(
        string='Tỉ lệ đạt (%)',
        compute='_compute_achievement_pct',
        digits=(5, 2),
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Tiền tệ',
        related='company_id.currency_id',
        store=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Công ty',
        required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            'uniq_user_period',
            'unique(user_id, period_type, date_from, company_id)',
            'Đã tồn tại mục tiêu cho nhân viên và kỳ này.',
        ),
    ]

    # -------------------------------------------------------------------------
    # Compute
    # -------------------------------------------------------------------------
    @api.depends('user_id', 'period_type', 'period_ref_date')
    def _compute_name(self):
        period_label = {
            'month': 'Tháng',
            'quarter': 'Quý',
            'year': 'Năm',
        }
        for target in self:
            ref = target.period_ref_date
            if not ref or not target.user_id:
                target.name = _('Mục tiêu mới')
                continue
            label = period_label.get(target.period_type, '')
            if target.period_type == 'month':
                period_str = '%s %02d/%d' % (label, ref.month, ref.year)
            elif target.period_type == 'quarter':
                quarter = (ref.month - 1) // 3 + 1
                period_str = '%s %d/%d' % (label, quarter, ref.year)
            else:
                period_str = '%s %d' % (label, ref.year)
            target.name = '%s - %s' % (target.user_id.name, period_str)

    @api.depends('period_ref_date', 'period_type')
    def _compute_period_dates(self):
        for target in self:
            ref = target.period_ref_date
            if not ref:
                target.date_from = False
                target.date_to = False
                continue

            if target.period_type == 'month':
                target.date_from = ref.replace(day=1)
                last_day = calendar.monthrange(ref.year, ref.month)[1]
                target.date_to = ref.replace(day=last_day)

            elif target.period_type == 'quarter':
                quarter_start_month = ((ref.month - 1) // 3) * 3 + 1
                target.date_from = ref.replace(month=quarter_start_month, day=1)
                quarter_end_month = quarter_start_month + 2
                last_day = calendar.monthrange(ref.year, quarter_end_month)[1]
                target.date_to = ref.replace(month=quarter_end_month, day=last_day)

            else:  # year
                target.date_from = ref.replace(month=1, day=1)
                target.date_to = ref.replace(month=12, day=31)

    @api.depends('user_id', 'date_from', 'date_to', 'company_id')
    def _compute_actual_amount(self):
        for target in self:
            if not target.user_id or not target.date_from or not target.date_to:
                target.actual_amount = 0.0
                continue

            orders = self.env['sale.order'].search([
                ('user_id', '=', target.user_id.id),
                ('state', 'in', ('sale', 'done')),
                ('date_order', '>=', fields.Datetime.from_string(
                    str(target.date_from) + ' 00:00:00'
                )),
                ('date_order', '<=', fields.Datetime.from_string(
                    str(target.date_to) + ' 23:59:59'
                )),
                ('company_id', '=', target.company_id.id),
            ])
            target.actual_amount = sum(orders.mapped('amount_total'))

    def _compute_achievement_pct(self):
        for target in self:
            if target.target_amount:
                target.achievement_pct = (target.actual_amount / target.target_amount) * 100.0
            else:
                target.achievement_pct = 0.0

    # -------------------------------------------------------------------------
    # Cron
    # -------------------------------------------------------------------------
    def _cron_update_actuals(self):
        """Cron job: invalidate và recompute actual_amount cho tất cả mục tiêu."""
        targets = self.search([])
        targets.invalidate_recordset(['actual_amount'])
        targets._compute_actual_amount()
