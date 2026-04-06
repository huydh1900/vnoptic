from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    contract_id = fields.Many2one("contract", string="Hợp đồng", index=True, copy=False)
    otk_type = fields.Selection(
        [("ok", "Vào Kho chính"), ("ng", "Vào Kho lỗi")],
        string="Loại OTK",
        copy=False,
        index=True,
    )


class StockMove(models.Model):
    _inherit = "stock.move"

    contract_id = fields.Many2one("contract", string="Hợp đồng", index=True, copy=False)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _synchronize_quant(self, quantity, location, action="available",
                           in_date=False, **quants_value):
        contract = self.move_id.contract_id if self.move_id else self.env['contract']
        if contract:
            self = self.with_context(quant_contract_id=contract.id)
        return super()._synchronize_quant(
            quantity, location, action=action, in_date=in_date, **quants_value,
        )
