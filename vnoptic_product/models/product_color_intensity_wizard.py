from odoo import models, fields, api


class ProductColorIntensityWizard(models.TransientModel):
    _name = 'product.color.intensity.wizard'
    _description = 'Color Intensity Creation Wizard'

    name = fields.Char('Tên độ đậm màu', required=True, size=50)
    cid = fields.Char('Mã độ đậm màu', size=50)
    description = fields.Text('Mô tả', size=100)

    def action_create_color_intensity(self):
        self.ensure_one()
        
        # Create the color intensity
        color_int = self.env['product.color.intensity'].create({
            'name': self.name,
            'cid': self.cid,
            'description': self.description,
            'active': True,
        })
        
        # Return action to show the created record
        return {
            'type': 'ir.actions.act_window',
            'name': 'Độ đậm màu',
            'res_model': 'product.color.intensity',
            'res_id': color_int.id,
            'view_mode': 'form',
            'target': 'current',
        }
