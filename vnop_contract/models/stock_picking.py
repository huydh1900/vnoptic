from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    contract_id = fields.Many2one("contract", string="Hợp đồng", index=True, copy=False)
    otk_type = fields.Selection(
        [("ok", "OTK đạt"), ("ng", "OTK lỗi")],
        string="Loại OTK",
        copy=False,
        index=True,
    )

    def _auto_process_validate_result(self, validate_result):
        """Auto process wizard (backorder/immediate transfer) nếu button_validate trả về action dict."""
        if not isinstance(validate_result, dict):
            return

        res_model = validate_result.get("res_model")
        res_id = validate_result.get("res_id")
        if not res_model or not res_id:
            return

        wizard = self.env[res_model].browse(res_id)
        if wizard.exists() and hasattr(wizard, "process"):
            # skip_backorder=False => tạo backorder theo chuẩn
            wizard.with_context(skip_backorder=False).process()


class StockMove(models.Model):
    _inherit = "stock.move"

    contract_id = fields.Many2one("contract", string="Hợp đồng", index=True, copy=False)


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    contract_id = fields.Many2one("contract", string="Hợp đồng", index=True, copy=False)
    origin = fields.Char('Chứng từ gốc', copy=False)

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