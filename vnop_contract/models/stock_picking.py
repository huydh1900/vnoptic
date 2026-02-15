from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    contract_id = fields.Many2one("contract", string="Hợp đồng", index=True, copy=False)
    contract_otk_id = fields.Many2one("contract.otk", string="Lần OTK", index=True, copy=False)
    otk_type = fields.Selection(
        [("ok", "OTK đạt"), ("ng", "OTK lỗi")],
        string="Loại OTK",
        copy=False,
        index=True,
    )

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals:
            self.mapped("contract_otk_id")._update_done_state()
        return res

    def button_validate(self):
        res = super().button_validate()
        self.mapped("contract_otk_id")._update_done_state()
        return res


class StockMove(models.Model):
    _inherit = "stock.move"

    contract_id = fields.Many2one("contract", string="Hợp đồng", index=True, copy=False)
    contract_otk_line_id = fields.Many2one("contract.otk.line", string="Dòng OTK", index=True, copy=False)
