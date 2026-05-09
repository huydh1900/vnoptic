import secrets
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class WarrantyRegistration(models.Model):
    _name = 'warranty.registration'
    _description = 'Phiếu bảo hành sản phẩm'
    _order = 'create_date desc, id desc'

    token = fields.Char(
        string='Mã định danh',
        required=True, readonly=True, index=True, copy=False,
        default=lambda self: secrets.token_urlsafe(16),
    )

    sale_order_id = fields.Many2one(
        'sale.order', string='Đơn bán', required=True,
        ondelete='cascade', index=True,
    )
    sale_order_line_id = fields.Many2one(
        'sale.order.line', string='Dòng đơn', required=True,
        ondelete='cascade', index=True,
    )
    product_id = fields.Many2one(
        'product.product', string='Sản phẩm', required=True,
    )
    warranty_id = fields.Many2one(
        'product.warranty', string='Gói bảo hành', required=True,
    )
    partner_id = fields.Many2one(
        related='sale_order_id.partner_id',
        string='Đại lý', store=True,
    )

    state = fields.Selection(
        [('pending', 'Chờ kích hoạt'),
         ('active', 'Đã kích hoạt'),
         ('expired', 'Hết hạn')],
        default='pending', required=True, index=True,
    )

    customer_name = fields.Char(string='Tên khách cuối')
    customer_phone = fields.Char(string='SĐT khách cuối')
    customer_email = fields.Char(string='Email khách cuối')
    customer_address = fields.Char(string='Địa chỉ khách cuối')

    date_start = fields.Date(string='Ngày bắt đầu')
    date_end = fields.Date(string='Ngày kết thúc')
    activated_at = fields.Datetime(string='Thời điểm kích hoạt', readonly=True)

    register_url = fields.Char(
        string='Link đăng ký',
        compute='_compute_register_url',
    )

    @api.depends('token')
    def _compute_register_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for rec in self:
            rec.register_url = '%s/warranty/register/%s' % (base, rec.token) if rec.token else False

    @api.depends('product_id', 'token')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s · %s' % (
                rec.product_id.display_name or '?',
                (rec.token or '')[:8],
            )

    def action_activate(self, vals):
        """Kích hoạt phiếu — gọi từ controller public sau khi khách điền form."""
        self.ensure_one()
        if self.state != 'pending':
            return False
        warranty = self.warranty_id
        today = fields.Date.context_today(self)
        bonus = warranty.bonus_days or 0
        if warranty.duration_unit == 'month':
            end = today + relativedelta(months=warranty.duration or 0) + timedelta(days=bonus)
        else:
            end = today + timedelta(days=(warranty.duration or 0) + bonus)
        self.write({
            'customer_name': vals.get('customer_name'),
            'customer_phone': vals.get('customer_phone'),
            'customer_email': vals.get('customer_email'),
            'customer_address': vals.get('customer_address'),
            'date_start': today,
            'date_end': end,
            'state': 'active',
            'activated_at': fields.Datetime.now(),
        })
        return True
