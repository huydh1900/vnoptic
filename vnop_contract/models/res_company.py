from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    otk_ok_location_id = fields.Many2one("stock.location", domain="[('usage','=','internal')]", string="Default OTK OK Location")
    otk_ng_location_id = fields.Many2one("stock.location", domain="[('usage','=','internal')]", string="Default OTK NG Location")
    otk_source_location_id = fields.Many2one("stock.location", domain="[('usage','=','internal')]", string="Default OTK Source Location")
    otk_internal_picking_type_id = fields.Many2one("stock.picking.type", domain="[('code','=','internal')]", string="Default OTK Internal Picking Type")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    otk_ok_location_id = fields.Many2one(related="company_id.otk_ok_location_id", readonly=False)
    otk_ng_location_id = fields.Many2one(related="company_id.otk_ng_location_id", readonly=False)
    otk_source_location_id = fields.Many2one(related="company_id.otk_source_location_id", readonly=False)
    otk_internal_picking_type_id = fields.Many2one(related="company_id.otk_internal_picking_type_id", readonly=False)
