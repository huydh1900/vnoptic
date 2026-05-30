# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ReturnQcClassifyWizard(models.TransientModel):
    _name = 'vnop.return.qc.classify.wizard'
    _description = 'Wizard OTK phân loại hàng trả'

    request_id = fields.Many2one('vnop.return.request', required=True,
                                 readonly=True)
    line_ids = fields.One2many('vnop.return.qc.classify.wizard.line',
                               'wizard_id', string='Dòng phân loại')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request = self.env['vnop.return.request'].browse(
            self.env.context.get('default_request_id'))
        if request:
            res['line_ids'] = [(0, 0, {
                'request_line_id': line.id,
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'classify_destination': line.classify_destination or 'commercial',
                'qc_note': line.qc_note,
            }) for line in request.line_ids]
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Không có dòng nào để phân loại.'))
        for wline in self.line_ids:
            if not wline.classify_destination:
                raise UserError(_('Phải chọn kho phân loại cho mọi dòng.'))
            wline.request_line_id.write({
                'classify_destination': wline.classify_destination,
                'qc_note': wline.qc_note,
            })
        self._create_internal_transfers()
        self.request_id.state = 'qc_classified'
        self.request_id._activity_schedule_for_role(
            'chief_accountant',
            _('Duyệt tài chính cho phiếu trả hàng %s', self.request_id.name))
        return {'type': 'ir.actions.act_window_close'}

    def _create_internal_transfers(self):
        env = self.env
        Picking = env['stock.picking']
        warehouse = env['stock.warehouse'].search(
            [('company_id', '=', self.request_id.company_id.id)], limit=1)
        # Source = Kho Tạm; Dest = main stock hoặc Kho Thanh Lý
        src = env.ref('vnop_stock.location_temp_incoming',
                      raise_if_not_found=False) or warehouse.lot_stock_id
        commercial_dst = env.ref('vnop_return.location_commercial',
                                  raise_if_not_found=False) or warehouse.lot_stock_id
        liquidation_dst = env.ref('vnop_return.location_liquidation',
                                  raise_if_not_found=False) or commercial_dst
        # Dùng ref tới loại phiếu nội bộ chuẩn (không lọc active) — giống pattern OTK
        # vnop_delivery; tránh fail khi tính năng "Storage Locations" tắt khiến internal
        # picking type bị active=False nên search thường trả về rỗng.
        picking_type = env.ref('stock.picking_type_internal', raise_if_not_found=False)
        if not picking_type:
            picking_type = env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('warehouse_id', '=', warehouse.id),
            ], limit=1)
        if not picking_type:
            raise UserError(_('Không tìm thấy loại phiếu chuyển kho nội bộ.'))

        # Gom 2 picking: commercial vs liquidation
        groups = {'commercial': [], 'liquidation': []}
        for wline in self.line_ids:
            groups[wline.classify_destination].append(wline)

        created = self.env['stock.picking']
        for dest_key, lines in groups.items():
            if not lines:
                continue
            dst = commercial_dst if dest_key == 'commercial' else liquidation_dst
            picking = Picking.create({
                'picking_type_id': picking_type.id,
                'location_id': src.id,
                'location_dest_id': dst.id,
                'origin': self.request_id.name,
                'company_id': self.request_id.company_id.id,
                # Lấy product/qty/uom từ request_line_id (nguồn thật) thay vì từ
                # dòng wizard: product_id/quantity trên wizard là readonly nên web
                # client không gửi lại khi save → sẽ rỗng nếu đọc trực tiếp wline.
                'move_ids': [(0, 0, {
                    'name': wline.request_line_id.product_id.display_name,
                    'product_id': wline.request_line_id.product_id.id,
                    'product_uom_qty': wline.request_line_id.quantity,
                    'product_uom': wline.request_line_id.product_uom_id.id,
                    'location_id': src.id,
                    'location_dest_id': dst.id,
                    'company_id': self.request_id.company_id.id,
                }) for wline in lines],
            })
            picking.action_confirm()
            created |= picking
        if created:
            self.request_id.classify_picking_ids = [(4, p.id) for p in created]


class ReturnQcClassifyWizardLine(models.TransientModel):
    _name = 'vnop.return.qc.classify.wizard.line'
    _description = 'Dòng wizard phân loại'

    wizard_id = fields.Many2one('vnop.return.qc.classify.wizard',
                                required=True, ondelete='cascade')
    request_line_id = fields.Many2one('vnop.return.request.line',
                                      required=True)
    product_id = fields.Many2one('product.product', string='Sản phẩm',
                                 readonly=True)
    quantity = fields.Float(string='Số lượng', readonly=True)
    classify_destination = fields.Selection(
        [('commercial', 'Kho Thương mại (bán lại)'),
         ('liquidation', 'Kho Thanh lý')],
        string='Phân loại nhập kho', required=True)
    qc_note = fields.Text(string='Ghi chú OTK')
