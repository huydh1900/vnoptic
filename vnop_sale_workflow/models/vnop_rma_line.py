# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class VnopRmaLine(models.Model):
    _name = 'vnop.rma.line'
    _description = 'Dòng yêu cầu trả hàng'

    rma_id = fields.Many2one(
        comodel_name='vnop.rma',
        string='RMA',
        required=True,
        ondelete='cascade',
    )
    sale_line_id = fields.Many2one(
        comodel_name='sale.order.line',
        string='Dòng đơn hàng gốc',
        required=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Sản phẩm',
        related='sale_line_id.product_id',
        store=True,
    )
    qty_returned = fields.Float(
        string='Số lượng trả',
        required=True,
        default=1.0,
    )
    qty_received = fields.Float(
        string='Số lượng đã nhận',
        default=0.0,
    )
    unit_price = fields.Float(
        string='Đơn giá',
        related='sale_line_id.price_unit',
        store=True,
        digits='Product Price',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Tiền tệ',
        related='rma_id.sale_order_id.currency_id',
        store=True,
    )
    reason_line = fields.Char(string='Ghi chú dòng')

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------
    @api.constrains('qty_received', 'qty_returned')
    def _check_qty_received(self):
        for line in self:
            if line.qty_received > line.qty_returned:
                raise ValidationError(
                    _('Sản phẩm "%s": số lượng đã nhận (%s) không được vượt quá số lượng trả (%s).')
                    % (line.product_id.display_name, line.qty_received, line.qty_returned)
                )
