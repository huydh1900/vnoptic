from odoo import models, fields, api


class ProductBrand(models.Model):
    _name = 'product.brand'
    _description = 'Product Brand'
    _order = 'name'

    name = fields.Char(string='Brand Name', required=True, index=True)
    code = fields.Char(string='Brand Code')
    description = fields.Text(string='Description')
    logo = fields.Binary(string='Logo')
    active = fields.Boolean(string='Active', default=True)

    product_count = fields.Integer(
        string='Product Count',
        compute='_compute_product_count'
    )

    @api.depends('name')
    def _compute_product_count(self):
        for brand in self:
            brand.product_count = self.env['product.template'].search_count([
                ('brand_id', '=', brand.id)
            ])

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Brand name must be unique!')
    ]
