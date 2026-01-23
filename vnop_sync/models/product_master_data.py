# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductGroup(models.Model):
    _name = 'product.group'
    _description = 'Product Group'
    _order = 'name'

    name = fields.Char('Tên nhóm', required=True)
    description = fields.Text('Mô tả', size=200)
    activated = fields.Boolean('Kích hoạt', default=True)
    cid = fields.Char("Mã nhóm", required=True)
    group_type_id = fields.Many2one('product.group.type', string='Loại nhóm')


class ProductGroupType(models.Model):
    _name = 'product.group.type'
    _description = 'Product Group Type'
    _order = 'name'

    name = fields.Char('Name', required=True)
    code = fields.Char('Code')


class ProductStatus(models.Model):
    _name = 'product.status'
    _description = 'Product Status'
    _order = 'name'

    name = fields.Char('Status Name', required=True)
    description = fields.Text('Description')
    activated = fields.Boolean('Activated', default=True)


class ProductDesign(models.Model):
    _name = 'product.design'
    _description = 'Product Design'
    _order = 'name'

    name = fields.Char('Design Name', required=True)
    description = fields.Text('Description')
    activated = fields.Boolean('Activated', default=True)


class ProductMaterial(models.Model):
    _name = 'product.material'
    _description = 'Product Material'
    _order = 'name'

    name = fields.Char('Material Name', required=True)
    description = fields.Text('Description')
    activated = fields.Boolean('Activated', default=True)


class ProductLensIndex(models.Model):
    _name = 'product.lens.index'
    _description = 'Lens Index'
    _order = 'name'

    name = fields.Char('Index Value', required=True)
    description = fields.Text('Description')
    activated = fields.Boolean('Activated', default=True)


class ProductCoating(models.Model):
    _name = 'product.coating'
    _description = 'Product Coating'
    _order = 'name'

    name = fields.Char('Coating Name', required=True)
    description = fields.Text('Description')
    activated = fields.Boolean('Activated', default=True)


class ProductCl(models.Model):
    _name = 'product.cl'
    _description = 'Color Options'
    _order = 'name'

    name = fields.Char('Color Name', required=True)
    code = fields.Char('Color Code')
    activated = fields.Boolean('Activated', default=True)


class ProductUv(models.Model):
    _name = 'product.uv'
    _description = 'UV Protection'
    _order = 'name'

    name = fields.Char('UV Type', required=True)
    activated = fields.Boolean('Activated', default=True)


class ProductFrame(models.Model):
    _name = 'product.frame'
    _description = 'Frame Style'
    _order = 'name'

    name = fields.Char('Frame Name', required=True)
    activated = fields.Boolean('Activated', default=True)


class ProductFrameType(models.Model):
    _name = 'product.frame.type'
    _description = 'Frame Type'
    _order = 'name'

    name = fields.Char('Frame Type', required=True)
    activated = fields.Boolean('Activated', default=True)


class ProductShape(models.Model):
    _name = 'product.shape'
    _description = 'Product Shape'
    _order = 'name'

    name = fields.Char('Shape Name', required=True)
    activated = fields.Boolean('Activated', default=True)


class ProductVe(models.Model):
    _name = 'product.ve'
    _description = 'VE'
    _order = 'name'

    name = fields.Char('VE Name', required=True)
    activated = fields.Boolean('Activated', default=True)


class ProductTemple(models.Model):
    _name = 'product.temple'
    _description = 'Temple Style'
    _order = 'name'

    name = fields.Char('Temple Name', required=True)
    activated = fields.Boolean('Activated', default=True)
