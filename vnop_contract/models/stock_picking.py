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

    def action_confirm(self):
        res = super().action_confirm()
        reset_qty_done = bool(self.env.context.get("reset_qty_done"))

        for batch in self:
            pickings = batch.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))

            # 1) confirm + assign để picking về assigned (nếu cần)
            to_confirm = pickings.filtered(lambda p: p.state in ("draft", "waiting", "confirmed"))
            if to_confirm:
                to_confirm.action_confirm()

            # incoming thường không cần reserve để validate nếu có done,
            # nhưng action_assign giúp ổn định flow
            to_assign = pickings.filtered(lambda p: p.state in ("confirmed", "waiting"))
            if to_assign:
                to_assign.action_assign()

            # 2) Guard: nếu không có DONE => chặn (đúng spec)
            MoveLine = self.env["stock.move.line"]
            done_field = "quantity" if "quantity" in MoveLine._fields else "qty_done"

            for picking in pickings:
                # chỉ check incoming
                if picking.picking_type_id.code != "incoming":
                    continue

                has_done = any(ml[done_field] > 0 for ml in picking.move_line_ids)
                if not has_done:
                    raise UserError(_(
                        "Phiếu %s chưa có số lượng thực nhận (Done). "
                        "Không thể xác nhận/validate để sinh backorder.\n"
                        "Hãy kiểm tra qty_remaining trên hợp đồng hoặc logic prefill Done."
                    ) % picking.name)

            # 3) Validate + auto process wizard backorder
            for picking in pickings:
                if picking.state in ("done", "cancel"):
                    continue
                validate_result = picking.with_context(skip_immediate=True).button_validate()
                picking._auto_process_validate_result(validate_result)

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
