# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ProductImportHistory(models.Model):
    _name = 'product.import.history'
    _description = 'Lịch sử import / cập nhật sản phẩm'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    date = fields.Datetime(
        string='Thời điểm',
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )
    user_id = fields.Many2one(
        'res.users', string='Người thực hiện',
        default=lambda self: self.env.user, readonly=True,
    )
    mode = fields.Selection([
        ('create', 'Import sản phẩm mới'),
        ('update', 'Cập nhật sản phẩm'),
    ], string='Loại thao tác', required=True, readonly=True, index=True)
    file_format = fields.Selection([
        ('vn_label', 'Nhãn tiếng Việt'),
        ('technical', 'Technical'),
    ], string='Định dạng file', readonly=True)
    file_name = fields.Char(string='Tên file', readonly=True)
    file_data = fields.Binary(
        string='File đính kèm',
        attachment=True,
        readonly=True,
        help='File Excel đã được dùng cho lần import/cập nhật này. Tải về để đối chiếu.',
    )

    total_count = fields.Integer(string='Tổng số dòng', readonly=True)
    success_count = fields.Integer(string='Số sản phẩm thành công', readonly=True)
    lens_count = fields.Integer(string='Tròng', readonly=True)
    frame_count = fields.Integer(string='Gọng', readonly=True)
    accessory_count = fields.Integer(string='Phụ kiện', readonly=True)
    other_count = fields.Integer(string='Khác', readonly=True)

    error_text = fields.Text(string='Ghi chú / Lỗi', readonly=True)

    product_ids = fields.Many2many(
        'product.template',
        'product_import_history_product_rel',
        'history_id', 'product_tmpl_id',
        string='Sản phẩm',
        readonly=True,
    )
    product_count = fields.Integer(
        string='SL sản phẩm', compute='_compute_product_count', store=True,
    )

    display_name = fields.Char(
        string='Mô tả', compute='_compute_display_name', store=True,
    )

    @api.depends('product_ids')
    def _compute_product_count(self):
        for r in self:
            r.product_count = len(r.product_ids)

    @api.depends('mode', 'date', 'file_name')
    def _compute_display_name(self):
        labels = dict(self._fields['mode']._description_selection(self.env))
        for r in self:
            mode_lb = labels.get(r.mode, r.mode or '')
            date_str = fields.Datetime.context_timestamp(r, r.date).strftime('%Y-%m-%d %H:%M') if r.date else ''
            file_part = ' — %s' % r.file_name if r.file_name else ''
            r.display_name = '%s · %s%s' % (mode_lb, date_str, file_part)

    def action_view_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sản phẩm'),
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.product_ids.ids)],
            'context': {'create': False},
        }
