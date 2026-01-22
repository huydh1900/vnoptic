from odoo import models, fields, api


class ProductLensIndexWizard(models.TransientModel):
    _name = 'product.lens.index.wizard'
    _description = 'Product Lens Index Creation Wizard'

    name = fields.Char('Tên chiết suất', required=True, size=50)
    cid = fields.Char('Mã chiết suất', size=5)
    description = fields.Text('Mô tả', size=100)

    def action_create_lens_index(self):
        self.ensure_one()
        
        # Create the product lens index
        lens_index = self.env['product.lens.index'].create({
            'name': self.name,
            'cid': self.cid,
            'description': self.description,
            'active': True,
        })
        
        # Return action to show the created lens index
        return {
            'type': 'ir.actions.act_window',
            'name': 'Chiết suất',
            'res_model': 'product.lens.index',
            'res_id': lens_index.id,
            'view_mode': 'form',
            'target': 'current',
        }
