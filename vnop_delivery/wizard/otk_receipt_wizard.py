# wizard/qc_receipt_wizard.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class OtkReceiptWizard(models.TransientModel):
    _name = 'otk.receipt.wizard'
    _description = 'OTK Receipt'

    picking_id = fields.Many2one('stock.picking', required=True)
    line_ids = fields.One2many('otk.receipt.wizard.line', 'wizard_id')

    def action_confirm_qc(self):
        self.ensure_one()

        for line in self.line_ids:
            if line.qty_ok + line.qty_defect != line.qty_received:
                raise UserError(
                    _('Tổng OK + Lỗi phải bằng số lượng nhận.')
                )

        # tạo phiếu điều chuyển OK / Lỗi (bước sau)


    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking = self.env['stock.picking'].browse(
            self.env.context.get('default_picking_id')
        )

        if not picking:
            return res

        lines = []
        for ml in picking.move_line_ids.filtered(lambda l: l.qty_done > 0):
            lines.append((0, 0, {
                'product_id': ml.product_id.id,
                'qty_received': ml.qty_done,
                'qty_ok': ml.qty_done,
                'qty_defect': 0,
            }))

        res['line_ids'] = lines
        return res



class OtkReceiptWizardLine(models.TransientModel):
    _name = 'otk.receipt.wizard.line'

    wizard_id = fields.Many2one('otk.receipt.wizard')
    product_id = fields.Many2one('product.product')
    qty_received = fields.Float()
    qty_ok = fields.Float()
    qty_defect = fields.Float()