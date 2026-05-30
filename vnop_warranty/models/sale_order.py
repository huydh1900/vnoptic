from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    warranty_registration_ids = fields.One2many(
        'warranty.registration', 'sale_order_id',
        string='Phiếu bảo hành',
    )
    warranty_registration_count = fields.Integer(
        string='Số phiếu bảo hành',
        compute='_compute_warranty_registration_count',
    )

    @api.depends('warranty_registration_ids')
    def _compute_warranty_registration_count(self):
        for order in self:
            order.warranty_registration_count = len(order.warranty_registration_ids)

    def action_print_warranty_labels(self):
        """Mở wizard preview tem QR bảo hành (popup)."""
        self.ensure_one()
        if not self.warranty_registration_ids:
            raise UserError(
                "Đơn này chưa có phiếu bảo hành nào để in tem."
            )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Preview tem QR bảo hành',
            'res_model': 'warranty.label.preview.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_sale_order_id': self.id},
        }

    def _get_warranty_for_line(self, line):
        # Dùng "Bảo hành công ty" (warranty_supplier_id) làm gói áp dụng cho
        # khách cuối. Override method này nếu muốn đổi nguồn (ví dụ dùng
        # warranty_id của hãng).
        return line.product_id.product_tmpl_id.warranty_supplier_id

