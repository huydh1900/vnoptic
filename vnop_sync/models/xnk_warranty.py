from odoo import models, fields, api


class XnkWarranty(models.Model):
    _name = 'xnk.warranty'
    _description = 'Warranty (XNK)'
    _order = 'code, name'
    _rec_name = 'name'

    # Basic Fields
    name = fields.Char('Warranty Name', required=True, index=True)
    code = fields.Char('Warranty Code', required=True, index=True)
    description = fields.Text('Description')
    value = fields.Integer('Duration (Days)', default=0, help="Warranty period in days")
    active = fields.Boolean('Active', default=True)

    # Computed Field
    product_count = fields.Integer(
        'Product Count',
        compute='_compute_product_count',
        store=False
    )

    # SQL Constraints
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Warranty code must be unique!'),
    ]

    # Compute Methods
    @api.depends('code')
    def _compute_product_count(self):
        """Đếm số sản phẩm có warranty này"""
        for record in self:
            record.product_count = self.env['product.template'].search_count([
                ('warranty_id', '=', record.id)
            ])

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, record.name))
        return result
