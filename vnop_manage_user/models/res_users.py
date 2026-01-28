from odoo import models, api

class ResUsers(models.Model):
    _name = 'res.users'
    _inherit = ['res.users', 'mail.thread']
    
    # Override write để tracking TẤT CẢ thay đổi
    @api.model_create_multi
    def create(self, vals_list):
        users = super(ResUsers, self).create(vals_list)
        for user in users:
            user.message_post(body="Tài khoản người dùng đã được tạo")
        return users
    
    def write(self, vals):
        # Bỏ qua các field hệ thống không cần tracking
        skip_fields = ['write_date', 'write_uid', 'create_date', 'create_uid', '__last_update', 
                      'message_follower_ids', 'message_ids', 'activity_ids']
        
        # Lọc các field thực sự cần tracking
        tracking_vals = {k: v for k, v in vals.items() if k not in skip_fields and k in self._fields}
        
        if tracking_vals:
            for user in self:
                # Lưu giá trị cũ
                old_values = {}
                for field_name in tracking_vals.keys():
                    try:
                        old_values[field_name] = getattr(user, field_name)
                    except:
                        old_values[field_name] = None
                
                # Thực hiện update
                result = super(ResUsers, user).write(vals)
                
                # Tạo message tracking cho từng field thay đổi
                changes = []
                for field_name, new_value in tracking_vals.items():
                    old_value = old_values.get(field_name)
                    field_obj = self._fields.get(field_name)
                    if not field_obj:
                        continue
                    
                    # Format giá trị hiển thị
                    try:
                        if field_obj.type == 'many2one':
                            old_display = old_value.display_name if old_value else 'Không có'
                            new_obj = self.env[field_obj.comodel_name].browse(new_value) if new_value else None
                            new_display = new_obj.display_name if new_obj else 'Không có'
                        elif field_obj.type == 'many2many':
                            old_display = ', '.join(old_value.mapped('display_name')) if old_value else 'Không có'
                            if new_value and isinstance(new_value, list) and len(new_value) > 0:
                                if new_value[0][0] == 6:  # (6, 0, [ids])
                                    new_ids = new_value[0][2]
                                    new_objs = self.env[field_obj.comodel_name].browse(new_ids)
                                    new_display = ', '.join(new_objs.mapped('display_name'))
                                else:
                                    new_display = str(new_value)
                            else:
                                new_display = 'Không có'
                        elif field_obj.type == 'boolean':
                            old_display = 'Có' if old_value else 'Không'
                            new_display = 'Có' if new_value else 'Không'
                        else:
                            old_display = str(old_value) if old_value is not None else 'Không có'
                            new_display = str(new_value) if new_value is not None else 'Không có'
                        
                        if old_display != new_display:
                            changes.append(f"<li><b>{field_obj.string}</b>: {old_display} → {new_display}</li>")
                    except Exception as e:
                        continue
                
                if changes:
                    user.message_post(
                        body=f"<ul>{''.join(changes)}</ul>",
                        subject="Cập nhật thông tin người dùng"
                    )
                
                return result
        
        return super(ResUsers, self).write(vals)

