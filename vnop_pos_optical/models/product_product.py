# -*- coding: utf-8 -*-

from odoo import api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        if 'is_optical_lens' not in fields_list:
            fields_list.append('is_optical_lens')
        return fields_list
