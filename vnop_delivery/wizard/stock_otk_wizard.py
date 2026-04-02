# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class StockOtkWizard(models.TransientModel):
    _name = 'stock.otk.wizard'
    _description = 'OTK - Kiểm hàng nhập kho'

    picking_id = fields.Many2one('stock.picking', required=True, readonly=True)
    line_ids = fields.One2many('stock.otk.wizard.line', 'wizard_id', string='Chi tiết kiểm')
    surplus_note = fields.Char(string='Lưu ý', compute='_compute_surplus_note')
    has_surplus = fields.Boolean(compute='_compute_surplus_note')

    @api.depends('line_ids.qty_remaining')
    def _compute_surplus_note(self):
        for wiz in self:
            has_surplus = any(l.qty_remaining > 0 for l in wiz.line_ids)
            wiz.has_surplus = has_surplus
            wiz.surplus_note = _('⚠️ Có sản phẩm SL dư, phần dư sẽ được giữ lại trong kho tạm.') if has_surplus else False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking_id = self.env.context.get('default_picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            lines = []
            for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                lines.append((0, 0, {
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'uom_id': move.product_uom.id,
                    'qty_demand': move.product_uom_qty,
                    'qty_otk': move.quantity,
                }))
            res['line_ids'] = lines
        return res

    def action_confirm(self):
        self.ensure_one()
        for line in self.line_ids:
            if float_compare(line.qty_otk, 0.0, precision_rounding=line.uom_id.rounding or 0.01) < 0:
                raise ValidationError(_('SL kiểm không được âm: %s') % line.product_id.display_name)
            if float_compare(line.qty_ng, line.qty_otk, precision_rounding=line.uom_id.rounding or 0.01) > 0:
                raise ValidationError(_('SL không đạt vượt quá SL kiểm: %s') % line.product_id.display_name)

        picking = self.picking_id

        # Set số lượng thực nhận theo qty_otk trước khi validate
        for line in self.line_ids:
            if line.move_id:
                line.move_id.quantity = line.qty_otk

        res = picking.with_context(skip_immediate=True, skip_backorder=False).button_validate()
        if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
            backorder_wizard = self.env['stock.backorder.confirmation'].with_context(
                res.get('context', {})
            ).create({'pick_ids': [(4, picking.id)]})
            backorder_wizard.process()

        # Tạo phiếu điều chuyển hàng đạt → kho chính, hàng lỗi → kho lỗi
        loc_temp = picking.location_dest_id
        loc_stock = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
        loc_defect = self.env.ref('vnop_delivery.location_defect', raise_if_not_found=False)
        int_type = self.env.ref('stock.picking_type_internal', raise_if_not_found=False)
        if not loc_stock or not loc_defect or not int_type:
            raise ValidationError(_('Thiếu cấu hình kho (stock location / picking type). Vui lòng kiểm tra lại.'))

        ok_lines = [(0, 0, {
            'name': l.product_id.display_name,
            'product_id': l.product_id.id,
            'product_uom': l.uom_id.id,
            'product_uom_qty': l.qty_ok,
            'location_id': loc_temp.id,
            'location_dest_id': loc_stock.id,
        }) for l in self.line_ids if float_compare(l.qty_ok, 0.0, precision_rounding=l.uom_id.rounding or 0.01) > 0]

        ng_lines = [(0, 0, {
            'name': l.product_id.display_name,
            'product_id': l.product_id.id,
            'product_uom': l.uom_id.id,
            'product_uom_qty': l.qty_ng,
            'location_id': loc_temp.id,
            'location_dest_id': loc_defect.id,
        }) for l in self.line_ids if float_compare(l.qty_ng, 0.0, precision_rounding=l.uom_id.rounding or 0.01) > 0]

        def _create_and_validate(move_lines, dest_loc):
            if not move_lines:
                return
            p = self.env['stock.picking'].create({
                'picking_type_id': int_type.id,
                'location_id': loc_temp.id,
                'location_dest_id': dest_loc.id,
                'origin': picking.name,
                'partner_id': picking.partner_id.id,
                'move_ids': move_lines,
            })
            p.action_confirm()
            for move in p.move_ids:
                move.quantity = move.product_uom_qty
            p.with_context(skip_immediate=True).button_validate()

        _create_and_validate(ok_lines, loc_stock)
        _create_and_validate(ng_lines, loc_defect)

        # Tạo snapshot OTK log
        purchase = picking.purchase_id
        seq = self.env['ir.sequence'].next_by_code('stock.otk.log') or '/'
        sequence = self.env['stock.otk.log'].search_count(
            [('purchase_id', '=', purchase.id)] if purchase else [('picking_id', '=', picking.id)]
        ) + 1
        self.env['stock.otk.log'].create({
            'name': seq,
            'sequence': sequence,
            'picking_id': picking.id,
            'purchase_id': purchase.id if purchase else False,
            'line_ids': [(0, 0, {
                'product_id': l.product_id.id,
                'uom_id': l.uom_id.id,
                'qty_demand': l.qty_demand,
                'qty_otk': l.qty_otk,
                'qty_ok': l.qty_ok,
                'qty_ng': l.qty_ng,
                'note': l.note,
            }) for l in self.line_ids if l.qty_otk > 0],
        })

        # Cập nhật SL đã nhận trên delivery.schedule.line và purchase.offer.line
        schedule = picking.delivery_schedule_id
        if schedule:
            # Gán schedule vào PO nếu chưa có
            if picking.purchase_id and not picking.purchase_id.delivery_schedule_id:
                picking.purchase_id.delivery_schedule_id = schedule

            # Build map product_id → schedule_lines để tránh O(n²)
            sl_by_product = {}
            for sl in schedule.line_ids:
                sl_by_product.setdefault(sl.product_id.id, self.env['delivery.schedule.line'])
                sl_by_product[sl.product_id.id] |= sl
            for line in self.line_ids:
                if not line.qty_otk:
                    continue
                schedule_lines = sl_by_product.get(line.product_id.id, self.env['delivery.schedule.line'])
                for sl in schedule_lines:
                    sl.qty_received += line.qty_otk
                offer_line = schedule_lines.mapped(
                    'contract_line_id.purchase_offer_line_id'
                )[:1]
                if offer_line:
                    offer_line.qty_received += line.qty_otk

        return {'type': 'ir.actions.act_window_close'}


class StockOtkWizardLine(models.TransientModel):
    _name = 'stock.otk.wizard.line'
    _description = 'OTK Wizard Line'

    wizard_id = fields.Many2one('stock.otk.wizard', ondelete='cascade')
    move_id = fields.Many2one('stock.move', readonly=True)
    product_id = fields.Many2one('product.product', string='Sản phẩm', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='ĐVT', readonly=True)
    qty_demand = fields.Float(string='SL yêu cầu', readonly=True)
    qty_otk = fields.Float(string='SL kiểm lần này')
    qty_ng = fields.Float(string='SL không đạt')
    qty_ok = fields.Float(string='SL đạt', compute='_compute_qty_ok', store=True)
    qty_remaining = fields.Float(string='SL dư', compute='_compute_qty_remaining')
    note = fields.Char(string='Ghi chú')

    @api.constrains('qty_otk', 'qty_ng')
    def _check_qty_not_negative(self):
        for line in self:
            if line.qty_otk < 0:
                raise ValidationError(_('SL kiểm lần này không được âm: %s') % line.product_id.display_name)
            if line.qty_ng < 0:
                raise ValidationError(_('SL không đạt không được âm: %s') % line.product_id.display_name)

    @api.depends('qty_otk', 'qty_ng', 'qty_demand')
    def _compute_qty_ok(self):
        for line in self:
            base = min(line.qty_otk, line.qty_demand)
            line.qty_ok = base - line.qty_ng

    @api.depends('qty_demand', 'qty_otk')
    def _compute_qty_remaining(self):
        for line in self:
            line.qty_remaining = max(line.qty_otk - line.qty_demand, 0.0)
