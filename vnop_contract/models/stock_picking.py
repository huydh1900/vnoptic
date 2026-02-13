from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    contract_id = fields.Many2one("contract", string="Hợp đồng", index=True, copy=False)
    otk_type = fields.Selection(
        [("ok", "OTK đạt"), ("ng", "OTK lỗi")],
        string="Loại OTK",
        copy=False,
        index=True,
    )

    def button_validate(self):
        res = super().button_validate()
        incoming_done_pickings = self.filtered(
            lambda picking: picking.state == "done" and picking.picking_type_code == "incoming"
        )
        incoming_done_pickings._sync_contract_line_qty_remaining_from_po()
        return res

    def _sync_contract_line_qty_remaining_from_po(self):
        for picking in self:
            remaining_by_po_product = {}
            for po_line in picking.move_ids_without_package.mapped("purchase_line_id"):
                if not po_line or not po_line.order_id or not po_line.product_id:
                    continue
                key = (po_line.order_id.id, po_line.product_id.id)
                remaining_by_po_product[key] = remaining_by_po_product.get(key, 0.0) + (po_line.qty_remaining or 0.0)

            for (purchase_id, product_id), qty_remaining in remaining_by_po_product.items():
                contract_lines = self.env["contract.line"].search([
                    ("purchase_id", "=", purchase_id),
                    ("product_id", "=", product_id),
                ])
                if contract_lines:
                    contract_lines.write({"qty_remaining": qty_remaining})


class StockMove(models.Model):
    _inherit = "stock.move"

    contract_id = fields.Many2one("contract", string="Hợp đồng", index=True, copy=False)


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    contract_id = fields.Many2one("contract", string="Hợp đồng", index=True, copy=False)

    def action_view_contract(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Hợp đồng',
            'res_model': 'contract',
            'view_mode': 'form',
            'target': 'current',
            'res_id': self.contract_id.id,
        }

    def action_view_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lệnh chuyển hàng',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [('id', 'in', self.picking_ids.ids)]
        }
