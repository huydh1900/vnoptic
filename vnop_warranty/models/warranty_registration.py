import secrets
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

OTP_TTL_SECONDS = 120


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
        string='Trạng thái',
        default='pending', required=True, index=True,
    )

    customer_name = fields.Char(string='Tên khách hàng')
    customer_phone = fields.Char(string='SĐT')
    customer_email = fields.Char(string='Email')
    customer_address = fields.Char(string='Địa chỉ')

    date_start = fields.Date(string='Ngày kích hoạt')
    date_end = fields.Date(string='Ngày hết hạn')
    activated_at = fields.Datetime(string='Thời điểm kích hoạt', readonly=True)

    date_delivered = fields.Date(
        string='Ngày xuất kho',
        help='Ngày phiếu giao hàng đầu tiên của đơn được xác nhận. '
             'Dùng để tính thời hạn bảo hành bán buôn.',
    )
    date_wholesale_end = fields.Date(
        string='Hết hạn BH bán buôn',
        compute='_compute_wholesale_window',
    )
    days_remaining_wholesale = fields.Integer(
        string='Số ngày BH bán buôn còn lại',
        compute='_compute_wholesale_window',
    )

    otp_code = fields.Char(string='OTP', readonly=True, copy=False)
    otp_expires_at = fields.Datetime(string='OTP hết hạn', readonly=True, copy=False)

    def _generate_dealer_otp(self):
        """Sinh mã OTP 6 số ngẫu nhiên, lưu DB, TTL OTP_TTL_SECONDS, gửi email
        tới partner_id của sale order. Trả về email đã gửi (masked) hoặc raise.
        """
        self.ensure_one()
        partner = self.sale_order_id.partner_id
        email = (partner.email or '').strip()
        if not email:
            return False
        code = '%06d' % secrets.randbelow(1000000)
        self.sudo().write({
            'otp_code': code,
            'otp_expires_at': fields.Datetime.now() + timedelta(seconds=OTP_TTL_SECONDS),
        })
        body = (
            '<p>Mã OTP xem bảo hành bán buôn cho phiếu <b>%s</b>:</p>'
            '<p style="font-size:22px;font-weight:700;letter-spacing:4px;">%s</p>'
            '<p>Mã có hiệu lực trong %d giây.</p>'
        ) % (self.token, code, OTP_TTL_SECONDS)
        self.env['mail.mail'].sudo().create({
            'subject': 'OTP xem bảo hành bán buôn – VNOptic',
            'body_html': body,
            'email_to': email,
            'auto_delete': True,
        }).send()
        return email

    def _verify_dealer_otp(self, code):
        self.ensure_one()
        if not code or not self.otp_code or not self.otp_expires_at:
            return False
        if fields.Datetime.now() > self.otp_expires_at:
            return False
        if str(code).strip() != self.otp_code:
            return False
        # One-shot: xoá OTP sau khi verify thành công.
        self.sudo().write({'otp_code': False, 'otp_expires_at': False})
        return True

    register_url = fields.Char(
        string='Link đăng ký',
        compute='_compute_register_url',
    )

    @api.depends('date_delivered', 'warranty_id.duration', 'warranty_id.duration_unit',
                 'warranty_id.bonus_days')
    def _compute_wholesale_window(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.date_delivered or not rec.warranty_id:
                rec.date_wholesale_end = False
                rec.days_remaining_wholesale = 0
                continue
            w = rec.warranty_id
            bonus = w.bonus_days or 0
            if w.duration_unit == 'month':
                end = rec.date_delivered + relativedelta(months=w.duration or 0) + timedelta(days=bonus)
            else:
                end = rec.date_delivered + timedelta(days=(w.duration or 0) + bonus)
            rec.date_wholesale_end = end
            rec.days_remaining_wholesale = (end - today).days

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
