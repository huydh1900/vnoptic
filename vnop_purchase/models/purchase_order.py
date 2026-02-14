from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    state = fields.Selection(
        selection_add=[
            ('need_revision', 'Cần chỉnh sửa')
        ]
    )
    approver_id = fields.Many2one('res.users', string="Người duyệt")

    create_date_tmp = fields.Date(
        string='Ngày tạo',
        compute='_compute_create_date_tmp',
    )
    delivery_schedule_ids = fields.Many2many(
        'delivery.schedule',
        string='Lịch giao hàng'
    )

    count_delivery_schedule = fields.Integer(compute='_compute_count_delivery_schedule')


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

    def button_submit_rfq(self):
        if not self.approver_id:
            raise UserError('Người duyệt không được trống!')
        self.write({'state': 'to approve'})

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

    @api.depends('delivery_schedule_ids')
    def _compute_count_delivery_schedule(self):
        for rec in self:
            rec.count_delivery_schedule = len(rec.delivery_schedule_ids)

    def action_view_delivery_schedule(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lịch giao hàng'),
            'res_model': 'delivery.schedule',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.delivery_schedule_ids.ids)],
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_purchase_ids': [(6, 0, [self.id])],
                'from_purchase': True,
            },
            'target': 'current',
        }

    @api.onchange('partner_id')
    def _onchange_partner_id_fill_partner_ref(self):
        if self.partner_id:
            self.partner_ref = self.partner_id.ref or False



