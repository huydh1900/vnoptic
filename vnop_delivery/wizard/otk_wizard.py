from odoo import models, fields, api
from odoo.exceptions import ValidationError


class OTKWizard(models.TransientModel):
    _name = "otk.wizard"
    _description = "OTK Wizard"

    picking_id = fields.Many2one('stock.picking', string='Phiếu nhập kho', required=True)
    line_ids = fields.One2many('otk.wizard.line', 'wizard_id')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        picking = self.env['stock.picking'].browse(self.env.context.get('default_picking_id'))

        lines = []
        for move in picking.move_ids_without_package:
            lines.append((0, 0, {
                'product_id': move.product_id.id,
                'qty_contract': move.product_uom_qty,
                'qty_received': move.quantity,
                'qty_ok': move.quantity,
            }))

        res['line_ids'] = lines
        return res

    def action_confirm_otk(self):
        self.ensure_one()

        self._mark_po_need_revision()

        kho_chinh = self.env['stock.location'].search([('name', '=', 'Kho chính')], limit=1)
        kho_loi = self.env['stock.location'].search([('name', '=', 'Kho lỗi')], limit=1)

        for line in self.line_ids:
            if line.qty_ok > 0:
                self._create_transfer(line.product_id, line.qty_ok, kho_chinh)

            if line.qty_ng > 0:
                self._create_transfer(line.product_id, line.qty_ng, kho_loi)

    def _mark_po_need_revision(self):
        """Đánh dấu PO cần chỉnh sửa khi OTK lệch so với kế hoạch nhận."""
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

        purchase_orders = self.picking_id.delivery_schedule_id.contract_id.purchase_order_ids
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

    def _create_transfer(self, product, qty, dest):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env['stock.picking.type'].search([
                ('code', '=', 'internal')
            ], limit=1).id,
            'location_id': self.picking_id.location_dest_id.id,
            'location_dest_id': dest.id,
            'partner_id': self.picking_id.partner_id.id,
            'origin': self.picking_id.name,
        })

        self.env['stock.move'].create({
            'name': product.display_name,
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom': product.uom_id.id,
            'picking_id': picking.id,
            'quantity': qty,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
        })

        picking.action_confirm()
        picking.button_validate()


class OTKWizardLine(models.TransientModel):
    _name = "otk.wizard.line"

    wizard_id = fields.Many2one('otk.wizard')

    product_id = fields.Many2one(
        'product.product',
        string="Sản phẩm",
        required=True
    )

    qty_contract = fields.Integer("Hợp đồng")
    qty_received = fields.Integer("Thực tế")
    qty_ok = fields.Integer("Đạt")

    qty_ng = fields.Integer(
        "Lỗi",
        compute="_compute_quantities",
        store=False
    )

    qty_over = fields.Integer(
        "Thừa",
        compute="_compute_quantities",
        store=False
    )

    qty_short = fields.Integer(
        "Thiếu",
        compute="_compute_quantities",
        store=False
    )

    @api.depends('qty_contract', 'qty_received', 'qty_ok')
    def _compute_quantities(self):
        for line in self:

            # Không cho nhập vượt thực tế
            if line.qty_ok > line.qty_received:
                line.qty_ok = line.qty_received

            # Tính lỗi
            line.qty_ng = max(line.qty_received - line.qty_ok, 0)

            # Tính thừa thiếu
            diff = line.qty_received - line.qty_contract

            line.qty_over = max(diff, 0)
            line.qty_short = max(-diff, 0)

    @api.constrains('qty_received', 'qty_ok')
    def _check_quantities(self):
        for line in self:
            if line.qty_ok > line.qty_received:
                raise ValidationError(
                    f"{line.product_id.display_name}: "
                    "Đạt không được lớn hơn Thực tế."
                )
