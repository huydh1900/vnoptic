# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ContractLine(models.Model):
    _name = "contract.line"
    _description = "Dòng tổng hợp sản phẩm theo hợp đồng"
    _order = "id"
    _rec_name = "display_name"

    @api.depends('product_id', 'product_qty', 'uom_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.product_id.display_name} ({rec.product_qty} {rec.uom_id.name})" if rec.product_id else "/"

    contract_id = fields.Many2one("contract", string="Hợp đồng", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Sản phẩm", required=True)
    uom_id = fields.Many2one("uom.uom", string="ĐVT")
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
    )
    product_qty = fields.Float(string="SL đặt hàng", digits="Product Unit of Measure")
    price_unit = fields.Float(string="Đơn giá", digits="Product Price")
    amount_total = fields.Float(string="Thành tiền")
    purchase_line_id = fields.Many2one(
        "purchase.order.line",
        string="Dòng PO",
        domain="[('display_type', '=', False)]",
    )

    qty_received = fields.Float(string="SL đã nhận", related='purchase_line_id.qty_received',
                             digits="Product Unit of Measure")

    qty_remaining = fields.Float(string="Còn lại", compute="_compute_qty_remaining",
                                 digits="Product Unit of Measure")

    @api.constrains("product_qty", "qty_remaining")
    def _check_product_qty_not_exceed_remaining(self):
        for line in self:
            if line.product_qty < 0:
                raise UserError(_("Số lượng không được âm."))

            # nếu chưa chọn PO line thì chưa có remaining chuẩn -> bỏ qua
            if not line.purchase_line_id:
                continue

            if line.product_qty > line.qty_remaining:
                raise UserError(_("Số lượng không được lớn hơn SL còn lại."))

    @api.depends("purchase_line_id", 'qty_received')
    def _compute_qty_remaining(self):
        for rec in self:
            rec.qty_remaining = rec.product_qty - rec.qty_received

    @api.constrains("purchase_line_id", "contract_id")
    def _check_purchase_line_unique_in_contract(self):
        for line in self.filtered("purchase_line_id"):
            duplicated = self.search_count([
                ("id", "!=", line.id),
                ("contract_id", "=", line.contract_id.id),
                ("purchase_line_id", "=", line.purchase_line_id.id),
            ])
            if duplicated:
                raise UserError(_("Mỗi dòng PO chỉ được map với một dòng hợp đồng."))
