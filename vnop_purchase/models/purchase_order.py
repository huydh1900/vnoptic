from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    create_date_tmp = fields.Date(
        string='Ngày tạo',
        compute='_compute_create_date_tmp',
    )
    delivery_schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Lịch giao hàng',
        readonly=True,
    )

    otk_log_count = fields.Integer(compute='_compute_otk_log_count')

    def _compute_otk_log_count(self):
        data = self.env['stock.otk.log'].read_group(
            [('purchase_id', 'in', self.ids)], ['purchase_id'], ['purchase_id']
        )
        counts = {d['purchase_id'][0]: d['purchase_id_count'] for d in data}
        for rec in self:
            rec.otk_log_count = counts.get(rec.id, 0)

    def action_view_otk_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lần OTK',
            'res_model': 'stock.otk.log',
            'view_mode': 'list,form',
            'domain': [('purchase_id', '=', self.id)],
        }

    def action_rfq_send(self):
        for order in self:

            if not order.order_line:
                raise ValidationError(_("Yêu cầu báo giá cần có ít nhất 01 sản phẩm!"))

            product_lines = order.order_line.filtered(lambda l: l.product_id)

            product_count = {}
            for line in product_lines:
                product_count.setdefault(line.product_id, 0)
                product_count[line.product_id] += 1

            duplicated_products = [
                product.display_name
                for product, count in product_count.items()
                if count > 1
            ]

            if duplicated_products:
                raise ValidationError(
                    _("Sản phẩm bị trùng trong Yêu cầu báo giá:\n- %s")
                    % "\n- ".join(duplicated_products)
                )

        return super().action_rfq_send()

    def action_need_revision(self):
        for rec in self:
            rec.write({'state': 'need_revision'})

    @api.depends('create_date')
    def _compute_create_date_tmp(self):
        for rec in self:
            rec.create_date_tmp = (
                rec.create_date.date() if rec.create_date else False
            )

    def unlink(self):
        for order in self:
            if order.state == 'purchase':
                raise UserError(
                    _("Không thể xóa đơn mua hàng đã được xác nhận.")
                )
        return super(PurchaseOrder, self).unlink()

    def action_view_delivery_schedule(self):
        self.ensure_one()
        if not self.contract_id:
            raise UserError(
                _('Đơn mua %s chưa liên kết hợp đồng. Vui lòng gán hợp đồng trước khi tạo lịch giao.')
                % self.name
            )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lịch giao hàng'),
            'res_model': 'delivery.schedule',
            'view_mode': 'list,form',
            'domain': [('purchase_id', '=', self.id)],
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_purchase_id': self.id,
                'from_purchase': True,
            },
            'target': 'current',
        }

    @api.onchange('partner_id')
    def _onchange_partner_id_fill_partner_ref(self):
        if self.partner_id:
            self.partner_ref = self.partner_id.ref or False
