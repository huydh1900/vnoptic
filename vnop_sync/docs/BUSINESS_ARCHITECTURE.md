# vnop_sync – Nghiệp vụ & Kiến trúc

## 1. Mục đích module
- Đồng bộ sản phẩm ngành kính mắt (Lens/Gọng) từ hệ thống React + Spring Boot sang Odoo 18.
- Chuẩn hoá dữ liệu kỹ thuật lens (SPH, CYL, thiết kế, vật liệu, UV, coating, v.v.) thành cấu trúc master-data trong Odoo.
- Phục vụ bán hàng, quản lý danh mục, và chuẩn bị nền tảng để sau này có thể nâng cấp sang quản lý tồn kho chi tiết theo từng specs.

## 2. Kiến trúc tổng quan

### 2.1. Luồng đồng bộ sản phẩm

1. Lấy cấu hình API từ biến môi trường (SPRING_BOOT_BASE_URL, API_LENS_ENDPOINT, API_OPTS_ENDPOINT, v.v.).
2. Lấy access token qua endpoint login.
3. Gọi API phân trang (`_fetch_paged_api`) để lấy toàn bộ dữ liệu lens/gọng (`_fetch_all_items`).
4. Preload cache dữ liệu hiện có trong Odoo (`_preload_all_data`).
5. Với mỗi record API:
   - Chuẩn bị dữ liệu cơ bản sản phẩm (`_prepare_base_vals`).
   - Chuẩn bị dữ liệu con theo loại sản phẩm:
     - Lens: `_prepare_lens_vals` → `product.lens`.
     - Gọng: `_prepare_opt_vals` → `product.opt`.
   - Ghi nhận phân loại: update (`to_update`) hoặc tạo mới (`to_create`).
6. Batch create/update `product.template`, sau đó create/update bản ghi con (`product.lens` / `product.opt`).

### 2.2. Các model chính

#### 2.2.1. Model đồng bộ – `product.sync`
- File: models/product_sync.py
- Chức năng:
  - Cấu hình/trigger việc đồng bộ (thường từ form hoặc cron).
  - Quản lý tiến độ, log, trạng thái sync.
- Các trường quan trọng:
  - `last_sync_date`, `sync_status`, `sync_log`, `total_synced`, `total_failed`, `lens_count`, `opts_count`.
- Hàm chính:
  - `_get_api_config()`: Lấy cấu hình API.
  - `_get_access_token()`: Login và lấy token.
  - `_fetch_paged_api()`, `_fetch_all_items()`: Lấy dữ liệu phân trang.
  - `_preload_all_data()`: Tạo cache cho product, category, supplier, tax, group, master data lens.
  - `_prepare_base_vals()`: Chuẩn hóa dữ liệu chung cho `product.template`.
  - `_prepare_lens_vals()`: Map dữ liệu lens từ API sang `product.lens`.
  - `_prepare_opt_vals()`: Map dữ liệu gọng từ API sang `product.opt`.
  - `_process_items()`: Batch create/update product + child.
  - `sync_products_from_springboot()`, `sync_products_limited()`, `_run_sync()`: Entry point đồng bộ.

#### 2.2.2. Model chi tiết Lens – `product.lens`
- File: models/product_lens.py
- Mục đích: Lưu thông số kỹ thuật lens theo từng product template.
- Các trường chính (đã chuẩn hoá):
  1. Công suất (Config-driven):
     - `sph_id` – Many2one `product.lens.power` (type = 'sph').
     - `cyl_id` – Many2one `product.lens.power` (type = 'cyl').
  2. Trục, ADD, Base curve, Đường kính:
     - `axis` – Integer (0–180), có validate.
     - `lens_add` – Float.
     - `base_curve` – Float.
     - `diameter` – Integer, validate khoảng hợp lệ.
  3. Thiết kế:
     - `design1_id` – Many2one `product.design` (Thiết kế 1 – legacy).
     - `design2_id` – Many2one `product.design` (Thiết kế 2 – legacy).
     - `design_id` – Many2one `product.lens.design` (thiết kế chuẩn, dùng cho sync mới).
  4. Vật liệu & chiết suất:
     - `material_id` – Many2one `product.lens.material`.
     - `index_id` – Many2one `product.lens.index` (chiết suất).
  5. Màu sắc & coating:
     - `color_int` – Char (Độ đậm màu – text từ API).
     - `mir_coating` – Char (Màu tráng gương – text từ API).
     - `uv_id` – Many2one `product.uv`.
     - `cl_hmc_id` – Many2one `product.cl` (HMC).
     - `cl_pho_id` – Many2one `product.cl` (Pho Col / Photochromic).
     - `cl_tint_id` – Many2one `product.cl` (Tint Col).
     - `coating_ids` – Many2many `product.coating` (coating layer).
  6. Liên kết:
     - `product_tmpl_id` – Many2one `product.template`.
     - `product_id` – Many2one `product.product` (chưa dùng cho stock, reserved để mở rộng).
- Có các ràng buộc/validate domain logic cơ bản (axis, diameter, base_curve, v.v.).

#### 2.2.3. Mở rộng product.template
- File: models/product_template_ext.py
- Mục đích:
  - Thêm `lens_ids` – One2many `product.lens` (quan hệ 1-n giữa product template và cấu hình lens).
  - Thêm các field custom (x_*) gắn với sản phẩm, nhóm, thương hiệu, bảo hành, v.v.

### 2.3. Views chính

#### 2.3.1. Form sản phẩm – Tabs Lens
- File: views/product_template_views.xml
- Các tab chính liên quan đến lens:

