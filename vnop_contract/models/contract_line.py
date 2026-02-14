# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ContractLine(models.Model):
    _name = "contract.line"
    _description = "Dòng tổng hợp sản phẩm theo hợp đồng"
    _order = "id"

    contract_id = fields.Many2one("contract", string="Hợp đồng", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Sản phẩm", required=True)
    uom_id = fields.Many2one("uom.uom", string="ĐVT")
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
    )
    product_qty = fields.Float(string="SL đặt hàng", digits="Product Unit of Measure")
    qty_contract = fields.Float(string="SL theo hợp đồng", digits="Product Unit of Measure")
    price_unit = fields.Float(string="Đơn giá", digits="Product Price")
    amount_total = fields.Float(string="Thành tiền")
    purchase_id = fields.Many2one(
        "purchase.order",
        string="Đơn mua",
    )
    purchase_line_id = fields.Many2one(
        "purchase.order.line",
        string="Dòng PO",
        domain="[('order_id', '=', purchase_id), ('display_type', '=', False)]",
    )

    qty_received = fields.Float(string="SL đã nhận", related='purchase_line_id.qty_received',
                                store=True, digits="Product Unit of Measure")

    qty_remaining = fields.Float(string="Còn lại", compute="_compute_qty_remaining",
                                 digits="Product Unit of Measure")

    @api.onchange("qty_contract")
    @api.constrains("qty_contract", "qty_remaining")
    def _check_qty_contract_not_exceed_remaining(self):
        for line in self:
            if line.qty_contract < 0:
                raise UserError(_("SL theo hợp đồng không được âm."))

            # nếu chưa chọn PO line thì chưa có remaining chuẩn -> bỏ qua
            if not line.purchase_line_id:
                continue

            if line.qty_contract > line.qty_remaining:
                raise UserError(_("SL theo hợp đồng không được lớn hơn SL còn lại."))

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
