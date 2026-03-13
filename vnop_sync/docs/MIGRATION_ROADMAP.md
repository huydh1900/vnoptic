# vnop_sync – Lộ trình Migration: Hướng B

> Cập nhật: 2026-02-25
> Hướng đi: **Field specs trực tiếp trên product.template**
> Trạng thái: 🟡 ĐANG TRIỂN KHAI

---

## Tổng quan

Chuyển thông số lens từ model riêng `product.lens` sang **field trực tiếp** trên `product.template`.
Mỗi sản phẩm lens (1 CID từ API) = 1 `product.template` = 1 `product.product` (variant mặc định).
Tồn kho, bán hàng, barcode quản lý qua variant mặc định.

---

## Lộ trình chi tiết

### Bước B1: Thêm lens specs fields lên product.template
**File:** `models/product_template_ext.py`
**Trạng thái:** 🔴 CHƯA LÀM

**Công việc:**
- [ ] Thêm các field mới trên `product.template`:

```python
# ═══ LENS SPECS (trực tiếp trên template) ═══
# Thiết kế
lens_sph_id = fields.Many2one('product.lens.power', string='SPH',
    domain="[('type', '=', 'sph')]")
lens_cyl_id = fields.Many2one('product.lens.power', string='CYL',
    domain="[('type', '=', 'cyl')]")
lens_add = fields.Float('ADD', digits=(4, 2))
lens_base_curve = fields.Float('Base Curve', digits=(4, 2))
lens_diameter = fields.Integer('Đường kính')
lens_prism = fields.Char('Prism', size=50)
lens_design1_id = fields.Many2one('product.design', string='Thiết kế 1')
lens_design2_id = fields.Many2one('product.design', string='Thiết kế 2')

# Chất liệu
lens_material_id = fields.Many2one('product.lens.material', string='Vật liệu')
lens_index_id = fields.Many2one('product.lens.index', string='Chiết suất')

# Tích hợp
lens_uv_id = fields.Many2one('product.uv', string='UV')
lens_cl_hmc_id = fields.Many2one('product.cl', string='HMC')
lens_cl_pho_id = fields.Many2one('product.cl', string='Pho Col')
lens_cl_tint_id = fields.Many2one('product.cl', string='Tint Col')
lens_color_int = fields.Char('Độ đậm màu', size=50)
lens_mir_coating = fields.Char('Màu tráng gương', size=50)
lens_coating_ids = fields.Many2many('product.coating',
    'template_coating_rel', 'tmpl_id', 'coating_id', string='Coating')
```

- [ ] Giữ nguyên `lens_ids` (One2many product.lens) tạm thời cho dữ liệu cũ
- [ ] Cập nhật computed fields `_compute_lens_info` dùng field mới thay vì `lens_ids[0]`

**Kiểm tra:**
- Upgrade module, xác nhận field mới xuất hiện trong DB
- Không lỗi khi load sản phẩm hiện có

---

### Bước B2: Refactor sync logic
**File:** `models/product_sync.py`
**Trạng thái:** 🔴 CHƯA LÀM

**Công việc:**
- [ ] Sửa `_prepare_base_vals()`: thêm mapping lens specs trực tiếp vào vals

```python
# Trong _prepare_base_vals(), nếu product_type == 'lens':
vals.update({
    'lens_sph_id': get_power_id(item.get('sph'), 'sph'),
    'lens_cyl_id': get_power_id(item.get('cyl'), 'cyl'),
    'lens_add': float(item.get('lensAdd') or 0),
    'lens_base_curve': float(item.get('base') or 0),
    'lens_diameter': int(item.get('diameter') or 0),
    'lens_prism': item.get('prism', ''),
    'lens_design1_id': cache['designs'].get((item.get('design') or '').upper()),
    'lens_design2_id': ...,
    'lens_material_id': cache['lens_materials'].get(...),
    'lens_index_id': ...,
    'lens_uv_id': ...,
    'lens_cl_hmc_id': ...,
    'lens_cl_pho_id': ...,
    'lens_cl_tint_id': ...,
    'lens_color_int': item.get('colorInt', ''),
    'lens_mir_coating': item.get('mirCoating', ''),
})
```

