from odoo import fields, models


class ProductWarranty(models.Model):
    _inherit = 'product.warranty'

    duration = fields.Integer(
        string='Thời hạn',
        default=12,
        help='Số ngày hoặc tháng bảo hành (theo Đơn vị bên cạnh).',
    )
    duration_unit = fields.Selection(
        [('day', 'Ngày'), ('month', 'Tháng')],
        string='Đơn vị',
        default='month',
        required=True,
    )
    bonus_days = fields.Integer(
        string='Bonus (ngày)',
        default=14,
        help='Số ngày tặng thêm khi tính ngày kết thúc bảo hành.',
    )
