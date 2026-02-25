# vnop_sync – Changelog & Tiến độ

> Mục tiêu file này: lưu vết những thay đổi chính trong module `vnop_sync` để dev/AI khác nắm bắt nhanh bối cảnh và lịch sử.

---

## 📋 Bảng tổng quan tiến độ

| Hạng mục | Trạng thái |
|---|---|
| Chuẩn hoá sync & cache (product_sync.py) | ✅ ĐÃ XONG |
| Model product.lens – fields kỹ thuật & legacy | ✅ ĐÃ XONG |
| Đồng bộ fields mới từ API (color_int, mir_coating, v.v.) | ✅ ĐÃ XONG |
| Views sản phẩm – 3 tab Lens (Thiết kế / Chất liệu / Tích hợp) | ✅ ĐÃ XONG |
| Ẩn menu cấu hình Lens (tạm thời) | ✅ ĐÃ XONG |
| Phân tích kiến trúc tồn kho lens | ✅ ĐÃ XONG |
| Chuyển sang `product.product` (variants) | ✅ ĐÃ XONG |
| Refactor sync logic sang tạo/update variants | ✅ ĐÃ XONG |
| Migration dữ liệu từ product.lens sang variants | 🟡 CHƯA LÀM (cần chạy thủ công nếu có data cũ) |
| Kiểm thử bán hàng, nhập kho, báo cáo tồn kho chi tiết | 🟡 CHƯA LÀM |

---

## 2026-02 – Đợt refactor Lens (giai đoạn 1)

### ✅ ĐÃ XONG 1 – Chuẩn hoá sync & cache
- File: `models/product_sync.py`
- Thêm `_get_api_config()` đọc biến môi trường, gom cấu hình API Spring Boot.
- Bổ sung `_fetch_paged_api()` + `_fetch_all_items()` để hỗ trợ phân trang (page/size).
- Thiết lập hệ thống cache `_preload_all_data()`:
  - `products`: map `default_code` → `product.template.id`.
  - `categories`, `suppliers`, `taxes`, `groups`, `statuses`.
  - Master data lens: `lens_powers` (SPH/CYL), `lens_designs`, `lens_materials`.
  - Child records: `lens_records`, `opt_records` để update/create tối ưu.
- Chuẩn hoá `_prepare_base_vals()` tạo bộ `vals` chuẩn cho `product.template`.
- Tách riêng xử lý lens/opt qua `_prepare_lens_vals()` và `_prepare_opt_vals()`.

### ✅ ĐÃ XONG 2 – Chuẩn hoá model chi tiết Lens – `product.lens`
- File: `models/product_lens.py`
- Thêm Many2one cho cấu hình công suất: `sph_id`, `cyl_id` → `product.lens.power`.
- Liên kết với `product.template` qua `product_tmpl_id`.
- Bổ sung các trường kỹ thuật và legacy:
  - Thiết kế: `design1_id`, `design2_id`, `design_id`.
  - Vật liệu, chiết suất: `material_id`, `index_id`.
  - Tích hợp/màu sắc/coating: `uv_id`, `cl_hmc_id`, `cl_pho_id`, `cl_tint_id`, `coating_ids`.
  - Text từ API: `color_int` (Độ đậm màu), `mir_coating` (Màu tráng gương).
- Sửa imports: `from odoo.exceptions import ValidationError` và `_` từ `odoo`.

### ✅ ĐÃ XONG 3 – Đồng bộ fields mới từ API
- File: `models/product_sync.py` → hàm `_prepare_lens_vals()`
- Map các trường: `len_add`, `diameter`, `base_curve`, `axis`, `prism`, `prism_base`, `color_int`, `mir_coating`.
- Chuẩn hoá mapping design/material bằng tên lower-case vào cache.

### ✅ ĐÃ XONG 4 – Views sản phẩm – 3 tab Lens
- File: `views/product_template_views.xml`
- **Tab "Thiết kế Lens"**: SPH, CYL, ADD, Prism, Base curve, Axis, Đường kính, Thiết kế 1, Thiết kế 2.
- **Tab "Chất liệu Lens"**: Chiết suất (`index_id`), Vật liệu (`material_id`).
- **Tab "Tích hợp Lens"**: `color_int`, `uv_id`, `cl_hmc_id`, `mir_coating`, `cl_pho_id`, `cl_tint_id`, `coating_ids`.
- Sửa/xóa các field XML thừa nằm ngoài `<page>` gây lỗi view.

