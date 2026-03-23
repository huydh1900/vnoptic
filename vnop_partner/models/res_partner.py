# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.addons.base.models.res_partner import WARNING_MESSAGE, WARNING_HELP


class ResPartner(models.Model):
    _inherit = 'res.partner'

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Mã khách hàng đã tồn tại, vui lòng kiểm tra lại!')
    ]

    code = fields.Char(string='Mã khách hàng', required=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ref = (vals.get('ref') or '').strip()
            code = (vals.get('code') or '').strip()

            # Keep technical compatibility for existing code-based flows.
            if ref and not code:
                vals['code'] = ref
            elif code and not ref:
                vals['ref'] = code
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        ref_in = (vals.get('ref') or '').strip()
        code_in = (vals.get('code') or '').strip()

        if ref_in and 'code' not in vals:
            vals['code'] = ref_in
        elif code_in and 'ref' not in vals:
            vals['ref'] = code_in

        return super().write(vals)