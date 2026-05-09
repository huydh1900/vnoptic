# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Khi đại lý đặt hàng cắt theo đơn (RX), bán buôn nhập tay Rx ở SO line.
    rx_od_sph = fields.Float(string='OD - SPH', digits=(4, 2))
    rx_od_cyl = fields.Float(string='OD - CYL', digits=(4, 2))
    rx_od_axis = fields.Integer(string='OD - AXIS')
    rx_od_add = fields.Float(string='OD - ADD', digits=(3, 2))

    rx_os_sph = fields.Float(string='OS - SPH', digits=(4, 2))
    rx_os_cyl = fields.Float(string='OS - CYL', digits=(4, 2))
    rx_os_axis = fields.Integer(string='OS - AXIS')
    rx_os_add = fields.Float(string='OS - ADD', digits=(3, 2))

    rx_pd = fields.Float(string='PD (mm)', digits=(4, 1))
    rx_note = fields.Char(string='Ghi chú đơn kính')
    rx_has_data = fields.Boolean(
        string='Có Rx',
        compute='_compute_rx_has_data',
        store=True,
    )

    @api.depends(
        'rx_od_sph', 'rx_od_cyl', 'rx_od_axis', 'rx_od_add',
        'rx_os_sph', 'rx_os_cyl', 'rx_os_axis', 'rx_os_add',
        'rx_pd', 'rx_note',
    )
    def _compute_rx_has_data(self):
        for line in self:
            line.rx_has_data = any((
                line.rx_od_sph, line.rx_od_cyl, line.rx_od_axis, line.rx_od_add,
                line.rx_os_sph, line.rx_os_cyl, line.rx_os_axis, line.rx_os_add,
                line.rx_pd, line.rx_note,
            ))

    qty_available_display = fields.Float(
        string='Tồn kho',
        compute='_compute_stock_status',
        digits='Product Unit of Measure',
        help='Số lượng tồn kho hiện tại của sản phẩm (theo công ty của đơn hàng).',
    )
    is_stock_insufficient = fields.Boolean(
        string='Thiếu tồn',
        compute='_compute_stock_status',
        help='Đánh dấu line có sản phẩm storable mà tồn kho hiện tại < số lượng đặt.',
    )

    @api.depends('product_id', 'product_uom_qty', 'order_id.company_id')
    def _compute_stock_status(self):
        # Batch fetch qty_available cho toàn bộ product.product trong recordset
        # để tránh N+1 query khi danh sách dòng dài.
        consu_lines = self.filtered(
            lambda line: line.product_id and line.product_id.type == 'consu'
        )
        (self - consu_lines).qty_available_display = 0.0
        (self - consu_lines).is_stock_insufficient = False
        if not consu_lines:
            return
        consu_lines.product_id.fetch(['qty_available'])
        for line in consu_lines:
            available = line.product_id.qty_available
            line.qty_available_display = available
            line.is_stock_insufficient = (
                line.product_uom_qty > 0 and available < line.product_uom_qty
            )
