# vnop_sync – Nghiệp vụ & Kiến trúc

> Cập nhật: 2026-02-25 | Hướng đi: **Hướng B – Field trực tiếp trên product.template**

---

## 1. Mục đích module

- Đồng bộ sản phẩm ngành kính mắt (Lens/Gọng) từ hệ thống React + Spring Boot sang Odoo 18.
- Chuẩn hoá dữ liệu kỹ thuật lens (SPH, CYL, thiết kế, vật liệu, UV, coating, v.v.).
- Quản lý tồn kho, bán hàng, barcode, báo cáo cho từng sản phẩm (SKU).

---

## 2. Quyết định kiến trúc (2026-02-25)

### 2.1. Bối cảnh

API Spring Boot trả về mỗi sản phẩm lens với **CID riêng** (mã sản phẩm duy nhất).
Mỗi CID đã bao gồm đầy đủ thông số (SPH, CYL, ADD, Material, Index...).
→ **1 CID = 1 product.template = 1 product.product (variant mặc định)**.

### 2.2. Ba hướng đã phân tích

| Hướng | Mô tả | Vấn đề |
|-------|-------|--------|
| **A** | Dùng `product.attribute` → sinh variant tổ hợp | Bùng nổ variant (50 SPH × 20 CYL × 5 Material = 5000+ variant/template) |
| **B** ✅ | Field specs trực tiếp trên `product.template` | Đơn giản, mỗi CID = 1 template + 1 variant mặc định, tồn kho per SKU |
| **C** | Giữ `product.lens` + liên kết tồn kho qua variant mặc định | Dữ liệu phân tán, phức tạp không cần thiết |

### 2.3. Kết luận: Chọn Hướng B

**Lý do:**
1. API đã trả 1 CID duy nhất mỗi sản phẩm → đã có SKU tự nhiên
2. Không cần nhóm nhiều combination dưới 1 template
3. Specs là field trực tiếp → filter, search, group trong list view dễ dàng
4. Tồn kho tự nhiên qua `product.product` mặc định, không cần attribute
5. Không bùng nổ variant
6. UI gọn gàng, hiểu trực quan

---

## 3. Kiến trúc mục tiêu (Hướng B)

### 3.1. Model chính

```
product.template (1 template = 1 sản phẩm, default_code = CID)
  ├── Thông tin chung: name, categ_id, brand_id, warranty_id, country_id, seller_ids
  ├── Giá: list_price, standard_price, x_ws_price, x_or_price
  ├── Lens specs (field trực tiếp):
  │   ├── lens_sph_id      → Many2one product.lens.power (type=sph)
  │   ├── lens_cyl_id      → Many2one product.lens.power (type=cyl)
  │   ├── lens_add         → Float
  │   ├── lens_base_curve  → Float
  │   ├── lens_diameter    → Integer
  │   ├── lens_prism       → Char
  │   ├── lens_design1_id  → Many2one product.design
  │   ├── lens_design2_id  → Many2one product.design
  │   ├── lens_material_id → Many2one product.lens.material
  │   ├── lens_index_id    → Many2one product.lens.index
  │   ├── lens_uv_id       → Many2one product.uv
  │   ├── lens_cl_hmc_id   → Many2one product.cl
  │   ├── lens_cl_pho_id   → Many2one product.cl
  │   ├── lens_cl_tint_id  → Many2one product.cl
  │   ├── lens_color_int   → Char (Độ đậm màu)
  │   ├── lens_mir_coating → Char (Màu tráng gương)
  │   └── lens_coating_ids → Many2many product.coating
  └── product.product (variant mặc định – 1 duy nhất)
       ├── SKU / barcode
       └── stock.quant (tồn kho)
```

### 3.2. Model bổ trợ (giữ nguyên)

| Model | Mục đích |
|-------|----------|
| `product.lens.power` | Giá trị SPH/CYL (VD: -1.00, +2.50) |
| `product.lens.material` | Vật liệu tròng (CR39, Polycarbonate...) |
| `product.lens.index` | Chiết suất (1.50, 1.56, 1.60...) |
| `product.design` | Thiết kế (Single Vision, Progressive...) |
| `product.uv` | UV Protection |
| `product.cl` | Color (HMC, Photochromic, Tint) |
| `product.coating` | Coating layers |
| `product.brand` | Thương hiệu |
| `product.warranty` | Bảo hành |
| `product.country` | Xuất xứ |
| `product.opt` | Thông số gọng kính (giữ nguyên) |

### 3.3. Model sẽ deprecated

| Model | Lý do |
|-------|-------|
| `product.lens` | Thay bằng field trực tiếp trên `product.template`. Giữ lại tạm để tham khảo dữ liệu cũ, xóa sau khi migrate xong. |

---

## 4. Luồng đồng bộ (sau khi refactor)

```
1. Lấy token từ Spring Boot API
2. Fetch dữ liệu phân trang (lens/gọng)
3. Preload cache (products, categories, suppliers, master data)
4. Với mỗi record API:
   a. _prepare_base_vals() → tạo vals product.template (bao gồm specs trực tiếp)
   b. Nếu lens: specs (SPH, CYL, ADD...) đi thẳng vào vals template
   c. Nếu gọng: _prepare_opt_vals() → product.opt
5. Batch create/update product.template
6. Odoo tự sinh 1 product.product (variant mặc định) cho mỗi template
7. Tồn kho, bán hàng, barcode → thao tác trên product.product variant mặc định
```

---

## 5. Views mục tiêu (sau khi refactor)

### 5.1. Form sản phẩm – Tabs Lens

> Dữ liệu lấy trực tiếp từ field trên `product.template`, KHÔNG qua `product.lens`.

| Tab | Nội dung |
|-----|----------|
| **Thiết kế Lens** | SPH, CYL, ADD, Prism, Base curve, Đường kính, Thiết kế 1, Thiết kế 2 |
| **Chất liệu Lens** | Chiết suất, Vật liệu |
| **Tích hợp Lens** | UV, Độ đậm màu, Màu tráng gương, HMC, Pho Col, Tint Col, Coating |

- Chỉ hiển thị khi `is_lens = True` (categ_id.code == '06')
- Có thể filter, search, group trong tree view theo SPH, CYL, Material...

### 5.2. Tabs Gọng (giữ nguyên)
- Vẫn dùng `product.opt` qua `opt_ids`

---

## 6. Ghi chú thiết kế quan trọng

- Cache (`_preload_all_data`) vẫn dùng mạnh để tránh query lặp khi sync số lượng lớn.
- Không dùng `product.attribute` cho lens → tránh bùng nổ variant.
- Field prefix `lens_` để phân biệt với field gốc Odoo.
- `product.lens` giữ lại tạm, tabs "(Cũ)" hiện khi còn data, ẩn khi đã migrate xong.
- Tab "Thuộc tính & biến thể" không cần dùng cho lens (chỉ 1 variant mặc định).

---

> Tài liệu này giúp dev/AI mới hiểu nhanh module, kiến trúc, và lý do thiết kế.
