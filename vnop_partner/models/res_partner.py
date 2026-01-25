# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.addons.base.models.res_partner import WARNING_MESSAGE, WARNING_HELP


class ResPartner(models.Model):
    _inherit = 'res.partner'

    _sql_constraints = [
        ('ref_unique', 'unique(ref)', 'Mã khách hàng đã tồn tại, vui lòng kiểm tra lại!')
    ]
