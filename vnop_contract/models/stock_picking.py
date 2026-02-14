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
        if not isinstance(validate_result, dict):
            return

        res_model = validate_result.get("res_model")
        res_id = validate_result.get("res_id")
        if not res_model or not res_id:
            return

        wizard = self.env[res_model].browse(res_id)
        if not wizard.exists():
            return

        if hasattr(wizard, "process"):
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

    def action_confirm(self):
        res = super().action_confirm()
        move_line_done_field = "quantity" if "quantity" in self.env["stock.move.line"]._fields else "qty_done"
        for batch in self:
            pending_pickings = batch.picking_ids.filtered(lambda picking: picking.state in ("draft", "confirmed", "waiting"))
            if pending_pickings:
                pending_pickings.action_confirm()
                pending_pickings.action_assign()

            if batch.contract_id:
                batch.contract_id._prefill_qty_done_from_contract(
                    batch.picking_ids,
                    reset_qty_done=bool(self.env.context.get("reset_qty_done")),
                )

            incoming_pickings = batch.picking_ids.filtered(
                lambda picking: picking.picking_type_id.code == "incoming" and picking.state not in ("done", "cancel")
            )
            has_contract_qty_done = any(
                line[move_line_done_field] > 0
                for line in incoming_pickings.move_line_ids
            )
            if incoming_pickings and not has_contract_qty_done:
                raise UserError(_("Không có số lượng nhận theo hợp đồng để xác nhận phiếu nhập."))

            pickings_to_validate = batch.picking_ids.filtered(lambda picking: picking.state not in ("done", "cancel"))
            for picking in pickings_to_validate:
                validate_result = picking.with_context(skip_immediate=True).button_validate()
                picking._auto_process_validate_result(validate_result)

        self._sync_contract_receipt_progress()
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
