import base64
import io
import logging

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)


class WarrantyPortal(http.Controller):

    @http.route(
        '/warranty/register/<string:token>',
        type='http', auth='public', website=True, csrf=True,
    )
    def register_form(self, token, **kw):
        reg = request.env['warranty.registration'].sudo().search(
            [('token', '=', token)], limit=1,
        )
        if not reg:
            return request.render('vnop_warranty.template_warranty_not_found')
        if reg.state != 'pending':
            return request.render(
                'vnop_warranty.template_warranty_already_active', {'reg': reg},
            )
        return request.render(
            'vnop_warranty.template_warranty_register_form', {'reg': reg},
        )

    @http.route(
        '/warranty/register/<string:token>/submit',
        type='http', auth='public', website=True, csrf=True, methods=['POST'],
    )
    def register_submit(self, token, **post):
        reg = request.env['warranty.registration'].sudo().search(
            [('token', '=', token)], limit=1,
        )
        if not reg:
            return request.render('vnop_warranty.template_warranty_not_found')
        if reg.state != 'pending':
            return request.render(
                'vnop_warranty.template_warranty_already_active', {'reg': reg},
            )
        name = (post.get('customer_name') or '').strip()
        phone = (post.get('customer_phone') or '').strip()
        if not name or not phone:
            return request.render(
                'vnop_warranty.template_warranty_register_form',
                {'reg': reg, 'error': 'Vui lòng nhập Họ tên và SĐT.'},
            )
        reg.action_activate({
            'customer_name': name,
            'customer_phone': phone,
            'customer_email': (post.get('customer_email') or '').strip(),
            'customer_address': (post.get('customer_address') or '').strip(),
        })
        return request.render(
            'vnop_warranty.template_warranty_success', {'reg': reg},
        )

    @http.route(
        '/warranty/check',
        type='http', auth='public', website=True, csrf=True,
    )
    def check_form(self, **kw):
        return request.render('vnop_warranty.template_warranty_check_form')

    @http.route(
        '/warranty/check/lookup',
        type='http', auth='public', website=True, csrf=True, methods=['POST'],
    )
    def check_lookup(self, **post):
        token = (post.get('token') or '').strip()
        phone = (post.get('phone') or '').strip()
        if not token and not phone:
            return request.render(
                'vnop_warranty.template_warranty_check_form',
                {'error': 'Vui lòng nhập Mã phiếu hoặc Số điện thoại.'},
            )
        Registration = request.env['warranty.registration'].sudo()
        if token:
            reg = Registration.search([('token', '=', token)], limit=1)
            if not reg or reg.state == 'pending' or (phone and reg.customer_phone != phone):
                return request.render(
                    'vnop_warranty.template_warranty_check_form',
                    {'error': 'Không tìm thấy phiếu khớp Mã + SĐT.'},
                )
            return request.render(
                'vnop_warranty.template_warranty_check_result', {'reg': reg},
            )
        regs = Registration.search([
            ('customer_phone', '=', phone),
            ('state', '!=', 'pending'),
        ])
        if not regs:
            return request.render(
                'vnop_warranty.template_warranty_check_form',
                {'error': 'Không tìm thấy phiếu bảo hành nào với SĐT này.'},
            )
        return request.render(
            'vnop_warranty.template_warranty_check_list',
            {'regs': regs, 'phone': phone},
        )

    @http.route(
        '/warranty/labels/<int:order_id>',
        type='http', auth='user', methods=['GET'], csrf=False,
    )
    def warranty_labels(self, order_id, **kw):
        """Render trang in tem QR bảo hành cho 1 sale.order.

        Trả về HTML thuần (không qua ir.actions.report). User mở trong tab mới,
        bấm "In / Lưu PDF" trên toolbar — trình duyệt sẽ in hoặc lưu PDF.
        """
        order = request.env['sale.order'].browse(order_id).exists()
        if not order:
            return request.not_found()
        try:
            order.check_access('read')
        except AccessError:
            return request.not_found()
        regs = order.warranty_registration_ids
        qr_map = {}
        try:
            import qrcode
        except ImportError:
            _logger.warning("Python `qrcode` library missing — QR images will be empty.")
            qrcode = None
        if qrcode is not None:
            for reg in regs:
                url = reg.register_url
                if not url:
                    continue
                img = qrcode.make(url)
                buf = io.BytesIO()
                img.save(buf, 'PNG')
                qr_map[reg.id] = base64.b64encode(buf.getvalue()).decode('ascii')
        return request.render(
            'vnop_warranty.warranty_label_print',
            {'order': order, 'regs': regs, 'qr_map': qr_map},
        )
