# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class StockOtkWizard(models.TransientModel):
    """Wizard OTK nhiều lần trên cùng 1 PO.

    Flow: Mỗi lần OTK → validate picking partial → Odoo tự tạo backorder
    cho phần chưa kiểm → lần OTK tiếp theo thao tác trên backorder đó.
    Tận dụng nguyên bản backorder flow chuẩn của stock module để đảm bảo
    tương thích valuation (stock_account) và purchase.order.line.qty_received.
    """
    _name = 'stock.otk.wizard'
    _description = 'OTK - Kiểm hàng nhập kho'

    picking_id = fields.Many2one('stock.picking', required=True, readonly=True)
    line_ids = fields.One2many('stock.otk.wizard.line', 'wizard_id', string='Chi tiết kiểm')
    extra_line_ids = fields.One2many(
        'stock.otk.wizard.extra.line', 'wizard_id',
        string='SP ngoài PO',
    )
    # Quyết định xử lý phần chưa kiểm:
    # 'yes' → tạo backorder (OTK tiếp lần sau), 'no' → cancel phần còn lại
    create_backorder = fields.Selection([
        ('yes', 'Tạo backorder (nhận tiếp lần sau)'),
        ('no', 'Đóng phần thiếu'),
    ], default='yes', string='Xử lý phần chưa kiểm')
    surplus_note = fields.Char(string='Lưu ý', compute='_compute_surplus_note')
    has_surplus = fields.Boolean(compute='_compute_surplus_note')
    has_extra = fields.Boolean(compute='_compute_has_extra')

    @api.depends('line_ids.qty_remaining')
    def _compute_surplus_note(self):
        for wiz in self:
            has_surplus = any(l.qty_remaining > 0 for l in wiz.line_ids)
            wiz.has_surplus = has_surplus
            wiz.surplus_note = (
                _('Có sản phẩm SL vượt yêu cầu, phần vượt sẽ được nhận vào kho tạm.')
                if has_surplus else False
            )

    @api.depends('extra_line_ids')
    def _compute_has_extra(self):
        for wiz in self:
            wiz.has_extra = bool(wiz.extra_line_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking_id = self.env.context.get('default_picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            lines = []
            # Chỉ load moves chưa done/cancel — trên backorder sẽ chỉ
            # còn phần chưa kiểm từ lần trước
            for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                lines.append((0, 0, {
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'uom_id': move.product_uom.id,
                    'qty_demand': move.product_uom_qty,
                    # Mặc định 0 — bắt buộc user nhập tay để tránh validate nhầm
                    'qty_otk': 0.0,
                }))
            res['line_ids'] = lines
        return res

    def _validate_lines(self):
        """Kiểm tra ràng buộc dữ liệu wizard trước khi chạy flow chính."""
        for line in self.line_ids:
            rounding = line.uom_id.rounding or 0.01
            if float_compare(line.qty_otk, 0.0, precision_rounding=rounding) < 0:
                raise ValidationError(
                    _('SL kiểm không được âm: %s') % line.product_id.display_name
                )
            if float_compare(line.qty_ng, line.qty_otk, precision_rounding=rounding) > 0:
                raise ValidationError(
                    _('SL không đạt vượt quá SL kiểm: %s') % line.product_id.display_name
                )
        for line in self.extra_line_ids:
            rounding = line.uom_id.rounding or 0.01
            if float_compare(line.qty_otk, 0.0, precision_rounding=rounding) <= 0:
                raise ValidationError(
                    _('SP ngoài PO phải có SL kiểm > 0: %s') % line.product_id.display_name
                )
            if float_compare(line.qty_ng, line.qty_otk, precision_rounding=rounding) > 0:
                raise ValidationError(
                    _('SL không đạt vượt quá SL kiểm: %s') % line.product_id.display_name
                )

    def action_confirm(self):
        """Xác nhận OTK — flow chính gồm 7 bước tuần tự.

        Side-effects:
        - Validate picking (tạo account move nếu có stock_account)
        - Tạo backorder picking nếu partial
        - Tạo internal transfers (kho tạm → kho chính / kho lỗi)
        - Tạo return picking nếu có SP trả NCC (chỉ confirm, chưa validate)
        - Ghi OTK log snapshot
        - Cập nhật qty_received trên delivery.schedule.line
        """
        self.ensure_one()
        self._validate_lines()

        picking = self.picking_id

        # Bước 1: Gán qty thực nhận lên stock.move
        # Odoo sẽ dựa vào move.quantity vs move.product_uom_qty để quyết định
        # tạo backorder hay không trong _action_done
        for line in self.line_ids:
            if line.move_id:
                line.move_id.quantity = line.qty_otk

        # Bước 2: SP ngoài PO được nhận → tạo additional move
        # Flag additional=True để _autoconfirm_picking xử lý đúng (line 1553 stock_picking.py)
        # Move này không liên kết PO line → qty_received trên PO không bị ảnh hưởng
        accepted_extras = self.extra_line_ids.filtered(
            lambda l: l.action_type == 'accept'
        )
        for extra in accepted_extras:
            self.env['stock.move'].create({
                'name': extra.product_id.display_name,
                'product_id': extra.product_id.id,
                'product_uom': extra.uom_id.id,
                'product_uom_qty': extra.qty_otk,
                'quantity': extra.qty_otk,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'additional': True,
                'picked': True,
            })

        # Bước 3: Validate picking
        # skip_immediate: bỏ qua wizard "immediate transfer" (đã set qty ở bước 1)
        # picking_ids_not_to_backorder + skip_backorder: cancel phần thiếu thay vì tạo backorder
        ctx = {'skip_immediate': True}
        if self.create_backorder == 'no':
            ctx['picking_ids_not_to_backorder'] = [picking.id]
            ctx['skip_backorder'] = True

        res = picking.with_context(**ctx).button_validate()

        # Nếu Odoo trả về backorder confirmation wizard (picking_type.create_backorder == 'ask')
        # → tự động process để tạo backorder, không hiển thị wizard cho user
        if (self.create_backorder == 'yes'
                and isinstance(res, dict)
                and res.get('res_model') == 'stock.backorder.confirmation'):
            bo_ctx = res.get('context', {})
            bo_wiz = self.env['stock.backorder.confirmation'].with_context(
                **bo_ctx
            ).create({'pick_ids': [(4, picking.id)]})
            bo_wiz.process()

        # Bước 4: Tạo internal transfers phân loại hàng sau OTK
        # Hàng đã nằm ở kho tạm (sau validate picking) → chuyển đến đích cuối
        # Trả về transfer_ok, transfer_ng để ghi vào OTK log (truy vết)
        transfer_ok, transfer_ng = self._create_internal_transfers(picking)

        # Bước 5: SP ngoài PO cần trả NCC → tạo return picking (chỉ confirm)
        # Lưu ý: SP 'return' KHÔNG được tạo move trên picking gốc (bước 2),
        # nên hàng chưa có trong kho tạm → phiếu return ở trạng thái confirmed,
        # chờ user xử lý thủ công (nhận vào trước rồi trả, hoặc trả tại chỗ)
        return_extras = self.extra_line_ids.filtered(
            lambda l: l.action_type == 'return'
        )
        if return_extras:
            self._create_vendor_return(return_extras, picking)

        # Bước 6 & 7: Ghi log (kèm link transfer) + sync upstream
        self._create_otk_log(picking, transfer_ok, transfer_ng)
        self._sync_delivery_schedule(picking)

        return {'type': 'ir.actions.act_window_close'}

    def _get_transfer_locations(self):
        """Lấy 3 tham chiếu cần thiết cho internal transfer: kho chính, kho lỗi, picking type."""
        loc_stock = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
        loc_defect = self.env.ref('vnop_delivery.location_defect', raise_if_not_found=False)
        int_type = self.env.ref('stock.picking_type_internal', raise_if_not_found=False)
        if not loc_stock or not loc_defect or not int_type:
            raise ValidationError(
                _('Thiếu cấu hình kho (stock location / picking type). Vui lòng kiểm tra lại.')
            )
        return loc_stock, loc_defect, int_type

    def _create_internal_transfers(self, picking):
        """Tạo 2 phiếu điều chuyển nội bộ sau OTK: OK → kho chính, NG → kho lỗi.

        Gom cả hàng PO (line_ids) và hàng ngoài PO đã accept (extra_line_ids)
        vào chung phiếu để giảm số lượng picking.
        """
        loc_stock, loc_defect, int_type = self._get_transfer_locations()
        loc_temp = picking.location_dest_id

        all_ok_moves = []
        all_ng_moves = []

        for line in self.line_ids:
            if float_compare(line.qty_ok, 0.0, precision_rounding=line.uom_id.rounding or 0.01) > 0:
                all_ok_moves.append((0, 0, {
                    'name': line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom': line.uom_id.id,
                    'product_uom_qty': line.qty_ok,
                    'location_id': loc_temp.id,
                    'location_dest_id': loc_stock.id,
                }))
            if float_compare(line.qty_ng, 0.0, precision_rounding=line.uom_id.rounding or 0.01) > 0:
                all_ng_moves.append((0, 0, {
                    'name': line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom': line.uom_id.id,
                    'product_uom_qty': line.qty_ng,
                    'location_id': loc_temp.id,
                    'location_dest_id': loc_defect.id,
                }))

        accepted_extras = self.extra_line_ids.filtered(lambda l: l.action_type == 'accept')
        for extra in accepted_extras:
            if float_compare(extra.qty_ok, 0.0, precision_rounding=extra.uom_id.rounding or 0.01) > 0:
                all_ok_moves.append((0, 0, {
                    'name': extra.product_id.display_name,
                    'product_id': extra.product_id.id,
                    'product_uom': extra.uom_id.id,
                    'product_uom_qty': extra.qty_ok,
                    'location_id': loc_temp.id,
                    'location_dest_id': loc_stock.id,
                }))
            if float_compare(extra.qty_ng, 0.0, precision_rounding=extra.uom_id.rounding or 0.01) > 0:
                all_ng_moves.append((0, 0, {
                    'name': extra.product_id.display_name,
                    'product_id': extra.product_id.id,
                    'product_uom': extra.uom_id.id,
                    'product_uom_qty': extra.qty_ng,
                    'location_id': loc_temp.id,
                    'location_dest_id': loc_defect.id,
                }))

        transfer_ok = self._create_and_validate_transfer(
            all_ok_moves, loc_temp, loc_stock, int_type, picking, 'ok',
        )
        transfer_ng = self._create_and_validate_transfer(
            all_ng_moves, loc_temp, loc_defect, int_type, picking, 'ng',
        )
        return transfer_ok, transfer_ng

    def _create_and_validate_transfer(self, move_lines, loc_src, loc_dest, picking_type, origin_picking, otk_type):
        """Tạo 1 phiếu điều chuyển nội bộ và validate ngay.

        Phiếu được gắn otk_type ('ok'/'ng') từ vnop_contract.stock_picking
        để phân biệt mục đích điều chuyển khi truy vết sau này.
        """
        if not move_lines:
            return self.env['stock.picking']
        transfer = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': loc_src.id,
            'location_dest_id': loc_dest.id,
            'origin': origin_picking.name,
            'partner_id': origin_picking.partner_id.id,
            'contract_id': origin_picking.contract_id.id if origin_picking.contract_id else False,
            'otk_type': otk_type,
            'move_ids': move_lines,
        })
        transfer.action_confirm()
        for move in transfer.move_ids:
            move.quantity = move.product_uom_qty
        transfer.with_context(skip_immediate=True).button_validate()
        return transfer

    def _create_vendor_return(self, return_lines, picking):
        """Tạo phiếu trả hàng NCC cho SP sai — chỉ confirm, KHÔNG validate.

        Phiếu ở trạng thái 'assigned' để user review và xử lý thủ công.
        Lý do không auto-validate: SP 'return' chưa được nhận vào kho tạm
        (không có stock quant), cần user quyết định quy trình trả thực tế.
        """
        loc_temp = picking.location_dest_id
        supplier_loc = self.env.ref('stock.stock_location_suppliers', raise_if_not_found=False)
        int_type = self.env.ref('stock.picking_type_internal', raise_if_not_found=False)
        if not supplier_loc or not int_type:
            return

        move_vals = []
        for line in return_lines:
            move_vals.append((0, 0, {
                'name': _('Trả NCC: %s') % line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom': line.uom_id.id,
                'product_uom_qty': line.qty_otk,
                'location_id': loc_temp.id,
                'location_dest_id': supplier_loc.id,
            }))

        if move_vals:
            return_picking = self.env['stock.picking'].create({
                'picking_type_id': int_type.id,
                'location_id': loc_temp.id,
                'location_dest_id': supplier_loc.id,
                'origin': _('Trả NCC từ OTK: %s') % picking.name,
                'partner_id': picking.partner_id.id,
                'move_ids': move_vals,
            })
            return_picking.action_confirm()

    def _create_otk_log(self, picking, transfer_ok=None, transfer_ng=None):
        """Lưu snapshot kết quả OTK — dữ liệu chỉ đọc, phục vụ audit.

        Sequence đếm theo PO (nếu có) để biết PO này đã OTK bao nhiêu lần,
        bất kể trên picking nào (picking gốc hay backorder).
        transfer_ok/transfer_ng: phiếu chuyển kho tạo bởi OTK lần này, dùng để truy vết.
        """
        purchase = picking.purchase_id
        seq = self.env['ir.sequence'].next_by_code('stock.otk.log') or '/'
        domain = ([('purchase_id', '=', purchase.id)]
                  if purchase
                  else [('picking_id', '=', picking.id)])
        sequence = self.env['stock.otk.log'].search_count(domain) + 1

        log_lines = []
        # Chỉ ghi dòng is_checked=True: đã kiểm lần này (kể cả qty_otk=0 = NCC không giao)
        # Dòng chưa tick = chưa kiểm đến, sẽ kiểm trên backorder → không log
        for line in self.line_ids.filtered(lambda l: l.is_checked):
            log_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'uom_id': line.uom_id.id,
                'qty_demand': line.qty_demand,
                'qty_otk': line.qty_otk,
                'qty_ok': line.qty_ok,
                'qty_ng': line.qty_ng,
                'qty_remaining': line.qty_remaining,
                'note': line.note,
            }))
        # SP ngoài PO: qty_demand = 0, qty_remaining = toàn bộ qty_otk
        for extra in self.extra_line_ids.filtered(lambda l: l.qty_otk > 0):
            log_lines.append((0, 0, {
                'product_id': extra.product_id.id,
                'uom_id': extra.uom_id.id,
                'qty_demand': 0.0,
                'qty_otk': extra.qty_otk,
                'qty_ok': extra.qty_ok,
                'qty_ng': extra.qty_ng,
                'qty_remaining': extra.qty_otk,
                'is_extra': True,
                'action_type': extra.action_type,
                'note': extra.note,
            }))

        self.env['stock.otk.log'].create({
            'name': seq,
            'sequence': sequence,
            'picking_id': picking.id,
            'purchase_id': purchase.id if purchase else False,
            'transfer_ok_id': transfer_ok.id if transfer_ok else False,
            'transfer_ng_id': transfer_ng.id if transfer_ng else False,
            'line_ids': log_lines,
        })

    def _sync_delivery_schedule(self, picking):
        """Cộng dồn qty_otk vào delivery.schedule.line.qty_received.

        Chỉ sync cho hàng PO (line_ids) — SP ngoài PO không thuộc schedule nào.
        Dùng dict sl_by_product để tránh O(n²) khi schedule có nhiều lines.
        """
        schedule = picking.delivery_schedule_id
        if not schedule:
            return

        # Gán schedule vào PO nếu chưa có — xảy ra khi picking được tạo
        # trước khi schedule được link (edge case)
        if picking.purchase_id and not picking.purchase_id.delivery_schedule_id:
            picking.purchase_id.delivery_schedule_id = schedule

        sl_by_product = {}
        for sl in schedule.line_ids:
            sl_by_product.setdefault(sl.product_id.id, self.env['delivery.schedule.line'])
            sl_by_product[sl.product_id.id] |= sl

        for line in self.line_ids.filtered(lambda l: l.qty_otk > 0):
            schedule_lines = sl_by_product.get(line.product_id.id, self.env['delivery.schedule.line'])
            for sl in schedule_lines:
                sl.qty_received += line.qty_otk
            # Cập nhật ngược lên purchase.offer.line nếu có liên kết
            offer_line = schedule_lines.mapped('contract_line_id.purchase_offer_line_id')[:1]
            if offer_line:
                offer_line.qty_received += line.qty_otk


