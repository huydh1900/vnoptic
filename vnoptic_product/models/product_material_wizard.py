from odoo import models, fields, api


class ProductMaterialWizard(models.TransientModel):
    _name = 'product.material.wizard'
    _description = 'Product Material Creation Wizard'

    name = fields.Char('Tên chất liệu', required=True, size=50)
    cid = fields.Char('Mã chất liệu', size=5)
    description = fields.Text('Mô tả', size=100)

    def action_create_material(self):
        self.ensure_one()
        
        # Create the product material
        material = self.env['product.material'].create({
            'name': self.name,
            'cid': self.cid,
            'description': self.description,
            'active': True,
        })
        
        # Return action to show the created material
        return {
            'type': 'ir.actions.act_window',
            'name': 'Chất liệu sản phẩm',
            'res_model': 'product.material',
            'res_id': material.id,
            'view_mode': 'form',
            'target': 'current',
        }
