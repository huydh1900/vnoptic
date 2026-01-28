from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DeliveryOTK(models.Model):
    _name = 'delivery.otk'
    _description = 'Lần OTK'
    _order = 'id desc'

    schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Lịch giao hàng',
        required=True,
        ondelete='cascade'
    )

    picking_id = fields.Many2one(
        'stock.picking',
        string='Phiếu nhập kho',
        readonly=True
    )

    total_qty_order = fields.Integer(
        string='Số lượng đặt hàng',
        compute='_compute_totals',
        store=True
    )
    total_qty_actual = fields.Integer(
        string='Tổng SL thực tế',
        compute='_compute_totals',
        store=True
    )
    total_qty_ok = fields.Integer(
        string='SL đạt',
        compute='_compute_totals',
        store=True
    )
    total_qty_ng = fields.Integer(
        string='SL không đạt',
        compute='_compute_totals',
        store=True
    )
    total_qty_over = fields.Integer(
        string='SL thừa',
        compute='_compute_totals',
        store=True
    )
    total_qty_lack = fields.Integer(
        string='SL thiếu',
        compute='_compute_totals',
        store=True
    )

    @api.depends(
        'line_ids.qty_order',
        'line_ids.qty_actual',
        'line_ids.qty_ok',
        'line_ids.qty_ng',
    )
    def _compute_totals(self):
        for rec in self:
            rec.total_qty_order = sum(rec.line_ids.mapped('qty_order'))
            rec.total_qty_actual = sum(rec.line_ids.mapped('qty_actual'))
            rec.total_qty_ok = sum(rec.line_ids.mapped('qty_ok'))
            rec.total_qty_ng = sum(rec.line_ids.mapped('qty_ng'))

            rec.total_qty_over = max(
                rec.total_qty_actual - rec.total_qty_order, 0
            )
            rec.total_qty_lack = max(
                rec.total_qty_order - rec.total_qty_actual, 0
            )

class DeliveryOTKLine(models.Model):
    _name = 'delivery.otk.line'
    _description = 'Chi tiết OTK'

    otk_id = fields.Many2one(
        'delivery.otk',
        string='OTK',
        required=True,
        ondelete='cascade'
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
        readonly=True
    )

    group_id = fields.Many2one(
        related='product_id.categ_id',
        string='Nhóm',
        store=True
    )

    sph = fields.Char(string='SPH')
    cyl = fields.Char(string='CYL')
    add = fields.Char(string='ADD')

    qty_order = fields.Integer(string='Số lượng đặt', required=True)
    qty_actual = fields.Integer(string='SL thực tế', required=True)

    qty_ok = fields.Integer(string='Đạt')
    qty_ng = fields.Integer(string='Không đạt')

    note = fields.Char(string='Ghi chú')

    state = fields.Selection(
        [
            ('ok', 'Đạt'),
            ('ng', 'Không đạt'),
        ],
        compute='_compute_state',
        store=True
    )

    @api.depends('qty_ok', 'qty_ng')
    def _compute_state(self):
        for line in self:
            if line.qty_ng > 0:
                line.state = 'ng'
            else:
                line.state = 'ok'

    @api.constrains('qty_actual', 'qty_ok', 'qty_ng')
    def _check_qty(self):
        for line in self:
            if line.qty_ok + line.qty_ng != line.qty_actual:
                raise ValidationError(
                    'SL Đạt + SL Không đạt phải bằng SL thực tế'
                )
