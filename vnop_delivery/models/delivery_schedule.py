from odoo import models, fields, api
from odoo.exceptions import UserError


class DeliverySchedule(models.Model):
    _name = 'delivery.schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'delivery_datetime desc'
    _rec_name = 'purchase_id'
    _description = 'Lịch giao hàng'

    delivery_datetime = fields.Datetime(
        string='Thời gian giao hàng',
        required=True
    )

    declaration_date = fields.Date(
        string='Ngày tờ khai'
    )

    description = fields.Text(
        string='Mô tả'
    )

    declaration_number = fields.Char(
        string='Số tờ khai'
    )

    bill_number = fields.Char(
        string='Số vận đơn'
    )

    insurance_fee = fields.Monetary(
        string='Phí bảo hiểm',
        currency_field='currency_id',
        default=0
    )

    environment_fee = fields.Monetary(
        string='Phí môi trường',
        currency_field='currency_id',
        default=0
    )

    total_declaration_amount = fields.Monetary(
        string='Tổng giá trị theo tờ khai',
        currency_field='currency_id',
        default=0
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Nhà cung cấp',
        required=True
    )

    purchase_id = fields.Many2one(
        'purchase.order',
        string='Mã đơn hàng',
        required=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )

    # otk_ids = fields.One2many(
    #     'delivery.otk',
    #     'schedule_id',
    #     string='Các lần OTK'
    # )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Phiếu nhập kho',
        readonly=True
    )

    product_id = fields.Many2one(
        'product.product',
        string='Phiếu nhập kho',
        readonly=True
    )

    state = fields.Selection([
        ('draft', 'Dự kiến giao'),
        ('confirmed', 'Xác nhận hàng về'),
        ('partial', 'Đã giao 1 phần'),
        ('done', 'Đã giao hết'),
        ('cancel', 'Huỷ'),
    ], string='Trạng thái giao hàng', default='draft', tracking=True)

    def action_view_po(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Đơn mua hàng',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': self.purchase_id.id,
            'target': 'current',
        }

    def action_confirm(self):
        for rec in self:
            if rec.picking_id:
                continue

            po = rec.purchase_id
            if not po:
                raise UserError('Chưa chọn đơn mua hàng')

            picking = self.env['stock.picking'].create({
                'picking_type_id': po.picking_type_id.id,
                'partner_id': po.partner_id.id,
                'origin': f'{po.name} - Schedule {rec.id}',
                'location_id': po.picking_type_id.default_location_src_id.id,
                'location_dest_id': po.picking_type_id.default_location_dest_id.id,
            })

            for line in po.order_line:
                if line.product_qty <= 0:
                    continue

                self.env['stock.move'].create({
                    'name': line.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_qty,
                    'product_uom': line.product_uom.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'purchase_line_id': line.id,
                    'date': rec.delivery_datetime,
                })

            picking.action_confirm()
            picking.action_assign()

            rec.picking_id = picking.id
            rec.state = 'confirmed'

    @api.model
    def create(self, vals):
        purchase_id = vals.get('purchase_id')
        if purchase_id:
            existed_done = self.search([
                ('purchase_id', '=', purchase_id),
                ('state', '=', 'done')
            ], limit=1)

            if existed_done:
                raise UserError(
                    'Đơn mua hàng này đã có lịch giao hàng ĐÃ GIAO HẾT, không thể tạo lịch mới.'
                )

        return super(DeliverySchedule, self).create(vals)

