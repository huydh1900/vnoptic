from odoo import models, fields, api


class ProductMirrorCoatingWizard(models.TransientModel):
    _name = 'product.mirror.coating.wizard'
    _description = 'Mirror Coating Creation Wizard'

    name = fields.Char('Tên màu tráng gương', required=True, size=50)
    cid = fields.Char('Mã màu tráng gương', size=50)
    description = fields.Text('Mô tả', size=100)

    def action_create_mirror_coating(self):
        self.ensure_one()
        
        # Create the mirror coating
        mir_coating = self.env['product.mirror.coating'].create({
            'name': self.name,
            'cid': self.cid,
            'description': self.description,
            'active': True,
        })
        
        # Return action to show the created record
        return {
            'type': 'ir.actions.act_window',
            'name': 'Màu tráng gương',
            'res_model': 'product.mirror.coating',
            'res_id': mir_coating.id,
            'view_mode': 'form',
            'target': 'current',
        }
