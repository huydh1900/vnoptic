from odoo import models, fields, api


class PurchaseContract(models.Model):
    _name = 'purchase.contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Tên hợp đồng", required=True)
    code = fields.Char(string="Mã hợp đồng", required=True)
    vendor_id = fields.Many2one('res.partner', string="Nhà cung cấp", required=True)
    start_date = fields.Date(string='Ngày ký kết')
    end_date = fields.Date(string='Ngày hết hạn')
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('active', 'Hiệu lực'),
        ('expired', 'Hết hiệu lực'),
    ], 'Trạng thái', default='draft', tracking=True)

    order_ids = fields.One2many(
        'purchase.order', 'contract_id', string="Đơn mua hàng"
    )
    order_count = fields.Integer(compute='_compute_purchase_order_count', string='Số đơn hàng')
    description = fields.Text(string='Mô tả')
    type_contract = fields.Selection([
        ('domestic', 'Hợp đồng trong nước'),
        ('foreign', 'Hợp đồng nước ngoài'),
    ], string='Loại hợp đồng', default='foreign', required=True)

    approved_by = fields.Many2one('res.users')
    approved_date = fields.Datetime()

    note = fields.Text()

    def action_activate(self):
        self.state = 'active'

    def action_expire(self):
        return

    @api.depends('order_ids')
    def _compute_purchase_order_count(self):
        for rec in self:
            rec.order_count = len(rec.order_ids)

    def action_view_purchase_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Đơn mua hàng',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id, 'default_vendor_id': self.vendor_id.id},
        }
