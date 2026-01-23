from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProductMaterialWizard(models.TransientModel):
    _name = 'product.material.wizard'
    _description = 'Material + Lens Index Wizard'

    # Lens Index
    create_index = fields.Boolean(string='Tạo chiết suất', default=True)
    index_name = fields.Char('Chiết suất', size=50)
    index_cid = fields.Char('Mã chiết suất', size=50)
    index_description = fields.Text('Mô tả chiết suất', size=100)

    # Material
    create_material = fields.Boolean(string='Tạo vật liệu', default=True)
    material_name = fields.Char('Vật liệu', size=50)
    material_cid = fields.Char('Mã vật liệu', size=5)
    material_description = fields.Text('Mô tả vật liệu', size=100)

    @api.constrains('create_index', 'index_name', 'create_material', 'material_name')
    def _check_required_when_selected(self):
        for w in self:
            if w.create_index and not (w.index_name or '').strip():
                raise ValidationError(_('Vui lòng nhập tên chiết suất.'))
            if w.create_material and not (w.material_name or '').strip():
                raise ValidationError(_('Vui lòng nhập tên vật liệu.'))

    def action_create(self):
        self.ensure_one()

        index = False
        material = False

        if self.create_index:
            index = self.env['product.lens.index'].create({
                'name': self.index_name,
                'cid': self.index_cid,
                'description': self.index_description,
                'active': True,
            })

        if self.create_material:
            material = self.env['product.material'].create({
                'name': self.material_name,
                'cid': self.material_cid,
                'description': self.material_description,
                'active': True,
            })

        # Trả về đóng popup; nếu bạn muốn “auto set” vào wizard tạo sản phẩm
        # thì cần gọi wizard này từ product.creation.wizard và set context/field (mình làm tiếp nếu bạn muốn)
        return {'type': 'ir.actions.act_window_close'}
