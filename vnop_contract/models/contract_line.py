# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ContractLine(models.Model):
    _name = "contract.line"
    _description = "Dòng tổng hợp sản phẩm theo hợp đồng"
    _order = "id"

    contract_id = fields.Many2one("contract", string="Hợp đồng", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Sản phẩm", required=True)
    product_uom = fields.Many2one("uom.uom", string="ĐVT", required=True)

    product_qty = fields.Integer(string="SL đặt hàng", digits="Product Unit of Measure")
    available_qty = fields.Integer(string="SL khả dụng", digits="Product Unit of Measure")
    price_unit = fields.Float(string="Đơn giá", digits="Product Price")
    amount_total = fields.Float(string="Thành tiền")
    contract_quantity = fields.Integer(string="SL hợp đồng")
    allowed_purchase_order_ids = fields.Many2many(
        "purchase.order",
        compute="_compute_allowed_purchase_orders",
        store=False,
    )

    @api.depends("contract_id", "contract_id.purchase_order_ids")
    def _compute_allowed_purchase_orders(self):
        for line in self:
            line.allowed_purchase_order_ids = line.contract_id.purchase_order_ids

    purchase_id = fields.Many2one(
        "purchase.order",
        string="Đơn mua",
        required=True,
        domain="[('id','in', allowed_purchase_order_ids)]",
    )

    @api.onchange("contract_quantity")
    def _onchange_contract_quantity(self):
        for record in self:
            if record.contract_quantity > record.product_qty:
                raise ValidationError("Số lượng theo hợp đồng không được lớn hơn số lượng đặt hàng.")
