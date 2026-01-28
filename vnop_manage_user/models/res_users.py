from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    def write(self, vals):
        # Danh sách các field KHÔNG theo dõi (vì lý do bảo mật hoặc không cần thiết)
        IGNORED_FIELDS = ['password', 'message_ids', 'message_follower_ids']
        
        # Theo dõi tất cả các field có trong vals, trừ các field bị ignore và các field ảo
        # Tuy nhiên, nếu có field ảo liên quan đến nhóm (sel_groups, in_group), ta CẦN theo dõi 'groups_id'
        
        has_virtual_group_fields = any(k.startswith(('sel_groups_', 'in_group_')) for k in vals)
        
        fields_to_check = [
            f for f in vals 
            if f not in IGNORED_FIELDS 
            and not f.startswith(('sel_groups_', 'in_group_'))
        ]
        
        # Nếu có thay đổi nhóm qua giao diện (ảo), bắt buộc theo dõi groups_id
        if has_virtual_group_fields and 'groups_id' not in fields_to_check:
            fields_to_check.append('groups_id')
            
        if not fields_to_check:
            return super(ResUsers, self).write(vals)

        # 1. Lưu giá trị cũ trước khi ghi đè
        old_values = {}
        for user in self:
            old_values[user.id] = {}
            for field in fields_to_check:
                if field == 'groups_id':
                    # Với Many2many, lưu danh sách ID nhóm để so sánh diff
                    old_values[user.id][field] = user.groups_id.ids
                else:
                    old_values[user.id][field] = user[field]

        # 2. Gọi hàm gốc để thực hiện ghi dữ liệu
        result = super(ResUsers, self).write(vals)

        # 3. So sánh và ghi log
        LogModel = self.env['user.change.log']
        # Dùng sudo() nếu người dùng hiện tại không có quyền ghi log (tuy nhiên log do system ghi thì thường ok)
        # Ở đây ta lấy user hiện tại (env.user)
        current_user = self.env.user

        for user in self:
            for field in fields_to_check:
                old_val = old_values[user.id].get(field)
                # Xử lý riêng cho trường Many2many (groups_id)
                if field == 'groups_id':
                    new_group_ids = set(user.groups_id.ids)
                    old_group_ids = set(old_values[user.id].get(field, []))
                    added = new_group_ids - old_group_ids
                    removed = old_group_ids - new_group_ids

                    Group = self.env['res.groups']
                    # Log từng nhóm được thêm
                    for gid in added:
                        group_name = Group.browse(gid).display_name
                        LogModel.create({
                            'user_id': user.id,
                            'changed_by': current_user.id,
                            'field_name': 'Groups',
                            'old_value': '',
                            'new_value': f'Thêm: {group_name}',
                        })
                    # Log từng nhóm bị bỏ
                    for gid in removed:
                        group_name = Group.browse(gid).display_name
                        LogModel.create({
                            'user_id': user.id,
                            'changed_by': current_user.id,
                            'field_name': 'Groups',
                            'old_value': '',
                            'new_value': f'Bỏ: {group_name}',
                        })
                    # Không cần xử lý new_val cho trường này nữa
                    continue
                # Các field cơ bản và relation khác
                new_val_raw = user[field]
                if old_val != new_val_raw:
                    def format_val(val, field_name):
                        if not val:
                            return ""
                        ftype = self._fields[field_name].type
                        if ftype == 'many2one':
                            return val.display_name or ''
                        elif ftype in ['many2many', 'one2many']:
                            return ', '.join(val.mapped('display_name'))
                        elif ftype == 'boolean':
                            return 'True' if val else 'False'
                        elif ftype == 'selection':
                            return dict(self._fields[field_name].selection).get(val, val)
                        else:
                            return str(val)

                    old_val_str = format_val(old_val, field)
                    new_val = format_val(new_val_raw, field)
                    if old_val_str == new_val:
                        continue  # Không log nếu giống nhau sau format
                    # Xử lý hiển thị active True/False cho đẹp (tuỳ chọn)
                    if field == 'active':
                        old_val_str = 'Active' if old_val_str == 'True' else 'Archived'
                        new_val = 'Active' if new_val == 'True' else 'Archived'
                    field_label = self._fields[field].string or field
                    LogModel.create({
                        'user_id': user.id,
                        'changed_by': current_user.id,
                        'field_name': field_label,
                        'old_value': old_val_str or '',
                        'new_value': new_val or '',
                    })

        return result
