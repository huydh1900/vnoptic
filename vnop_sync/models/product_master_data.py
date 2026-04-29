# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductGroup(models.Model):
    _name = 'product.group'
    _description = 'Product Group'
    _order = 'sequence, name'

    name = fields.Char('Tên nhóm', required=True)
    description = fields.Text('Mô tả', size=200)
    cid = fields.Char("CID", required=True)
    sequence = fields.Integer('STT', default=lambda self: (self.search([], order='sequence desc', limit=1)[:1].sequence or 0) + 1)
    category_id = fields.Many2one(
        'product.category',
        string='Danh mục',
        help='Danh mục mà nhóm này áp dụng (dùng để lọc nhóm theo cây danh mục).'
    )
    product_type = fields.Selection([
        ('DT', 'Đơn tròng'),
        ('HT', 'Hai tròng'),
        ('PT', 'Phôi tròng'),
        ('DAT', 'Đa tròng'),
        ('GK', 'Gọng kính'),
        ('PK', 'Phụ kiện'),
    ], string='Phân loại')

    _sql_constraints = [
        ('sequence_unique', 'unique(sequence)', 'STT nhóm sản phẩm phải là duy nhất!'),
    ]

    def _infer_group_code_from_category(self, category):
        categ = category
        while categ:
            code = (getattr(categ, 'code', '') or '').strip().upper()
            if code:
                return code
            categ = categ.parent_id
        return ''

    @api.model_create_multi
    def create(self, vals_list):
        allowed = {k for k, _ in self._fields['product_type'].selection}
        last = self.search([], order='sequence desc', limit=1)
        max_seq = last.sequence if last else 0
        for i, vals in enumerate(vals_list):
            if 'sequence' not in vals:
                vals['sequence'] = max_seq + i + 1
            categ_id = vals.get('category_id')
            if categ_id:
                code = self._infer_group_code_from_category(self.env['product.category'].browse(categ_id))
                if code in allowed:
                    vals['product_type'] = code
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('category_id'):
            allowed = {k for k, _ in self._fields['product_type'].selection}
            code = self._infer_group_code_from_category(self.env['product.category'].browse(vals['category_id']))
            if code in allowed:
                vals = dict(vals)
                vals['product_type'] = code
        return super().write(vals)

class ProductLensIndex(models.Model):
    _name = 'product.lens.index'
    _description = 'Lens Index'
    _order = 'name'

    name = fields.Char('Chiết suất', required=True)
    cid = fields.Char('Mã CID')
    description = fields.Text('Mô tả')


class ProductCoating(models.Model):
    _name = 'product.coating'
    _description = 'Lớp phủ'
    _order = 'name'

    name = fields.Char('Tên đầy đủ', required=True)
    name_en = fields.Char('Tên tiếng Anh')
    cid = fields.Char('Viết tắt')


class ProductCl(models.Model):
    _name = 'product.cl'
    _description = 'Color Options'
    _order = 'name'

    name = fields.Char('Tên màu', required=True)
    code = fields.Char('Mã màu')
    cid = fields.Char('Mã CID')


class ProductUv(models.Model):
    _name = 'product.uv'
    _description = 'UV Protection'
    _order = 'name'

    name = fields.Char('Loại UV', required=True)
    cid = fields.Char('Mã CID')


class ProductFrame(models.Model):
    _name = 'product.frame'
    _description = 'Frame Style'
    _order = 'name'

    name = fields.Char('Tên gọng', required=True)
    cid = fields.Char('Mã CID')


class ProductFrameType(models.Model):
    _name = 'product.frame.type'
    _description = 'Frame Type'
    _order = 'name'

    name = fields.Char('Loại gọng', required=True)
    cid = fields.Char('Mã CID')


class ProductVe(models.Model):
    _name = 'product.ve'
    _description = 'VE'
    _order = 'name'

    name = fields.Char('Tên ve', required=True)
    cid = fields.Char('Mã CID')


class ProductTemple(models.Model):
    _name = 'product.temple'
    _description = 'Temple Style'
    _order = 'name'

    name = fields.Char('Tên càng kính', required=True)
    cid = fields.Char('Mã CID')


class ProductTarget(models.Model):
    _name = 'product.target'
    _description = 'Đối tượng'
    _order = 'name'

    name = fields.Char('Đối tượng', required=True)
    cid = fields.Char('Viết tắt')


class ProductClassification(models.Model):
    _name = 'product.classification'
    _description = 'Nhóm sản phẩm'
    _order = 'category_type_sequence, code'

    _CATEGORY_TYPE_ORDER = {
        'frame': 1,
        'lens': 2,
        'accessory': 3,
        'other': 4,
    }

    name = fields.Char('Tên nhóm', required=True)
    code = fields.Char('Mã nhóm', required=True, index=True)
    category_type = fields.Selection([
        ('frame', 'Gọng kính'),
        ('lens', 'Tròng kính'),
        ('accessory', 'Phụ kiện'),
        ('other', 'Khác'),
    ], string='Phân loại')
    category_type_sequence = fields.Integer(
        compute='_compute_category_type_sequence',
        store=True,
        index=True,
    )

    @api.depends('category_type')
    def _compute_category_type_sequence(self):
        for record in self:
            record.category_type_sequence = self._CATEGORY_TYPE_ORDER.get(record.category_type, 99)
