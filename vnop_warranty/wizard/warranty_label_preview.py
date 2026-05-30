import base64
import io
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class WarrantyLabelPreviewWizard(models.TransientModel):
    _name = 'warranty.label.preview.wizard'
    _description = 'Wizard preview tem QR bảo hành'

    sale_order_id = fields.Many2one(
        'sale.order', string='Đơn bán', required=True,
        ondelete='cascade',
    )
    registration_ids = fields.Many2many(
        'warranty.registration', string='Phiếu bảo hành',
        compute='_compute_registration_ids',
    )
    preview_html = fields.Html(
        string='Preview', compute='_compute_preview_html', sanitize=False,
    )

    @api.depends('sale_order_id')
    def _compute_registration_ids(self):
        for wiz in self:
            wiz.registration_ids = wiz.sale_order_id.warranty_registration_ids

    @api.depends('registration_ids')
    def _compute_preview_html(self):
        for wiz in self:
            regs = wiz.registration_ids
            qr_map = wiz._build_qr_map(regs)
            wiz.preview_html = self.env['ir.qweb']._render(
                'vnop_warranty.warranty_label_preview_body',
                {
                    'order': wiz.sale_order_id,
                    'regs': regs,
                    'qr_map': qr_map,
                },
            )

    @staticmethod
    def _build_qr_map(regs):
        qr_map = {}
        try:
            import qrcode
        except ImportError:
            _logger.warning("Python `qrcode` library missing — QR images will be empty.")
            return qr_map
        for reg in regs:
            url = reg.register_url
            if not url:
                continue
            img = qrcode.make(url)
            buf = io.BytesIO()
            img.save(buf, 'PNG')
            qr_map[reg.id] = base64.b64encode(buf.getvalue()).decode('ascii')
        return qr_map

    def action_print(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/warranty/labels/%d' % self.sale_order_id.id,
            'target': 'new',
        }
