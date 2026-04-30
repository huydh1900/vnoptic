# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductLensIndex(models.Model):
    _name = 'product.lens.index'
    _description = 'Lens Index'
    _order = 'name'

    name = fields.Char('Chiết suất', required=True)
    code = fields.Char('Viết tắt', index=True)


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
    name_en = fields.Char('Tên tiếng Anh')
    cid = fields.Char('Viết tắt')


class ProductLensFilm(models.Model):
    _name = 'product.lens.film'
    _description = 'Lớp film chức năng'
    _order = 'name'

    name = fields.Char('Lớp FILM', required=True)
    description = fields.Char('Chú giải')
    cid = fields.Char('Viết tắt')


class ProductLensPhotochromic(models.Model):
    _name = 'product.lens.photochromic'
    _description = 'Đổi màu'
    _order = 'name'

    name = fields.Char('Đổi màu', required=True)
    name_en = fields.Char('Tên tiếng Anh')
    cid = fields.Char('Viết tắt')


class ProductFrameType(models.Model):
    _name = 'product.frame.type'
    _description = 'Frame Type'
    _order = 'name'

    name = fields.Char('Loại gọng', required=True)
    cid = fields.Char('Viết tắt')


class ProductFrameStructure(models.Model):
    _name = 'product.frame.structure'
    _description = 'Frame Structure'
    _order = 'name'

    name = fields.Char('Loại vành', required=True)
    cid = fields.Char('Viết tắt')


class ProductVe(models.Model):
    _name = 'product.ve'
    _description = 'VE'
    _order = 'name'

    name = fields.Char('Tên ve', required=True)
    cid = fields.Char('Mã CID')


class ProductTempleTip(models.Model):
    _name = 'product.temple.tip'
    _description = 'Temple Tip Type'
    _order = 'name'

    name = fields.Char('Loại chuôi càng', required=True)
    cid = fields.Char('Viết tắt')


class ProductTarget(models.Model):
    _name = 'product.target'
    _description = 'Đối tượng'
    _order = 'name'

    name = fields.Char('Đối tượng', required=True)
    cid = fields.Char('Viết tắt')


class ProductClassification(models.Model):
    _name = 'product.classification'
    _description = 'Nhóm sản phẩm'
    _order = 'code'

    name = fields.Char('Tên nhóm', required=True)
    code = fields.Char('Mã nhóm', required=True, index=True)
    category_type = fields.Selection([
        ('frame', 'Gọng kính'),
        ('lens', 'Tròng kính'),
        ('accessory', 'Phụ kiện'),
        ('other', 'Khác'),
    ], string='Phân loại')
