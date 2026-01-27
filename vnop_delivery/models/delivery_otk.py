from odoo import models, fields, api


class DeliveryOTK(models.Model):
    _name = 'delivery.otk'
    _description = 'Lần OTK'

    schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Lịch giao hàng',
        required=True,
        ondelete='cascade'
    )

    total_qty_order = fields.Integer(
        string='Tổng số lượng đặt',
        compute='_compute_totals', readonly=False,
        store=True
    )
    total_qty_actual = fields.Integer(
        string='Tổng số lượng thực tế',
        compute='_compute_totals', readonly=False,
        store=True
    )
    total_qty_ok = fields.Integer(
        string='Tổng số lượng đạt',
        compute='_compute_totals', readonly=False,
        store=True
    )
    total_qty_ng = fields.Integer(
        string='Tổng số lượng không đạt', readonly=False,
        compute='_compute_totals',
        store=True
    )
    total_qty_over = fields.Integer(
        string='Tổng số lượng thừa', readonly=False,
        compute='_compute_totals',
        store=True
    )
    total_qty_lack = fields.Integer(
        string='Tổng số lượng thiếu', readonly=False,
        compute='_compute_totals',
        store=True
    )

    line_ids = fields.One2many(
        'delivery.otk.line',
        'otk_id', readonly=False,
        string='Chi tiết OTK'
    )

    @api.depends(
        'line_ids.qty_order',
        'line_ids.qty_actual',
        'line_ids.qty_ok',
        'line_ids.qty_ng',
        'line_ids.qty_over',
        'line_ids.qty_lack',
    )
    def _compute_totals(self):
        for rec in self:
            rec.total_qty_order = sum(rec.line_ids.mapped('qty_order'))
            rec.total_qty_actual = sum(rec.line_ids.mapped('qty_actual'))
            rec.total_qty_ok = sum(rec.line_ids.mapped('qty_ok'))
            rec.total_qty_ng = sum(rec.line_ids.mapped('qty_ng'))
            rec.total_qty_over = sum(rec.line_ids.mapped('qty_over'))
            rec.total_qty_lack = sum(rec.line_ids.mapped('qty_lack'))


class DeliveryOTKLine(models.Model):
    _name = 'delivery.otk.line'
    _description = 'Chi tiết OTK'

    otk_id = fields.Many2one(
        'delivery.otk',
        string='OTK',
        ondelete='cascade',
        required=True
    )

    product_id = fields.Many2one(
        'product.product',
        string='Sản phẩm',
        required=True
    )

    product_code = fields.Char(
        related='product_id.default_code',
        string='Mã SP',
        store=True
    )

    image_1920 = fields.Image(
        related='product_id.image_1920',
        string='Hình ảnh'
    )

    group_id = fields.Many2one(
        'product.category',
        string='Nhóm'
    )

    sph = fields.Char(string='SPH')
    cyl = fields.Char(string='CYL')
    add = fields.Char(string='ADD')

    state = fields.Selection(
        [
            ('ok', 'Đạt'),
            ('ng', 'Không đạt'),
        ],
        string='Tình trạng'
    )

    qty_order = fields.Integer(string='Số lượng đặt')
    qty_actual = fields.Integer(string='SL thực tế')

    qty_ok = fields.Integer(string='Đạt')
    qty_ng = fields.Integer(string='Không đạt')
    qty_over = fields.Integer(string='Thừa')
    qty_lack = fields.Integer(string='Thiếu')

    note = fields.Char(string='Ghi chú')

    write_date = fields.Datetime(string='Thời gian cập nhật')