1. **"Thiết kế Lens"**
   - Thông tin: SPH, CYL, ADD, Prism, Base curve, Đường kính, Thiết kế 1, Thiết kế 2.
   - Lấy từ `lens_ids` với form/list liên kết `product.lens`.

2. **"Chất liệu Lens"**
   - Thông tin: Chiết suất (`index_id`), Vật liệu (`material_id`).
   - Dùng lại `lens_ids` nhưng group fields theo tab này.

3. **"Tích hợp Lens"**
   - Thông tin: Độ đậm màu (`color_int`), UV (`uv_id`), HMC (`cl_hmc_id`), Màu tráng gương (`mir_coating`), Pho Col (`cl_pho_id`), Tint Col (`cl_tint_id`), Coating (`coating_ids`).
   - Dùng lại `lens_ids` nhưng tập trung vào nhóm tính năng tích hợp.

#### 2.3.2. Menu cấu hình Lens (đã ẩn)
- File: views/product_lens_config_views.xml
- Trước đây có menu Config cho master data lens.
- Hiện tại đã comment/ẩn theo yêu cầu, vẫn có thể bật lại nếu cần quản trị master trực tiếp trong Odoo.

## 3. Nghiệp vụ hiện tại vs. hướng phát triển

---

### 📊 Bảng trạng thái tổng quan

| Hạng mục | Trạng thái |
|---|---|
| Đồng bộ sản phẩm lens/gọng từ Spring Boot | ✅ ĐÃ XONG |
| Cache master data (design, material, power, v.v.) | ✅ ĐÃ XONG |
| Model `product.lens` với đầy đủ fields kỹ thuật | ✅ ĐÃ XONG |
| Views sản phẩm – 3 tab Lens (Thiết kế / Chất liệu / Tích hợp) | ✅ ĐÃ XONG |
| Ẩn menu cấu hình Lens (tạm thời) | ✅ ĐÃ XONG |
| Phân tích kiến trúc tồn kho chi tiết | ✅ ĐÃ XONG |
| Chuyển sang `product.product` variants | 🟡 CHƯA LÀM |
| Quản lý tồn kho chi tiết theo từng SKU specs | 🟡 CHƯA LÀM |
| Báo cáo tồn kho chi tiết từng combination | 🟡 CHƯA LÀM |
| Migration dữ liệu `product.lens` → variants | 🟡 CHƯA LÀM |

---

### 3.1. Nghiệp vụ hiện tại ✅
- Dữ liệu lens từ Spring Boot:
  - Cho mỗi combination specs (sph, cyl, material, v.v.) → 1 record trong API.
  - Không có trường số lượng tồn kho (qty/stock) theo từng combination.
- Trong Odoo:
  - Mỗi sản phẩm lens là một `product.template`.
  - Các combination specs được lưu thành nhiều dòng `product.lens` gắn với cùng `product_tmpl_id`.
  - Tồn kho hiện tại chỉ có thể quản lý tổng theo `product.template` (type = consu), chưa quản lý tồn kho riêng cho từng combination specs.

### 3.2. Hạn chế của mô hình `product.lens` ✅ (đã phân tích xong)
- `product.lens` KHÔNG phải là `product.product` → không có stock moves/stock quant.
- Không thể:
  - Quản lý tồn kho chi tiết theo từng combination SPH/CYL/Material.
  - Bán hàng chọn đúng 1 SKU specs và trừ tồn kho riêng.
  - Báo cáo tồn kho chi tiết từng specs.
- `product.lens` hiện tại chỉ đóng vai trò **bảng thông số kỹ thuật** gắn với 1 sản phẩm chính.

### 3.3. Hướng phát triển tương lai – Sang `product.product` (variants) 🟡 CHƯA LÀM
- Mục tiêu:
  - Mỗi combination lens (SPH, CYL, Material, Index, Coating, v.v.) trở thành **1 variant `product.product`**.
  - Quản lý tồn kho, bán hàng, báo cáo theo từng variant.
- Ý tưởng kiến trúc:
  - Dùng `product.attribute` & `product.attribute.value` cho các dimension: SPH, CYL, Index, Material, v.v.
  - `product.template` là model lens tổng (vd: Essilor Crizal), các combination specs tạo thành variants.
  - Logic sync:
    - Từ API → map sang attributes/values → tạo hoặc cập nhật variants.
  - Phần `product.lens` có thể:
    - Hoặc bị thay thế dần bằng variants.
    - Hoặc giữ lại như bảng mô tả kỹ thuật bổ sung, liên kết 1-1 hoặc 1-n với variants.

## 4. Ghi chú thiết kế quan trọng

- Cache (`_preload_all_data`) được dùng mạnh để tránh query lặp lại khi sync số lượng lớn bản ghi.
- Các master data (design, material, uv, coating, colors, lens index, v.v.) được đồng bộ vào cache và tra cứu bằng key (cid, name, v.v.).
- SPH/CYL được chuẩn hoá sang float và map qua `product.lens.power` để tránh lệch định dạng giữa API và Odoo.
- Module hiện tại tập trung vào **đồng bộ master & thông số kỹ thuật**, chưa giải bài toán **stock chi tiết từng combination**. Điều này là chủ đích kiến trúc giai đoạn 1 để giảm độ phức tạp.

---

Tài liệu này dùng để giúp dev/AI mới đọc nhanh hiểu được:
- Module dùng để làm gì.
- Các model chính là gì và liên kết ra sao.
- Luồng sync dữ liệu từ Spring Boot sang Odoo.
- Hiện trạng nghiệp vụ và hướng phát triển sang `product.product` trong tương lai.