class StockOtkWizardLine(models.TransientModel):
    _name = 'stock.otk.wizard.line'
    _description = 'OTK Wizard Line'

    wizard_id = fields.Many2one('stock.otk.wizard', ondelete='cascade')
    move_id = fields.Many2one('stock.move', readonly=True)
    product_id = fields.Many2one('product.product', string='Sản phẩm', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='ĐVT', readonly=True)
    qty_demand = fields.Float(string='SL yêu cầu', readonly=True)
    # User tick = dòng này đã kiểm lần này (kể cả kiểm = 0 vì NCC không giao)
    # Không tick = chưa kiểm đến, chờ backorder lần sau
    is_checked = fields.Boolean(string='Đã kiểm', default=False)
    qty_otk = fields.Float(string='SL kiểm lần này')
    qty_ng = fields.Float(string='SL không đạt')
    qty_ok = fields.Float(string='SL đạt', compute='_compute_qty_ok', store=True)
    qty_remaining = fields.Float(string='SL dư', compute='_compute_qty_remaining')
    note = fields.Char(string='Ghi chú')

    @api.onchange('qty_otk')
    def _onchange_qty_otk_auto_check(self):
        """Tự động tick 'Đã kiểm' khi user nhập SL > 0, tiện cho thao tác nhanh."""
        for line in self:
            if line.qty_otk > 0:
                line.is_checked = True

    @api.constrains('qty_otk', 'qty_ng')
    def _check_qty_not_negative(self):
        for line in self:
            if line.qty_otk < 0:
                raise ValidationError(
                    _('SL kiểm lần này không được âm: %s') % line.product_id.display_name
                )
            if line.qty_ng < 0:
                raise ValidationError(
                    _('SL không đạt không được âm: %s') % line.product_id.display_name
                )

    @api.depends('qty_otk', 'qty_ng')
    def _compute_qty_ok(self):
        """qty_ok = qty_otk - qty_ng (không cap bởi qty_demand).

        Khác với version cũ dùng min(qty_otk, qty_demand): cho phép nhận vượt
        demand — Odoo xử lý over-receipt ở stock.move level (move.quantity >
        move.product_uom_qty không bị chặn, stock_account tính valuation đúng).
        """
        for line in self:
            line.qty_ok = line.qty_otk - line.qty_ng

    @api.depends('qty_demand', 'qty_otk')
    def _compute_qty_remaining(self):
        """Phần vượt demand — hiển thị warning cho user, không block validate."""
        for line in self:
            line.qty_remaining = max(line.qty_otk - line.qty_demand, 0.0)


