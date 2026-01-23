from odoo import models, fields, api


class XnkBrand(models.Model):
    _name = 'xnk.brand'
    _description = 'Brand (XNK)'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char('Brand Name', required=True, index=True)
    code = fields.Char('Brand Code', index=True)
    description = fields.Text('Description')
    logo = fields.Image('Logo', max_width=512, max_height=512)
    active = fields.Boolean('Active', default=True)

    product_count = fields.Integer(
        'Product Count',
        compute='_compute_product_count',
        store=False
    )

    # SQL Constraints
    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Brand name must be unique!'),
    ]

    # Compute Methods
    @api.depends('name')
    def _compute_product_count(self):
        for record in self:
            record.product_count = self.env['product.template'].search_count([
                ('brand_id', '=', record.id)
            ])

    # Display Name
    def name_get(self):
        result = []
        for record in self:
            # Display name instead of code for better readability
            if record.name:
                name = record.name
            elif record.code:
                name = record.code
            else:
                name = 'Unknown Brand'
            result.append((record.id, name))
        return result