- [ ] Xóa gọi `_sync_lens_variant()` trong `_process_batch()`
- [ ] Xóa gọi `_prepare_lens_vals()` (dùng cho product.lens cũ)
- [ ] Xóa 5 hàm variant helper: `_get_or_create_attribute`, `_get_or_create_attr_value`, `_ensure_attr_line`, `_find_variant_by_attrs`, `_sync_lens_variant`
- [ ] Xóa cache attribute: `cache['attr_ids']`, `cache['attr_val_ids']`, `cache['attr_lines']`
- [ ] `_process_batch()` cho lens: chỉ cần create/update template (specs đã nằm trong vals), KHÔNG cần child model

**Kiểm tra:**
- Chạy sync 10-20 sản phẩm lens → xác nhận dữ liệu specs nằm đúng trên template
- Xác nhận product.product variant mặc định tồn tại

---

### Bước B3: Cập nhật UI
**File:** `views/product_template_views.xml`
**Trạng thái:** 🔴 CHƯA LÀM

**Công việc:**
- [ ] Thay tabs "(Cũ)" bằng tabs mới dùng field trực tiếp:

```xml
<!-- Tab Thiết kế Lens -->
<page string="Thiết kế Lens" name="product_lens_design"
      invisible="not is_lens">
    <group>
        <group string="Công suất">
            <field name="lens_sph_id" options="{'no_create': True}"/>
            <field name="lens_cyl_id" options="{'no_create': True}"/>
            <field name="lens_add"/>
            <field name="lens_prism"/>
            <field name="lens_base_curve"/>
            <field name="lens_diameter"/>
        </group>
        <group string="Thiết kế">
            <field name="lens_design1_id" options="{'no_create': True}"/>
            <field name="lens_design2_id" options="{'no_create': True}"/>
        </group>
    </group>
</page>

<!-- Tab Chất liệu Lens -->
<page string="Chất liệu Lens" name="product_lens_material"
      invisible="not is_lens">
    <group>
        <group string="Chất liệu">
            <field name="lens_index_id" options="{'no_create': True}"/>
            <field name="lens_material_id" options="{'no_create': True}"/>
        </group>
    </group>
</page>

<!-- Tab Tích hợp Lens -->
<page string="Tích hợp Lens" name="product_lens_integration"
      invisible="not is_lens">
    <group>
        <group string="Tích hợp">
            <field name="lens_uv_id" options="{'no_create': True}"/>
            <field name="lens_cl_hmc_id" options="{'no_create': True}"/>
            <field name="lens_cl_pho_id" options="{'no_create': True}"/>
            <field name="lens_cl_tint_id" options="{'no_create': True}"/>
            <field name="lens_color_int"/>
            <field name="lens_mir_coating"/>
            <field name="lens_coating_ids" widget="many2many_tags"
                   options="{'no_create': True}"/>
        </group>
    </group>
</page>
```

- [ ] Xóa các tabs "(Cũ)" hiện tại (khi đã không còn product.lens data)
- [ ] Thêm field lens specs vào tree view common (nếu muốn filter/search)

**Kiểm tra:**
- Vào Tồn kho → Sản phẩm → Chi tiết → thấy 3 tab đúng khi sản phẩm là lens
- Tab ẩn khi sản phẩm là gọng/phụ kiện
- Dữ liệu hiển thị đúng sau sync

---

### Bước B4: Migration dữ liệu cũ (nếu có)
**File:** Wizard mới hoặc script
**Trạng thái:** 🔴 CHƯA LÀM

**Công việc:**
- [ ] Viết wizard/script đọc mỗi `product.lens` record → copy specs sang field tương ứng trên `product.template`:

