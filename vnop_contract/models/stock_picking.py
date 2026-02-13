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

    def action_confirm(self):
        res = super().action_confirm()
        for batch in self:
            pending_pickings = batch.picking_ids.filtered(lambda picking: picking.state in ("draft", "confirmed", "waiting"))
            if pending_pickings:
                pending_pickings.action_confirm()
                pending_pickings.action_assign()
        return res

    def action_done(self):
        res = super().action_done()
        self._sync_contract_receipt_progress()
        return res

    def button_validate(self):
        res = super().button_validate()
        self._sync_contract_receipt_progress()
        return res

    def _sync_contract_receipt_progress(self):
        contracts = self.mapped("contract_id")
        if contracts:
            contracts._sync_receipt_progress()
