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
    qty_remaining = fields.Float(string="SL còn lại", digits="Product Unit of Measure")
    price_unit = fields.Float(string="Đơn giá", digits="Product Price")
    amount_total = fields.Float(string="Thành tiền")
    purchase_id = fields.Many2one(
        "purchase.order",
        string="Đơn mua",
    )

    @api.constrains("qty_contract", "product_qty")
    @api.onchange("qty_contract")
    def _check_qty_contract_not_exceed_po(self):
        for line in self:
            if line.qty_contract and line.product_qty:
                if line.qty_contract > line.product_qty:
                    raise UserError("SL theo hợp đồng không được vượt SL đặt hàng.\n\n"
                        "Vui lòng quay lại Đơn mua để điều chỉnh.")
                line.qty_remaining = (line.product_qty or 0.0) - (line.qty_contract or 0.0)




