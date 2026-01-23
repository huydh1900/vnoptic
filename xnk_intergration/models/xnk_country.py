from odoo import models, fields, api


class XnkCountry(models.Model):
    _name = 'xnk.country'
    _description = 'Country of Origin'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char('Country Name', required=True, index=True)
    code = fields.Char('Country Code', required=True, index=True)
    description = fields.Text('Description')
    active = fields.Boolean('Active', default=True)

    product_count = fields.Integer(
        'Product Count',
        compute='_compute_product_count',
        store=False
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Country code must be unique!'),
    ]

    @api.depends('code')
    def _compute_product_count(self):
        for record in self:
            record.product_count = self.env['product.template'].search_count([
                ('country_id', '=', record.id)
            ])

    def name_get(self):
        result = []
        for record in self:
            name = f"[{record.code}] {record.name}" if record.code else record.name
            result.append((record.id, name))
        return result
