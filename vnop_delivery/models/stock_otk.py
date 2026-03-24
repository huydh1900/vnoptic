# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockOtk(models.Model):
    _name = 'stock.otk'
    _description = 'OTK Header'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Số OTK', required=True, copy=False, readonly=True, default='/')
    picking_id = fields.Many2one('stock.picking', required=True, ondelete='cascade', readonly=True)
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('partial', 'Một phần'),
        ('done', 'Hoàn thành'),
    ], default='draft', tracking=True)
    line_ids = fields.One2many('stock.otk.line', 'otk_id', string='Tổng hợp')
    check_ids = fields.One2many('stock.otk.check', 'otk_id', string='Lần OTK')
    ok_picking_ids = fields.One2many('stock.picking', 'otk_ok_id', string='Phiếu hàng đạt')
    ng_picking_ids = fields.One2many('stock.picking', 'otk_ng_id', string='Phiếu hàng lỗi')
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Người tạo', default=lambda self: self.env.user)
    date = fields.Datetime(string='Ngày tạo',default=fields.Datetime.now)
    purchase_id = fields.Many2one('purchase.order', string='Đơn mua hàng', related='picking_id.purchase_id', store=True)
    contract_id = fields.Many2one('contract', string='Hợp đồng', related='purchase_id.contract_id', store=True)
    check_count = fields.Integer(compute='_compute_check_count')

    def _compute_check_count(self):
        data = self.env['stock.otk.check'].read_group(
            [('otk_id', 'in', self.ids)], ['otk_id'], ['otk_id']
        )
        counts = {d['otk_id'][0]: d['otk_id_count'] for d in data}
        for rec in self:
            rec.check_count = counts.get(rec.id, 0)

    def action_view_checks(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Các lần OTK',
            'res_model': 'stock.otk.check',
            'view_mode': 'list,form',
            'domain': [('otk_id', '=', self.id)],
            'context': {'default_otk_id': self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.otk') or '/'
        return super().create(vals_list)
        for otk in self:
            if all(l.qty_remaining == 0 for l in otk.line_ids):
                otk.state = 'done'
            elif any(l.qty_checked > 0 for l in otk.line_ids):
                otk.state = 'partial'

    def action_new_check(self):
        self.ensure_one()
        check = self.env['stock.otk.check'].create({
            'otk_id': self.id,
            'line_ids': [(0, 0, {
                'product_id': l.product_id.id,
                'uom_id': l.uom_id.id,
                'otk_line_id': l.id,
                'qty_to_check': l.qty_remaining,
            }) for l in self.line_ids if l.qty_remaining > 0],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.otk.check',
            'view_mode': 'form',
            'res_id': check.id,
            'target': 'new',
        }


class StockOtkLine(models.Model):
    _name = 'stock.otk.line'
    _description = 'OTK Aggregate Line'

    otk_id = fields.Many2one('stock.otk', ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Sản phẩm', required=True, index=True)
    uom_id = fields.Many2one('uom.uom', string='Đơn vị')
    move_id = fields.Many2one('stock.move')
    qty_received = fields.Float(string='SL nhận', readonly=True)
    qty_checked = fields.Float(string='Đã kiểm', readonly=True)
    qty_ok = fields.Float(string='SL đạt', readonly=True)
    qty_ng = fields.Float(string='SL không đạt', readonly=True)
    qty_remaining = fields.Float(string='Còn lại', compute='_compute_remaining', store=True)

    @api.depends('qty_received', 'qty_checked')
    def _compute_remaining(self):
        for rec in self:
            rec.qty_remaining = rec.qty_received - rec.qty_checked


class StockOtkCheck(models.Model):
    _name = 'stock.otk.check'
    _description = 'OTK Check - Mỗi lần QC'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    otk_id = fields.Many2one('stock.otk', string='OTK', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Số phiếu', readonly=True, default='/')
    sequence = fields.Integer(string='Lần', readonly=True)
    date = fields.Datetime(string='Ngày kiểm', default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='Người kiểm', default=lambda self: self.env.user)
    state = fields.Selection([('draft', 'Nháp'), ('done', 'Hoàn thành')], string='Trạng thái', default='draft')
    line_ids = fields.One2many('stock.otk.check.line', 'check_id', string='Chi tiết kiểm')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.otk.check') or '/'
            if vals.get('otk_id'):
                vals['sequence'] = self.search_count([('otk_id', '=', vals['otk_id'])]) + 1
        return super().create(vals_list)

    def action_confirm(self):
        self.ensure_one()
        loc_main = self.env.ref('stock.stock_location_stock')
        loc_defect = self.env.ref('vnop_delivery.location_defect')
        loc_src = self.otk_id.picking_id.location_dest_id
        picking_type = self.otk_id.picking_id.picking_type_id

        # Validate - chỉ check dòng có qty_to_check > 0
        for line in self.line_ids.filtered(lambda l: l.qty_to_check > 0):
            otk_line = line.otk_line_id
            if line.qty_to_check > otk_line.qty_remaining:
                raise ValidationError(_('SL kiểm vượt quá SL còn lại cho sản phẩm %s.') % line.product_id.display_name)
            if line.qty_ng > line.qty_to_check:
                raise ValidationError(_('SL không đạt không được lớn hơn SL kiểm cho sản phẩm %s.') % line.product_id.display_name)

        # Tạo stock moves cho hàng đạt
        ok_moves = [(0, 0, {
            'name': l.product_id.display_name,
            'product_id': l.product_id.id,
            'product_uom': l.uom_id.id,
            'product_uom_qty': l.qty_ok,
            'location_id': loc_src.id,
            'location_dest_id': loc_main.id,
            'picking_type_id': picking_type.id,
        }) for l in self.line_ids if l.qty_to_check > 0 and l.qty_ok]

        ng_moves = [(0, 0, {
            'name': l.product_id.display_name,
            'product_id': l.product_id.id,
            'product_uom': l.uom_id.id,
            'product_uom_qty': l.qty_ng,
            'location_id': loc_src.id,
            'location_dest_id': loc_defect.id,
            'picking_type_id': picking_type.id,
        }) for l in self.line_ids if l.qty_to_check > 0 and l.qty_ng]

        def _validate_picking(moves, otk_field):
            if not moves:
                return
            picking = self.env['stock.picking'].create({
                'picking_type_id': picking_type.id,
                'location_id': loc_src.id,
                'location_dest_id': moves[0][2]['location_dest_id'],
                'origin': self.name,
                'move_ids': moves,
                otk_field: self.otk_id.id,
            })
            picking.action_confirm()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
            picking.with_context(skip_immediate=True).button_validate()

        _validate_picking(ok_moves, 'otk_ok_id')
        _validate_picking(ng_moves, 'otk_ng_id')

        # Update aggregate lines - chỉ dòng đã kiểm
        for line in self.line_ids.filtered(lambda l: l.qty_to_check > 0):
            otk_line = line.otk_line_id
            otk_line.qty_checked += line.qty_to_check
            otk_line.qty_ok += line.qty_ok
            otk_line.qty_ng += line.qty_ng

        self.state = 'done'
        self.otk_id._update_state()


class StockOtkCheckLine(models.Model):
    _name = 'stock.otk.check.line'
    _description = 'OTK Check Line'

    check_id = fields.Many2one('stock.otk.check', ondelete='cascade', index=True)
    otk_line_id = fields.Many2one('stock.otk.line', string='Dòng OTK')
    product_id = fields.Many2one('product.product', string='Sản phẩm', required=True)
    uom_id = fields.Many2one('uom.uom', string='Đơn vị')
    qty_ordered = fields.Float(string='SL đơn mua', related='otk_line_id.qty_received', readonly=True)
    qty_checked_prev = fields.Float(string='SL đã kiểm', related='otk_line_id.qty_checked', readonly=True)
    qty_to_check = fields.Float(string='SL kiểm')
    qty_ok = fields.Float(string='SL đạt', compute='_compute_qty_ok', store=True)
    qty_ng = fields.Float(string='SL không đạt')

    @api.depends('qty_to_check', 'qty_ng')
    def _compute_qty_ok(self):
        for line in self:
            line.qty_ok = line.qty_to_check - line.qty_ng

    @api.constrains('qty_ok', 'qty_ng', 'qty_to_check')
    def _check_quantities(self):
        for line in self:
            if line.qty_ok < 0 or line.qty_ng < 0:
                raise ValidationError(_('Số lượng không được âm.'))
