# -*- coding: utf-8 -*-

from odoo import api, fields, models


POS_CATEGORY_XMLID_MAP = {
    'vnop_sync.product_category_gong': 'vnop_pos_optical.pos_category_gong',
    'vnop_sync.product_category_trong': 'vnop_pos_optical.pos_category_trong',
    'vnop_sync.product_category_glasses': 'vnop_pos_optical.pos_category_glasses',
    'vnop_sync.product_category_kids_glasses': 'vnop_pos_optical.pos_category_kids_glasses',
    'vnop_sync.product_category_accessory': 'vnop_pos_optical.pos_category_accessory',
    'vnop_sync.product_category_equipment': 'vnop_pos_optical.pos_category_equipment',
    'vnop_sync.product_category_service': 'vnop_pos_optical.pos_category_service',
}

POS_CATEGORY_SEQUENCE_MAP = {
    'vnop_pos_optical.pos_category_gong': 10,
    'vnop_pos_optical.pos_category_trong': 20,
    'vnop_pos_optical.pos_category_glasses': 30,
    'vnop_pos_optical.pos_category_kids_glasses': 40,
    'vnop_pos_optical.pos_category_accessory': 50,
    'vnop_pos_optical.pos_category_equipment': 60,
    'vnop_pos_optical.pos_category_service': 70,
}


class ProductCategory(models.Model):
    _inherit = 'product.category'

    vnop_pos_category_id = fields.Many2one(
        comodel_name='pos.category',
        string='Danh mục POS đồng bộ',
        copy=False,
        readonly=True,
        ondelete='set null',
        help='Danh mục POS được tạo tự động từ danh mục sản phẩm để POS hiển thị theo product.template.categ_id.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        categories = super().create(vals_list)
        if not self.env.context.get('vnop_skip_pos_category_sync'):
            categories.env['product.category']._vnop_sync_pos_categories_from_products()
        return categories

    def write(self, vals):
        res = super().write(vals)
        sync_fields = {'name', 'parent_id', 'sequence'}
        if sync_fields.intersection(vals) and not self.env.context.get('vnop_skip_pos_category_sync'):
            self.env['product.category']._vnop_sync_pos_categories_from_products()
        return res

    def _vnop_sync_pos_category(self):
        self.ensure_one()
        pos_category = self.vnop_pos_category_id
        if not pos_category:
            return pos_category

        vals = {}
        if pos_category.name != self.name:
            vals['name'] = self.name
        if vals:
            pos_category.write(vals)
        return pos_category

    @api.model
    def _vnop_reset_pos_category_sequences_from_data(self):
        for pos_category_xmlid, sequence in POS_CATEGORY_SEQUENCE_MAP.items():
            pos_category = self.env.ref(pos_category_xmlid, raise_if_not_found=False)
            if pos_category and pos_category.sequence != sequence:
                pos_category.sequence = sequence

    @api.model
    def _vnop_link_pos_categories_from_data(self):
        for product_category_xmlid, pos_category_xmlid in POS_CATEGORY_XMLID_MAP.items():
            product_category = self.env.ref(product_category_xmlid, raise_if_not_found=False)
            pos_category = self.env.ref(pos_category_xmlid, raise_if_not_found=False)
            if product_category and pos_category and product_category.vnop_pos_category_id != pos_category:
                product_category.with_context(vnop_skip_pos_category_sync=True).write({
                    'vnop_pos_category_id': pos_category.id,
                })

    @api.model
    def _vnop_sync_pos_categories_from_products(self):
        """Mirror product.template.categ_id into POS categories.

        Odoo POS filters by product.template.pos_categ_ids, so we keep that
        technical field synchronized with the normal product category selected
        by users on product.template.categ_id.
        """
        self._vnop_link_pos_categories_from_data()
        self._vnop_reset_pos_category_sequences_from_data()
        products = self.env['product.template'].with_context(active_test=False).search([
            ('available_in_pos', '=', True),
            ('sale_ok', '=', True),
            ('categ_id', '!=', False),
        ])
        categories = products.mapped('categ_id').filtered('vnop_pos_category_id')
        for category in categories:
            category._vnop_sync_pos_category()

        for category in categories:
            pos_category = category.vnop_pos_category_id
            products.filtered(lambda product: product.categ_id == category).with_context(
                vnop_skip_pos_category_sync=True
            ).write({'pos_categ_ids': [(6, 0, [pos_category.id])]})

        unmapped_products = products.filtered(lambda product: not product.categ_id.vnop_pos_category_id)
        if unmapped_products:
            unmapped_products.with_context(vnop_skip_pos_category_sync=True).write({'pos_categ_ids': [(5, 0, 0)]})
