from odoo import models, fields, api
from odoo.exceptions import UserError
from collections import defaultdict


class DeliverySchedule(models.Model):
    _name = 'delivery.schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'delivery_datetime desc'
    _rec_name = 'bill_number'
    _description = 'Lịch giao hàng'

    name = fields.Char(string='Đợt giao')
    delivery_datetime = fields.Datetime(
        string='Thời gian giao hàng',
        required=True,
        tracking=True
    )

    declaration_date = fields.Date(
        string='Ngày tờ khai'
    )

    declaration_number = fields.Char(
        string='Số tờ khai'
    )

    bill_number = fields.Char(
        string='Mã vận đơn', required=True
    )

    description = fields.Text(
        string='Mô tả'
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Nhà cung cấp',
        required=True,
        tracking=True
    )

    purchase_ids = fields.Many2many(
        'purchase.order',
        string='Đơn mua hàng'
    )

    picking_ids = fields.One2many(
        'stock.picking',
        'delivery_schedule_id',
        string='Phiếu nhập kho',
        readonly=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
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

    state = fields.Selection([
        ('draft', 'Dự kiến giao'),
        ('confirmed', 'Xác nhận hàng về'),
        ('partial', 'Đã giao một phần'),
        ('done', 'Đã giao đủ'),
        ('cancel', 'Huỷ'),
    ], default='draft', tracking=True)

    input_location_id = fields.Many2one(
        'stock.location', string='Kho tạm (Input)', required=True
    )
    stock_location_id = fields.Many2one(
        'stock.location', string='Kho chính (Stock)', required=True
    )
    defect_location_id = fields.Many2one(
        'stock.location', string='Kho lỗi (Defect)', required=True
    )
    internal_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Loại phiếu điều chuyển',
        domain="[('code','=','internal')]",
        required=True
    )

    ok_transfer_id = fields.Many2one('stock.picking', string='Phiếu chuyển OK', readonly=True)
    defect_transfer_id = fields.Many2one('stock.picking', string='Phiếu chuyển Lỗi', readonly=True)

    def action_view_purchase_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Đơn mua hàng',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.purchase_ids.ids)],
            'target': 'current',
        }

    def action_view_pickings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Phiếu nhập kho',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.picking_ids.ids)],
            'target': 'current',
        }

    def action_confirm_arrival(self):
        self.ensure_one()
        if not self.purchase_ids:
            raise UserError('Vui lòng chọn ít nhất một PO.')

        receipts = self.purchase_ids.mapped('picking_ids').filtered(
            lambda p: p.picking_type_id.code == 'incoming' and p.state not in ('done', 'cancel')
        )
        if not receipts:
            raise UserError('Không tìm thấy phiếu nhập (Receipt) hợp lệ từ các PO đã chọn.')

        # gắn schedule vào receipt
        receipts.write({'delivery_schedule_id': self.id})

        # cập nhật trạng thái schedule
        self.state = 'confirmed'

        return {
            'type': 'ir.actions.act_window',
            'name': 'Phiếu nhập kho theo đợt',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', receipts.ids)],
            'target': 'current',
        }

    def action_qc_create_transfers(self):
        self.ensure_one()

        if self.state not in ('confirmed', 'partial'):
            raise UserError(_('Chỉ QC khi đợt đang "Xác nhận hàng về" hoặc "Đã giao một phần".'))

        if not self.picking_ids:
            raise UserError(_('Đợt này chưa có phiếu nhập kho.'))

        if not (
                self.input_location_id and self.stock_location_id and self.defect_location_id and self.internal_picking_type_id):
            raise UserError(_('Vui lòng cấu hình Kho tạm/Kho chính/Kho lỗi/Loại điều chuyển.'))

        # Tổng hợp số lượng thực nhận (qty_done) theo sản phẩm từ tất cả receipt trong đợt
        qty_by_product = defaultdict(float)
        for picking in self.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
            # lấy dòng chi tiết done (move lines)
            for ml in picking.move_line_ids.filtered(lambda x: x.product_id and x.qty_done > 0):
                qty_by_product[(ml.product_id.id, ml.product_uom_id.id)] += ml.qty_done

        if not qty_by_product:
            raise UserError(
                _('Chưa có số lượng thực nhận (qty_done). Vui lòng nhập số lượng nhận trên Receipt trước.'))

        # (MVP) Toàn bộ qty_done coi như OK chuyển về kho chính
        # Nếu bạn muốn tách OK/Lỗi thì cần wizard nhập qty_defect.
        ok_picking = self.env['stock.picking'].create({
            'picking_type_id': self.internal_picking_type_id.id,
            'location_id': self.input_location_id.id,
            'location_dest_id': self.stock_location_id.id,
            'origin': self.bill_number or self.display_name,
            'delivery_schedule_id': self.id,  # nếu bạn cũng muốn link ngược
        })

        move_vals = []
        for (product_id, uom_id), qty in qty_by_product.items():
            move_vals.append((0, 0, {
                'name': self.env['product.product'].browse(product_id).display_name,
                'product_id': product_id,
                'product_uom': uom_id,
                'product_uom_qty': qty,
                'location_id': self.input_location_id.id,
                'location_dest_id': self.stock_location_id.id,
                'picking_id': ok_picking.id,
            }))
        ok_picking.write({'move_ids_without_package': move_vals})
        ok_picking.action_confirm()
        ok_picking.action_assign()

        self.ok_transfer_id = ok_picking.id
        self.state = 'partial'  # hoặc done tuỳ rule

        return {
            'type': 'ir.actions.act_window',
            'name': _('Phiếu điều chuyển OK'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': ok_picking.id,
            'target': 'current',
        }
