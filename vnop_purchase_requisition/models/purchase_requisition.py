# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PurchaseRequisition(models.Model):
    _inherit = "purchase.requisition"
    _order = "id desc"

    purchase_region = fields.Selection([
        ('domestic', 'Trong nước'),
        ('foreign', 'Nước ngoài'),
    ], string='Khu vực mua hàng', default='foreign')

    approved_by = fields.Many2one(
        'res.users',
        string='Người duyệt',
        readonly=True,
        copy=False
    )
    approved_date = fields.Datetime(
        string='Thời gian duyệt',
        readonly=True,
        copy=False
    )

    note = fields.Text(string='Ghi chú')

    def action_confirm(self):
        res = super().action_confirm()
        for rec in self:
            if not rec.approved_by:
                rec.write({
                    'approved_by': self.env.user.id,
                    'approved_date': fields.Datetime.now(),
                })
        return res
