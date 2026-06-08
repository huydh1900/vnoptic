# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class VnopReturnRequestLine(models.Model):
    _name = 'vnop.return.request.line'
    _description = 'Dòng sản phẩm trả'

    request_id = fields.Many2one('vnop.return.request', required=True,
                                 ondelete='cascade', string='Phiếu trả')
    sale_order_line_id = fields.Many2one(
        'sale.order.line', string='Dòng đơn hàng gốc',
        domain="[('order_id', '=', parent.sale_order_id)]")
    product_id = fields.Many2one('product.product', string='Sản phẩm',
                                 required=True)
    product_uom_id = fields.Many2one('uom.uom', string='Đơn vị',
                                     required=True)
    quantity = fields.Float(string='Số lượng', required=True, default=1.0,
                            digits='Product Unit of Measure')
    price_unit = fields.Monetary(
        string='Giá gốc', currency_field='currency_id',
        compute='_compute_price_unit', store=True, readonly=False,
        help='Giá lúc bán lấy từ dòng đơn hàng gốc; có thể chỉnh tay khi trả ngoại lệ.')
    subtotal = fields.Monetary(string='Thành tiền', compute='_compute_subtotal',
                               store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='request_id.currency_id', readonly=True)

    defect_group = fields.Many2one(
        'vnop.return.defect.group', string='Nhóm lỗi', required=True,
        ondelete='restrict',
        domain="[('return_type', '=', parent.return_type)]")
    reason_id = fields.Many2one(
        'vnop.return.reason', string='Lý do',
        domain="[('defect_group', '=', defect_group)]", required=True)

    # BH bán buôn
    warranty_days_remaining = fields.Integer(
        string='BH bán buôn còn lại (ngày)',
        compute='_compute_warranty_days', store=False)

    # OTK phân loại
    classify_destination = fields.Selection(
        [('commercial', 'Kho Thương mại (bán lại)'),
         ('liquidation', 'Kho Thanh lý')],
        string='Phân loại nhập kho')
    qc_note = fields.Text(string='Ghi chú OTK')

    @api.constrains('defect_group', 'request_id')
    def _check_defect_group_return_type(self):
        for line in self:
            rt = line.request_id.return_type
            if line.defect_group and rt and line.defect_group.return_type != rt:
                raise ValidationError(_(
                    'Nhóm lỗi "%s" không thuộc loại trả của phiếu.',
                    line.defect_group.name))

    @api.depends('product_id', 'request_id.sale_order_id')
    def _compute_warranty_days(self):
        Reg = self.env['warranty.registration']
        for line in self:
            so = line.request_id.sale_order_id
            if not so or not line.product_id:
                line.warranty_days_remaining = 0
                continue
            regs = Reg.search([
                ('sale_order_id', '=', so.id),
                ('product_id', '=', line.product_id.id),
            ])
            days = max(regs.mapped('days_remaining_wholesale') or [0])
            line.warranty_days_remaining = days

    @api.depends('product_id', 'request_id.sale_order_id')
    def _compute_price_unit(self):
        """Lấy giá lúc bán từ dòng đơn gốc. Tính server-side nên persist kể cả
        khi field readonly trên view (onchange của field readonly không được
        web client gửi lên khi lưu)."""
        for line in self:
            so = line.request_id.sale_order_id
            sol = so.order_line.filtered(
                lambda ol: ol.product_id == line.product_id)[:1] \
                if (so and line.product_id) else False
            if sol:
                line.price_unit = sol.price_unit
            elif not line.price_unit:
                line.price_unit = 0.0

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * (line.price_unit or 0.0)

    @api.onchange('sale_order_line_id')
    def _onchange_sale_order_line(self):
        if self.sale_order_line_id:
            sol = self.sale_order_line_id
            self.product_id = sol.product_id
            self.product_uom_id = sol.product_uom
            self.price_unit = sol.price_unit
            if not self.quantity:
                self.quantity = sol.product_uom_qty

    @api.onchange('product_id')
    def _onchange_product(self):
        if not self.product_id:
            return
        # Lấy giá/đơn vị từ dòng đơn hàng gốc (giá lúc bán) nếu có đơn gốc.
        so = self.request_id.sale_order_id
        sol = so.order_line.filtered(
            lambda line: line.product_id == self.product_id)[:1] if so else False
        if sol:
            self.sale_order_line_id = sol
            self.product_uom_id = sol.product_uom
        elif not self.product_uom_id:
            self.product_uom_id = self.product_id.uom_id

    @api.onchange('reason_id')
    def _onchange_reason(self):
        if self.reason_id:
            self.defect_group = self.reason_id.defect_group
            if self.request_id and not self.request_id.return_type:
                self.request_id.return_type = self.reason_id.default_return_type

    @api.constrains('quantity')
    def _check_qty(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_('Số lượng trả phải > 0.'))
