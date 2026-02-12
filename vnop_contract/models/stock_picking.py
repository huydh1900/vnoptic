from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    contract_id = fields.Many2one("contract", string="Contract", index=True, copy=False)
    otk_type = fields.Selection(
        [("ok", "OTK OK"), ("ng", "OTK NG")],
        string="OTK Type",
        copy=False,
        index=True,
    )


class StockMove(models.Model):
    _inherit = "stock.move"

    contract_id = fields.Many2one("contract", string="Contract", index=True, copy=False)


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    contract_id = fields.Many2one("contract", string="Contract", index=True, copy=False)
