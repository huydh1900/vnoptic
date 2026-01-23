from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProductIntegrationWizard(models.TransientModel):
    _name = 'product.integration.wizard'
    _description = 'UV + Pho CL Integration Wizard'

    # UV
    create_uv = fields.Boolean(string='Tạo UV', default=True)
    uv_name = fields.Char('Tên UV', size=50)
    uv_cid = fields.Char('Mã UV', size=50)
    uv_description = fields.Text('Mô tả UV', size=50)

    # Pho CL (for Pho Col, HMC, Tint Col)
    create_pho_cl = fields.Boolean(string='Tạo Pho CL', default=True)
    pho_cl_name = fields.Char('Tên Pho CL', size=50)
    pho_cl_cid = fields.Char('Mã Pho CL', size=50)
    pho_cl_description = fields.Text('Mô tả Pho CL', size=100)

    @api.constrains('create_uv', 'uv_name', 'create_pho_cl', 'pho_cl_name')
    def _check_required_when_selected(self):
        for w in self:
            if w.create_uv and not (w.uv_name or '').strip():
                raise ValidationError(_('Vui lòng nhập tên UV.'))
            if w.create_pho_cl and not (w.pho_cl_name or '').strip():
                raise ValidationError(_('Vui lòng nhập tên Pho CL.'))

    def action_create(self):
        self.ensure_one()

        uv = False
        pho_cl = False

        if self.create_uv:
            uv = self.env['product.uv'].create({
                'name': self.uv_name,
                'cid': self.uv_cid,
                'description': self.uv_description,
                'active': True,
            })

        if self.create_pho_cl:
            pho_cl = self.env['product.cl'].create({
                'name': self.pho_cl_name,
                'cid': self.pho_cl_cid,
                'description': self.pho_cl_description,
                'active': True,
            })

        return {'type': 'ir.actions.act_window_close'}
