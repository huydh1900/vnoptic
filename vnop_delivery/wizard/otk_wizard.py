from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class OTKWizard(models.TransientModel):
    _name = "otk.wizard"
    _description = "Trình hướng dẫn OTK"

    picking_id = fields.Many2one('stock.picking', string='Phiếu nhập kho', required=True)
    line_ids = fields.One2many('otk.wizard.line', 'wizard_id', string='Chi tiết OTK')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking = self.env['stock.picking'].browse(self.env.context.get('default_picking_id'))
        if not picking:
            return res

        lines = []
        for move in picking.move_ids_without_package:
            qty_received = self._get_done_qty(move)
            lines.append((0, 0, {
                'product_id': move.product_id.id,
                'qty_contract': move.product_uom_qty,
                'qty_received': qty_received,
                'qty_ok': qty_received,
            }))

        res['line_ids'] = lines
        return res

    def action_confirm_otk(self):
        self.ensure_one()

        if self.picking_id.picking_type_id.code != 'incoming':
            raise UserError("Chỉ hỗ trợ OTK cho phiếu nhập kho đầu vào (Incoming).")

        if self.picking_id.state != 'done':
            raise UserError("Vui lòng Xác nhận phiếu nhập kho trước, sau đó mới thực hiện OTK.")

        self._mark_po_need_revision()

        stock_location = self.picking_id.location_dest_id
        location_ok = self.env['stock.location'].search([
            ('name', 'in', ['Kho đạt', 'WH/Stock/OK']),
            ('usage', '=', 'internal'),
            ('company_id', 'in', [self.picking_id.company_id.id, False]),
        ], limit=1)
        location_ng = self.env['stock.location'].search([
            ('name', 'in', ['Kho lỗi', 'WH/Stock/NG']),
            ('usage', '=', 'internal'),
            ('company_id', 'in', [self.picking_id.company_id.id, False]),
        ], limit=1)

        if not location_ok or not location_ng:
            raise UserError(
                "Thiếu cấu hình location OTK. Vui lòng tạo location nội bộ tên 'Kho đạt' và 'Kho lỗi'."
            )

        ok_lines = [line for line in self.line_ids if line.qty_ok > 0]
        ng_lines = [line for line in self.line_ids if line.qty_ng > 0]

        if ok_lines:
            self._create_internal_transfer(
                source_location=stock_location,
                destination_location=location_ok,
                lines=ok_lines,
            )

        if ng_lines:
            self._create_internal_transfer(
                source_location=stock_location,
                destination_location=location_ng,
                lines=ng_lines,
            )

    def _get_done_qty(self, move):
        if 'quantity' in move._fields:
            return move.quantity
        return move.quantity_done

    def _set_done_qty_on_move_line(self, move_line, qty):
        if 'quantity' in move_line._fields:
            move_line.quantity = qty
        elif 'qty_done' in move_line._fields:
            move_line.qty_done = qty

    def _mark_po_need_revision(self):
        """Đánh dấu PO cần chỉnh sửa khi OTK lệch so với số lượng kế hoạch nhận."""
        self.ensure_one()

        expected_qty = {
            move.product_id.id: move.product_uom_qty
            for move in self.picking_id.move_ids_without_package
            if move.product_id
        }

        has_mismatch = False
        for line in self.line_ids:
            planned_qty = expected_qty.get(line.product_id.id, 0)
            if line.product_id.id not in expected_qty or line.qty_received != planned_qty:
                has_mismatch = True
                break

        if not has_mismatch:
            return

        schedule = self.picking_id.delivery_schedule_id
        purchase_orders = schedule.contract_id.purchase_order_ids if schedule and schedule.contract_id else self.env['purchase.order']
        if not purchase_orders:
            return

        if hasattr(purchase_orders, 'action_need_revision'):
            purchase_orders.action_need_revision()
        else:
            purchase_orders.write({'state': 'need_revision'})

        for order in purchase_orders:
            order.message_post(body=(
                "OTK phát hiện lệch số lượng/chủng loại so với kế hoạch nhận hàng. "
                "Vui lòng chỉnh sửa đơn mua hàng và gửi duyệt lại."
            ))

    def _create_internal_transfer(self, source_location, destination_location, lines):
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('company_id', 'in', [self.picking_id.company_id.id, False]),
        ], limit=1)

        if not picking_type:
            raise UserError("Không tìm thấy loại vận chuyển nội bộ (Internal Transfer).")

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': destination_location.id,
            'partner_id': self.picking_id.partner_id.id,
            'origin': f"{self.picking_id.name} - OTK",
            'company_id': self.picking_id.company_id.id,
            'delivery_schedule_id': self.picking_id.delivery_schedule_id.id,
        })

        move_model = self.env['stock.move']
        for line in lines:
            values = {
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_ok if destination_location.name in ['Kho đạt', 'WH/Stock/OK'] else line.qty_ng,
                'product_uom': line.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': source_location.id,
                'location_dest_id': destination_location.id,
            }
            move_model.create(values)

        picking.action_confirm()
        picking.action_assign()

        for move in picking.move_ids_without_package:
            qty_done = move.product_uom_qty
            if not move.move_line_ids:
                self.env['stock.move.line'].create({
                    'picking_id': picking.id,
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'location_id': source_location.id,
                    'location_dest_id': destination_location.id,
                    'quantity' if 'quantity' in self.env['stock.move.line']._fields else 'qty_done': qty_done,
                })
            else:
                for move_line in move.move_line_ids:
                    self._set_done_qty_on_move_line(move_line, qty_done)

        picking.button_validate()


class OTKWizardLine(models.TransientModel):
    _name = "otk.wizard.line"
    _description = "Dòng kiểm tra OTK"

    wizard_id = fields.Many2one('otk.wizard', string='Phiếu OTK')

    product_id = fields.Many2one(
        'product.product',
        string="Sản phẩm",
        required=True
    )

    qty_contract = fields.Float("Kế hoạch")
    qty_received = fields.Float("Thực tế")
    qty_ok = fields.Float("Đạt")

    qty_ng = fields.Float(
        "Lỗi",
        compute="_compute_quantities",
        store=False
    )

    qty_over = fields.Float(
        "Thừa",
        compute="_compute_quantities",
        store=False
    )

    qty_short = fields.Float(
        "Thiếu",
        compute="_compute_quantities",
        store=False
    )

    @api.depends('qty_contract', 'qty_received', 'qty_ok')
    def _compute_quantities(self):
        for line in self:
            if line.qty_ok > line.qty_received:
                line.qty_ok = line.qty_received

            line.qty_ng = max(line.qty_received - line.qty_ok, 0)

            diff = line.qty_received - line.qty_contract
            line.qty_over = max(diff, 0)
            line.qty_short = max(-diff, 0)

    @api.constrains('qty_received', 'qty_ok')
    def _check_quantities(self):
        for line in self:
            if line.qty_received < 0 or line.qty_ok < 0:
                raise ValidationError(
                    f"{line.product_id.display_name}: số lượng không được âm."
                )
            if line.qty_ok > line.qty_received:
                raise ValidationError(
                    f"{line.product_id.display_name}: "
                    "Đạt không được lớn hơn Thực tế."
                )
