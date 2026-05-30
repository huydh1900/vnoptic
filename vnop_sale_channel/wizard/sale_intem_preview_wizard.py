# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import api, fields, models


class SaleIntemPreviewWizard(models.TransientModel):
    _name = 'sale.intem.preview.wizard'
    _description = 'Xem trước file In tem'

    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade')
    attachment_id = fields.Many2one(
        'ir.attachment', required=True, ondelete='cascade',
    )
    preview_html = fields.Html(
        compute='_compute_preview_html', sanitize=False, readonly=True,
    )

    @api.depends('attachment_id')
    def _compute_preview_html(self):
        for w in self:
            aid = w.attachment_id.id
            if not aid:
                w.preview_html = False
                continue
            url = f'/attachment_preview/view?aid={aid}'
            w.preview_html = Markup(
                f'<iframe src="{url}" '
                f'style="width:100%;height:70vh;border:0;"></iframe>'
            )

    def action_download(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.attachment_id.id}?download=true',
            'target': 'self',
        }
