from odoo import models, fields, api


class DeliverySchedule(models.Model):
    _name = 'delivery.schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'delivery_datetime desc'
    _rec_name = 'purchase_id'
    _description = 'Lịch giao hàng'

    delivery_datetime = fields.Datetime(
        string='Thời gian giao hàng',
        required=True
    )

    declaration_date = fields.Date(
        string='Ngày tờ khai'
    )

    description = fields.Text(
        string='Mô tả'
    )

    declaration_number = fields.Char(
        string='Số tờ khai'
    )

    bill_number = fields.Char(
        string='Số vận đơn'
    )

    insurance_fee = fields.Monetary(
        string='Phí bảo hiểm',
        currency_field='currency_id',
        default=0
    )

    environment_fee = fields.Monetary(
        string='Phí môi trường',
        currency_field='currency_id',
        default=0
    )

    total_declaration_amount = fields.Monetary(
        string='Tổng giá trị theo tờ khai',
        currency_field='currency_id',
        default=0
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Nhà cung cấp',
        required=True
    )

    purchase_id = fields.Many2one(
        'purchase.order',
        string='Mã đơn hàng',
        required=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )

    otk_ids = fields.One2many(
        'delivery.otk',
        'schedule_id',
        string='Các lần OTK'
    )

    state = fields.Selection([
        ('draft', 'Dự kiến'),
        ('confirmed', 'Đã xác nhận'),
        ('partial', 'Đã giao 1 phần'),
        ('done', 'Đã giao hết'),
        ('cancel', 'Huỷ'),
    ], string='Trạng thái giao hàng', default='draft', tracking=True)

    def action_view_po(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Đơn mua hàng',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': self.purchase_id.id,
            'target': 'current',
        }

    def action_confirm(self):
        return
