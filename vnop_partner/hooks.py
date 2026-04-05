# -*- coding: utf-8 -*-
"""Post-init hook: thay thế 63 tỉnh/thành cũ của Việt Nam bằng 34 đơn vị
hành chính sau sáp nhập (hiệu lực 01/07/2025)."""

from odoo import SUPERUSER_ID, api


# 6 thành phố trực thuộc trung ương + 28 tỉnh = 34 đơn vị
VN_PROVINCES_AFTER_MERGER = [
    # (name, code)
    # 6 thành phố trực thuộc trung ương
    ("Hà Nội", "VN-HN"),
    ("Hải Phòng", "VN-HP"),
    ("Huế", "VN-HUE"),
    ("Đà Nẵng", "VN-DN"),
    ("TP. Hồ Chí Minh", "VN-SG"),
    ("Cần Thơ", "VN-CT"),
    # 28 tỉnh
    ("Lai Châu", "VN-01"),
    ("Điện Biên", "VN-71"),
    ("Sơn La", "VN-05"),
    ("Lạng Sơn", "VN-09"),
    ("Quảng Ninh", "VN-13"),
    ("Cao Bằng", "VN-04"),
    ("Tuyên Quang", "VN-07"),
    ("Lào Cai", "VN-02"),
    ("Thái Nguyên", "VN-69"),
    ("Phú Thọ", "VN-68"),
    ("Bắc Ninh", "VN-56"),
    ("Hưng Yên", "VN-66"),
    ("Ninh Bình", "VN-18"),
    ("Thanh Hóa", "VN-21"),
    ("Nghệ An", "VN-22"),
    ("Hà Tĩnh", "VN-23"),
    ("Quảng Trị", "VN-25"),
    ("Quảng Ngãi", "VN-29"),
    ("Gia Lai", "VN-30"),
    ("Đắk Lắk", "VN-33"),
    ("Khánh Hòa", "VN-34"),
    ("Lâm Đồng", "VN-35"),
    ("Đồng Nai", "VN-39"),
    ("Tây Ninh", "VN-37"),
    ("Đồng Tháp", "VN-45"),
    ("Vĩnh Long", "VN-49"),
    ("An Giang", "VN-44"),
    ("Cà Mau", "VN-59"),
]

# Các tỉnh cần giữ nguyên (không xoá) vì đã có trong danh sách mới
_KEEP_NAMES = {name for name, _code in VN_PROVINCES_AFTER_MERGER}


def post_init_hook(env):
    """Xoá các tỉnh VN cũ không còn tồn tại sau sáp nhập và tạo các tỉnh mới.

    - Set `state_id = False` trên mọi res.partner đang trỏ tới tỉnh bị xoá
      để tránh vi phạm ràng buộc khoá ngoại.
    - Unlink các tỉnh cũ không còn trong danh sách mới.
    - Tạo/cập nhật các tỉnh mới theo danh sách hiện hành.
    """
    # Hỗ trợ cả 2 signature: Odoo <=17 truyền (cr, registry); Odoo 18+ truyền env
    if not isinstance(env, api.Environment):
        cr = env
        env = api.Environment(cr, SUPERUSER_ID, {})

    vn_country = env.ref("base.vn", raise_if_not_found=False)
    if not vn_country:
        return

    State = env["res.country.state"]

    # 1) Xoá tỉnh cũ không còn trong danh sách mới
    old_states = State.search([
        ("country_id", "=", vn_country.id),
        ("name", "not in", list(_KEEP_NAMES)),
    ])
    if old_states:
        # Huỷ tham chiếu từ res.partner để tránh FK error
        partners = env["res.partner"].search([("state_id", "in", old_states.ids)])
        if partners:
            partners.write({"state_id": False})
        try:
            old_states.unlink()
        except Exception:
            # Nếu còn model khác tham chiếu, bỏ qua để không chặn install
            pass

    # 2) Tạo / cập nhật các tỉnh mới theo danh sách sau sáp nhập
    for name, code in VN_PROVINCES_AFTER_MERGER:
        existing = State.search([
            ("country_id", "=", vn_country.id),
            ("name", "=", name),
        ], limit=1)
        if existing:
            if existing.code != code:
                existing.code = code
        else:
            State.create({
                "country_id": vn_country.id,
                "name": name,
                "code": code,
            })