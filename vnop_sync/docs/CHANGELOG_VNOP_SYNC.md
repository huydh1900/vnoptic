# vnop_sync – Changelog & Tiến độ

> Mục tiêu file này: lưu vết những thay đổi chính trong module `vnop_sync` để dev/AI khác nắm bắt nhanh bối cảnh và lịch sử.

---

## 📋 Bảng tổng quan tiến độ

| Hạng mục | Trạng thái |
|---|---|
| Chuẩn hoá sync & cache (product_sync.py) | ✅ ĐÃ XONG |
| Model product.lens – fields kỹ thuật & legacy | ✅ ĐÃ XONG (sẽ deprecated) |
| Đồng bộ fields mới từ API (color_int, mir_coating, v.v.) | ✅ ĐÃ XONG |
| Views sản phẩm – 3 tab Lens (Thiết kế / Chất liệu / Tích hợp) | ✅ ĐÃ XONG (sẽ thay bằng field trực tiếp) |
| Ẩn menu cấu hình Lens (tạm thời) | ✅ ĐÃ XONG |
| Phân tích kiến trúc tồn kho lens | ✅ ĐÃ XONG |
| Quyết định kiến trúc: chọn Hướng B | ✅ ĐÃ XONG (2026-02-25) |
| Tạo wizard migration lens → variant | ✅ ĐÃ XONG (nhưng sẽ thay bằng wizard lens → field) |
| **HƯỚNG B: Thêm lens specs field trực tiếp lên product.template** | 🔴 CHƯA LÀM |
| **HƯỚNG B: Refactor sync logic (specs → template field)** | 🔴 CHƯA LÀM |
| **HƯỚNG B: Cập nhật UI tabs dùng field trực tiếp** | 🔴 CHƯA LÀM |
| **HƯỚNG B: Migration dữ liệu product.lens → field trên template** | 🔴 CHƯA LÀM |
| **HƯỚNG B: Cleanup code cũ (variant helpers, product.lens)** | 🔴 CHƯA LÀM |
| Kiểm thử bán hàng, nhập kho, báo cáo tồn kho | 🔴 CHƯA LÀM |

---

## 2026-02-25 – Quyết định kiến trúc: Hướng B

### Bối cảnh

- API Spring Boot trả mỗi sản phẩm 1 CID riêng → đã là 1 SKU duy nhất.
- Hướng A (attribute → variant) gây bùng nổ variant (tích Descartes).
- Hướng C (giữ product.lens) gây dữ liệu phân tán.
- **Chọn Hướng B: lens specs là field trực tiếp trên `product.template`.**

### Những gì đã code nhưng sẽ THAY ĐỔI / LOẠI BỎ

| File/Code | Trạng thái |
|---|---|
| `_get_or_create_attribute()` | ❌ Sẽ xóa (không dùng attribute) |
| `_get_or_create_attr_value()` | ❌ Sẽ xóa |
| `_ensure_attr_line()` | ❌ Sẽ xóa |
| `_find_variant_by_attrs()` | ❌ Sẽ xóa |
| `_sync_lens_variant()` | ❌ Sẽ xóa |
| `cache['attr_ids']`, `cache['attr_val_ids']`, `cache['attr_lines']` | ❌ Sẽ xóa |
| `lens_variant_migration_wizard.py` | ❌ Sẽ thay bằng wizard dạng field migration |
| Tabs lens "(Cũ)" hiện tại | ⚠️ Tạm giữ, sẽ thay bằng tabs dùng field trực tiếp |

---

## 2026-02 – Đợt refactor Lens (giai đoạn 1) – ĐÃ XONG

### ✅ ĐÃ XONG 1 – Chuẩn hoá sync & cache
- File: `models/product_sync.py`
- Thêm `_get_api_config()`, `_fetch_paged_api()`, `_fetch_all_items()`, `_preload_all_data()`.
- Cache: products, categories, suppliers, taxes, groups, statuses, master data lens.

### ✅ ĐÃ XONG 2 – Model product.lens
- File: `models/product_lens.py`
- Fields kỹ thuật: sph_id, cyl_id, axis, lens_add, base_curve, diameter, design1_id, design2_id, material_id, index_id, uv_id, cl_hmc_id, cl_pho_id, cl_tint_id, coating_ids, color_int, mir_coating.
- **Sẽ deprecated khi Hướng B hoàn thành.**

### ✅ ĐÃ XONG 3 – Views sản phẩm – 3 tab Lens
- File: `views/product_template_views.xml`
- Tab "Thiết kế Lens", "Chất liệu Lens", "Tích hợp Lens" (hiện dùng lens_ids → product.lens).
- **Sẽ thay bằng tabs dùng field trực tiếp khi Hướng B hoàn thành.**

### ✅ ĐÃ XONG 4 – Bỏ auto-create product.lens
- File: `models/product_template_ext.py`
- Sản phẩm lens mới tạo không còn tự sinh product.lens record.

### ✅ ĐÃ XONG 5 – Migration Wizard (tạm)
- File: `wizard/lens_variant_migration_wizard.py`
- Wizard chuyển product.lens → variant (Hướng A). **Sẽ thay bằng wizard Hướng B.**

---

## 🔴 CHƯA LÀM – Giai đoạn 2: Hướng B (Field trực tiếp)

> Xem chi tiết lộ trình trong `docs/MIGRATION_ROADMAP.md`

| Bước | Công việc | File |
|------|-----------|------|
| B1 | Thêm lens_* fields lên product.template | product_template_ext.py |
| B2 | Refactor sync: specs → template vals | product_sync.py |
| B3 | Cập nhật UI tabs | product_template_views.xml |
| B4 | Migration: product.lens → template fields | wizard mới |
| B5 | Cleanup: xóa variant helpers, xóa product.lens | product_sync.py, product_lens.py |
| B6 | Test: sync, UI, tồn kho, bán hàng | manual |

---

> File này cập nhật khi: thay đổi model, luồng sync, hoặc hoàn thành bước trong lộ trình Hướng B.
