from odoo import fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    warranty_registration_ids = fields.One2many(
        'warranty.registration', 'sale_order_id',
        string='Phiếu bảo hành',
    )

    def action_print_warranty_labels(self):
        """Mở trang HTML preview tem QR bảo hành trong tab mới.

        Không dùng ir.actions.report — dùng trang HTML/CSS thuần để có thể
        tuỳ biến giao diện và để user xem preview rồi quyết định in / lưu PDF
        qua trình duyệt.
        """
        self.ensure_one()
        if not self.warranty_registration_ids:
            raise UserError(
                "Đơn này chưa có phiếu bảo hành nào để in tem."
            )
        return {
            'type': 'ir.actions.act_url',
            'url': '/warranty/labels/%d' % self.id,
            'target': 'new',
        }

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            order._generate_warranty_registrations()
        return res

    def _get_warranty_for_line(self, line):
        # Dùng "Bảo hành công ty" (warranty_supplier_id) làm gói áp dụng cho
        # khách cuối. Override method này nếu muốn đổi nguồn (ví dụ dùng
        # warranty_id của hãng).
        return line.product_id.product_tmpl_id.warranty_supplier_id

    def _generate_warranty_registrations(self):
        """Sinh phiếu bảo hành cho mỗi đơn vị sản phẩm trong đơn.

        Idempotent: gọi nhiều lần không tạo trùng.
        """
        self.ensure_one()
        Reg = self.env['warranty.registration']
        for line in self.order_line:
            if line.display_type:
                continue
            warranty = self._get_warranty_for_line(line)
            if not warranty:
                continue
            qty = int(line.product_uom_qty or 0)
            if qty <= 0:
                continue
            existing = Reg.search_count([('sale_order_line_id', '=', line.id)])
            to_create = max(qty - existing, 0)
            if not to_create:
                continue
            Reg.create([{
                'sale_order_id': self.id,
                'sale_order_line_id': line.id,
                'product_id': line.product_id.id,
                'warranty_id': warranty.id,
            } for _ in range(to_create)])