```python
for lens in self.env['product.lens'].search([]):
    tmpl = lens.product_tmpl_id
    if tmpl:
        tmpl.write({
            'lens_sph_id': lens.sph_id.id,
            'lens_cyl_id': lens.cyl_id.id,
            'lens_add': lens.lens_add,
            'lens_base_curve': lens.base_curve,
            'lens_diameter': lens.diameter,
            'lens_prism': lens.prism,
            'lens_design1_id': lens.design1_id.id,
            'lens_design2_id': lens.design2_id.id,
            'lens_material_id': lens.material_id.id,
            'lens_index_id': lens.index_id.id,
            'lens_uv_id': lens.uv_id.id,
            'lens_cl_hmc_id': lens.cl_hmc_id.id,
            'lens_cl_pho_id': lens.cl_pho_id.id,
            'lens_cl_tint_id': lens.cl_tint_id.id,
            'lens_color_int': lens.color_int,
            'lens_mir_coating': lens.mir_coating,
            'lens_coating_ids': [(6, 0, lens.coating_ids.ids)],
        })
```

**Kiểm tra:**
- Chạy wizard → xác nhận dữ liệu product.lens đã copy sang template
- So sánh dữ liệu trước/sau migration

---

### Bước B5: Cleanup code cũ
**Trạng thái:** 🔴 CHƯA LÀM

**Công việc:**
- [ ] Xóa 5 hàm variant helper trong `product_sync.py`
- [ ] Xóa `_prepare_lens_vals()` (không còn dùng)
- [ ] Xóa `lens_variant_migration_wizard.py` + views + menu
- [ ] Xóa tabs "(Cũ)" trong `product_template_views.xml`
- [ ] Đánh dấu `product.lens` là deprecated (có thể xóa sau khi production stable)
- [ ] Xóa `lens_ids` khỏi `product_template_ext.py` (nếu đã migrate xong data)
- [ ] Cleanup `_preload_all_data()`: xóa cache attr_ids/attr_val_ids/attr_lines
- [ ] Update `product_excel_import.py`: dùng field trực tiếp thay vì tạo product.lens

**Kiểm tra:**
- Module upgrade không lỗi
- Sync vẫn hoạt động đúng
- UI hiển thị đúng

---

### Bước B6: Kiểm thử tổng thể
**Trạng thái:** 🔴 CHƯA LÀM

**Công việc:**
- [ ] Sync 100+ sản phẩm lens từ API → xác nhận specs đúng trên template
- [ ] Vào form sản phẩm → 3 tabs hiện đúng thông tin
- [ ] Tạo đơn bán hàng → chọn sản phẩm lens → xác nhận giá/SKU đúng
- [ ] Nhập kho → xác nhận tồn kho tăng đúng cho sản phẩm đó
- [ ] Xuất kho → xác nhận tồn kho giảm đúng
- [ ] Báo cáo tồn kho → xác nhận hiển thị đúng từng sản phẩm
- [ ] Filter/search sản phẩm theo SPH, CYL, Material... → hoạt động đúng

---

## Thứ tự thực hiện

```
B1 (fields) → B2 (sync) → B3 (UI) → B4 (migrate data) → B5 (cleanup) → B6 (test)
     ↓             ↓           ↓             ↓                ↓              ↓
  1-2 giờ      2-3 giờ     1-2 giờ       30 phút          1-2 giờ        2-3 giờ
```

**Tổng ước lượng: ~8-12 giờ làm việc**

---

## Nguyên tắc

1. **Không xóa product.lens ngay** – giữ lại cho đến khi production stable
2. **Backward compatible** – tabs "(Cũ)" vẫn hoạt động song song trong giai đoạn chuyển tiếp
3. **Incremental** – mỗi bước có thể test độc lập, không cần hoàn thành tất cả cùng lúc
4. **Sync luôn ưu tiên field mới** – ngay sau bước B2, sync mới sẽ dùng field trực tiếp

---

> File này là lộ trình chính thức cho migration Hướng B. Cập nhật trạng thái khi hoàn thành từng bước.
