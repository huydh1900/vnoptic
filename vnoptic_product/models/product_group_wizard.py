import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProductGroupWizard(models.TransientModel):
    _name = 'product.group.wizard'
    _description = 'Product Group Creation Wizard'

    name = fields.Char('Tên nhóm', required=True)
    description = fields.Text('Mô tả')
    cid = fields.Char('Mã', required=True)
    group_type_id = fields.Many2one('product.group.type', string='Loại nhóm', required=True)

    def action_create_group(self):
        """Create product group and close wizard"""
        self.ensure_one()

        # Validate
        if not self.name or not self.cid:
            raise UserError("Vui lòng nhập tên nhóm và ký hiệu viết tắt!")

        if not self.group_type_id:
            raise UserError("Vui lòng chọn loại nhóm!")

        # Check if CID already exists
        existing = self.env['product.group'].search([('cid', '=', self.cid)], limit=1)
        if existing:
            raise UserError(f"Ký hiệu '{self.cid}' đã tồn tại! Vui lòng chọn ký hiệu khác.")

        # Create group
        vals = {
            'name': self.name,
            'description': self.description or '',
            'cid': self.cid,
            'group_type_id': self.group_type_id.id,
            'activated': True,
        }

        group = self.env['product.group'].create(vals)

        _logger.info(f"✅ Created product group: {group.name} (CID: {group.cid}, Type: {group.group_type_id.name})")

        # Show success message and close wizard
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Thành công!',
                'message': f'Đã tạo nhóm "{self.name}" thành công!',
                'type': 'success',
                'sticky': False,
            }
        }