### ✅ ĐÃ XONG 5 – Ẩn menu cấu hình Lens (tạm thời)
- File: `views/product_lens_config_views.xml`
- Comment/ẩn các menu cấu hình master-data lens (chủ yếu sync từ hệ thống ngoài).
- Có thể bật lại khi cần quản trị master trực tiếp trên Odoo.

---

## 2026-02 – Phân tích kiến trúc tồn kho

### ✅ ĐÃ XONG – Phân tích & kết luận
- API `/api/xnk/lens` hiện tại chỉ trả về specs kỹ thuật, không có trường `qty`/`stock` cho từng combination.
- `product.lens` không phải `product.product` → không có stock quant/move riêng → không quản lý tồn kho chi tiết từng specs.
- Đội ngũ (anh HuyO) xác nhận cần chuyển sang `product.product` variants để quản lý tồn kho, bán hàng, báo cáo chi tiết.

---

## 🟡 CHƯA LÀM – Giai đoạn 2: Chuyển sang product.product (variants)

> Phần code đã hoàn thành, còn lại là kiểm thử và migration data cũ.

| Công việc | Trạng thái |
|---|---|
| Phân tích API, xác định dimensions cần làm attributes (SPH, CYL, Material, Index, Coating...) | ✅ ĐÃ XONG |
| Thiết kế mapping: API field → product.attribute / product.attribute.value | ✅ ĐÃ XONG |
| Refactor `_prepare_lens_vals()` để tạo/update variants product.product | ✅ ĐÃ XONG |
| Viết script migration dữ liệu cũ từ product.lens → variants | 🟡 CHƯA LÀM (nếu có data cũ) |
| Cập nhật views, bán hàng, báo cáo theo variants | 🟡 CHƯA LÀM |
| Kiểm thử quy trình bán hàng, nhập kho, báo cáo tồn kho chi tiết | 🟡 CHƯA LÀM |
| Cập nhật tài liệu sau khi hoàn thành giai đoạn 2 | 🟡 CHƯA LÀM |

---

## ✅ ĐÃ XONG – Giai đoạn 2: Chuyển sang product.product variants (2026-02)

### Thay đổi chính trong `models/product_sync.py`

**4 hàm helper mới:**
- `_get_or_create_attribute(cache, attr_name)` – Tạo/lấy `product.attribute` (SPH, CYL, Vật liệu, Thiết kế) theo tên, dùng cache tránh query lặp.
- `_get_or_create_attr_value(cache, attr_id, value_name)` – Tạo/lấy `product.attribute.value` (ví dụ: -1.00, -0.50, CR39) theo (attr_id, value_name).
- `_ensure_attr_line(cache, tmpl_id, attr_id, value_id)` – Đảm bảo `product.template.attribute.line` tồn tại trên template và có chứa value. Khi thêm value mới, Odoo tự tạo thêm variant tương ứng.
- `_find_variant_by_attrs(tmpl_id, attr_value_ids)` – Tìm `product.product` variant khớp đúng tập attribute value IDs (so sánh theo set).

**Hàm chính mới:**
- `_sync_lens_variant(tmpl_id, item, cache)` – Thay thế logic tạo `product.lens`. Với mỗi bản ghi lens từ API: tạo attributes (SPH, CYL, Vật liệu, Thiết kế) → tạo values → gán vào attribute line của template → tìm/trả về variant `product.product` có tồn kho riêng.

**Cache mở rộng trong `_preload_all_data`:**
- `cache['attr_ids']` – Map tên attribute (lower) → attribute.id
- `cache['attr_val_ids']` – Map (attr_id, value_lower) → attribute_value.id
- `cache['attr_lines']` – Map (tmpl_id, attr_id) → {id, value_ids}

**`_process_batch` refactored:**
- Với `product_type = 'lens'`: KHÔNG tạo `product.lens` nữa, thay bằng gọi `_sync_lens_variant` sau khi template được create/update.
- Với `product_type = 'opt'`: giữ nguyên child model approach.
- `_run_sync`: bỏ `'product.lens'` khỏi tham số gọi `_process_batch` cho lens.

**Kết quả:**
- Mỗi combination (SPH, CYL, Vật liệu, Thiết kế) từ API → 1 `product.product` variant.
- Variant hiện diện trong tab "Attributes & Variants" chuẩn Odoo trên form sản phẩm.
- Tồn kho có thể quản lý riêng từng SKU (từng combination specs).

---

> File này cập nhật khi: thêm field mới, thay đổi model/luồng sync, hoặc bắt đầu triển khai giai đoạn 2.
