import logging
from odoo import models, api

_logger = logging.getLogger(__name__)

class ProductTemplateDebugLog(models.Model):
    _inherit = 'product.template'

    def write(self, vals):
        _logger.warning("SYNC WRITE product.template ID %s", self.ids)
        _logger.warning("WRITE VALS: %s", vals)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        _logger.warning("SYNC CREATE product.template")
        _logger.warning("CREATE VALS: %s", vals_list)
        return super().create(vals_list)