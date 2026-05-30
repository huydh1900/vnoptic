# -*- coding: utf-8 -*-
"""Post-init hook: thay thế 63 tỉnh/thành cũ của Việt Nam bằng 34 đơn vị
hành chính sau sáp nhập (hiệu lực 01/07/2025)."""

import json
import logging
import os
import re

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


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
            _logger.warning("Không thể xóa tỉnh cũ, có thể còn tham chiếu FK", exc_info=True)

    # 2) Tạo / cập nhật các tỉnh mới theo danh sách sau sáp nhập
    all_names = [name for name, _code in VN_PROVINCES_AFTER_MERGER]
    existing_states = State.search([
        ("country_id", "=", vn_country.id),
        ("name", "in", all_names),
    ])
    existing_map = {s.name: s for s in existing_states}
    for name, code in VN_PROVINCES_AFTER_MERGER:
        existing = existing_map.get(name)
        if existing:
            if existing.code != code:
                existing.code = code
        else:
            State.create({
                "country_id": vn_country.id,
                "name": name,
                "code": code,
            })

    _seed_wards(env, vn_country)


_PROVINCE_PREFIX_RE = re.compile(
    r'^(thành\s+phố\s+|tỉnh\s+|tp\.?\s*)', flags=re.IGNORECASE
)


def _normalize(name):
    return _PROVINCE_PREFIX_RE.sub('', (name or '').strip()).strip().lower()


def _seed_wards(env, vn_country):
    """Load phường/xã từ data/vn_wards.json (nguồn provinces.open-api.vn v2,
    cập nhật sau sáp nhập 2025-07-01) vào model vnop.ward.
    """
    data_path = os.path.join(os.path.dirname(__file__), 'data', 'vn_wards.json')
    if not os.path.isfile(data_path):
        _logger.warning("vn_wards.json không tồn tại tại %s", data_path)
        return
    with open(data_path, encoding='utf-8') as f:
        provinces = json.load(f)

    State = env['res.country.state']
    states = State.search([('country_id', '=', vn_country.id)])
    # Map state theo tên đã chuẩn hóa
    state_by_name = {_normalize(s.name): s for s in states}
    # Alias đặc biệt
    hcm = state_by_name.get('hồ chí minh')
    if not hcm:
        # Odoo lưu "TP. Hồ Chí Minh" -> sau strip prefix còn "hồ chí minh"
        hcm = state_by_name.get('tp. hồ chí minh') or state_by_name.get('tp hồ chí minh')
        if hcm:
            state_by_name['hồ chí minh'] = hcm

    Ward = env['vnop.ward']
    existing = {w.code: w for w in Ward.search([])}

    rows = []
    skipped_provinces = set()
    for p in provinces:
        key = _normalize(p.get('name', ''))
        state = state_by_name.get(key)
        if not state:
            skipped_provinces.add(p.get('name'))
            continue
        for w in p.get('wards') or []:
            code = str(w.get('code'))
            if code in existing:
                continue
            rows.append({
                'name': w.get('name'),
                'code': code,
                'state_id': state.id,
            })
    if rows:
        Ward.create(rows)
        _logger.info("vnop_partner: seeded %s phường/xã", len(rows))
    if skipped_provinces:
        _logger.warning("vnop_partner: không match được tỉnh: %s", skipped_provinces)