from odoo import models, fields, api


class ProductCoatingWizard(models.TransientModel):
    _name = 'product.coating.wizard'
    _description = 'Product Coating Creation Wizard'

    name = fields.Char('Tên lớp phủ', required=True, size=50)
    cid = fields.Char('Mã lớp phủ', size=50)
    description = fields.Text('Mô tả', size=100)

    def action_create_coating(self):
        self.ensure_one()
        
        # Create the product coating
        coating = self.env['product.coating'].create({
            'name': self.name,
            'cid': self.cid,
            'description': self.description,
            'active': True,
        })
        
        # Return action to show the created coating
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lớp phủ sản phẩm',
            'res_model': 'product.coating',
            'res_id': coating.id,
            'view_mode': 'form',
            'target': 'current',
        }