class StockOtkWizardExtraLine(models.TransientModel):
    """Dòng SP ngoài PO — NCC giao nhầm hoặc giao thêm SP không có trong PO.

    Hai hướng xử lý:
    - 'accept': tạo additional move (flag additional=True) trên picking gốc,
      sau đó chuyển kho tạm → kho chính/kho lỗi như hàng PO.
    - 'return': KHÔNG nhận vào kho, tạo return picking (draft) để user xử lý.
    """
    _name = 'stock.otk.wizard.extra.line'
    _description = 'OTK Wizard - SP ngoài PO'

    wizard_id = fields.Many2one('stock.otk.wizard', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Sản phẩm', required=True)
    uom_id = fields.Many2one(
        'uom.uom', string='ĐVT',
        compute='_compute_uom_id', store=True, readonly=False,
    )
    qty_otk = fields.Float(string='SL kiểm')
    qty_ng = fields.Float(string='SL không đạt')
    qty_ok = fields.Float(string='SL đạt', compute='_compute_qty_ok', store=True)
    action_type = fields.Selection([
        ('accept', 'Nhận vào kho'),
        ('return', 'Trả NCC'),
    ], default='accept', string='Xử lý', required=True)
    note = fields.Char(string='Ghi chú')

    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            line.uom_id = line.product_id.uom_id if line.product_id else False

    @api.depends('qty_otk', 'qty_ng')
    def _compute_qty_ok(self):
        for line in self:
            line.qty_ok = line.qty_otk - line.qty_ng

    @api.constrains('qty_otk', 'qty_ng')
    def _check_qty_not_negative(self):
        for line in self:
            if line.qty_otk < 0:
                raise ValidationError(
                    _('SL kiểm không được âm: %s') % line.product_id.display_name
                )
            if line.qty_ng < 0:
                raise ValidationError(
                    _('SL không đạt không được âm: %s') % line.product_id.display_name
                )
