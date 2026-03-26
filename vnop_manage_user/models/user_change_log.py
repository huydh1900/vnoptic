from odoo import models, fields, api

class UserChangeLog(models.Model):
    _name = 'user.change.log'
    _description = 'User Change Log'
    _order = 'change_time desc'

    user_id = fields.Many2one('res.users', string='Người dùng bị thay đổi', required=True, ondelete='cascade')
    changed_by = fields.Many2one('res.users', string='Người thực hiện', required=True)
    change_time = fields.Datetime(string='Thời gian thay đổi', default=fields.Datetime.now)
    field_name = fields.Char(string='Tên trường', required=True)
    old_value = fields.Text(string='Giá trị cũ')
    new_value = fields.Text(string='Giá trị mới')
