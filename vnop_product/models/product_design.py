from odoo import models, fields


class ProductDesign(models.Model):
    _name = 'product.design'
    _description = 'Product Design'
    _order = 'name'

    name = fields.Char('Design Name', required=True, size=50)
    description = fields.Text('Description', size=100)
    cid = fields.Char('Design Code', size=5)
    active = fields.Boolean('Active', default=True)
    
    # Design Type
    design_type = fields.Selection([
        ('lens', 'Lens'),
        ('opt', 'Optical'),
        ('other', 'Khác')
    ], string='Loại thiết kế', default='lens')
