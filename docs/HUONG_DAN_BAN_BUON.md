# HƯỚNG DẪN BÁN BUÔN (Wholesale)

> Đối tượng: nhân viên kinh doanh / sale phụ trách đại lý của VNOptic.
> Phần mềm: Odoo 18 + module **VNOptic Sale Channel** + **VNOptic Promotion**.

---

## MỤC LỤC

1. [Tổng quan luồng bán buôn](#1-tổng-quan-luồng-bán-buôn)
2. [Quản lý đại lý / khách buôn](#2-quản-lý-đại-lý--khách-buôn)
3. [Quản lý bảng giá bán buôn](#3-quản-lý-bảng-giá-bán-buôn)
4. [Tạo báo giá → đơn hàng](#4-tạo-báo-giá--đơn-hàng)
5. [Đặc thù: tròng cắt theo Rx cho đại lý](#5-đặc-thù-tròng-cắt-theo-rx-cho-đại-lý)
6. [Khuyến mại bán buôn](#6-khuyến-mại-bán-buôn)
7. [Giao hàng → hóa đơn → công nợ](#7-giao-hàng--hóa-đơn--công-nợ)
8. [Báo cáo & xuất Excel](#8-báo-cáo--xuất-excel)
9. [Xử lý tình huống thường gặp](#9-xử-lý-tình-huống-thường-gặp)

---

## 1. TỔNG QUAN LUỒNG BÁN BUÔN

```
[1] Tạo / chọn đại lý (channel_type = wholesale)
        ↓
[2] Tạo Báo giá (Quotation) — tự động lấy bảng giá bán buôn
        ↓
[3] Gửi báo giá cho đại lý qua Email / PRO-FORMA Invoice
        ↓
[4] Đại lý đồng ý → Confirm thành Đơn hàng (Sale Order)
        ↓
[5] Hệ thống tự sinh phiếu xuất kho (Delivery)
        ↓
[6] Giao hàng + xác nhận đại lý đã nhận
        ↓
[7] Tạo hóa đơn → push HĐĐT
        ↓
[8] Theo dõi công nợ → thu tiền
```

> 🎯 **Khác biệt với bán lẻ POS:**
> - Bán buôn: tạo SO trên backend, có duyệt, có giao hàng nhiều ngày, có công nợ
> - Bán lẻ: bán trực tiếp tại POS, thanh toán + giao kính trong ngày

---

## 2. QUẢN LÝ ĐẠI LÝ / KHÁCH BUÔN

### 2.1. Vào danh mục đại lý

- Menu **"Bán buôn"** ở thanh chính → **"Khách hàng"**
- Danh sách đã được lọc tự động: chỉ hiện khách có `channel_type = Bán buôn`

### 2.2. Tạo đại lý mới

1. Bấm **"New"** (góc trên trái)
2. Nhập thông tin bắt buộc:
   - **Tên** (vd: "Cửa hàng Kính thuốc Hà Đông")
   - **Số ĐT** (hotline cửa hàng)
   - **Địa chỉ** đầy đủ (Tỉnh / Huyện / Xã / Số nhà)
3. Tab **Sales & Purchases**:
   - **Salesperson**: NV phụ trách đại lý
   - **Payment Terms**: điều khoản thanh toán (vd: 30 ngày)
4. **Channel** (kênh bán) → mặc định đã set **"Bán buôn"** ✓
5. Bấm **Save**

> 💡 **Quy ước phân nhóm:**
> - **Khách "quan hệ"**: 63 cửa hàng kính thuốc tỉnh — chính sách đơn giản, ổn định
> - **Khách "thương mại"**: công ty / cá nhân kinh doanh — chính sách đa dạng hơn
>
> Có thể dùng **Tags** để phân nhóm (vd: tag "khach-quan-he", "khach-thuong-mai") để filter báo cáo.

### 2.3. Cập nhật hạn mức công nợ

- Mở form đại lý → tab **"Sales & Purchases"**
- Field **"Credit Limit"**: nhập trần công nợ (vd: 50.000.000đ)
- Field **"Payment Terms"**: số ngày được nợ
- Save

> ⚠️ Hệ thống sẽ **cảnh báo** khi tạo SO khiến công nợ vượt trần (chưa chặn cứng — Phase 2 sẽ thêm).

---

## 3. QUẢN LÝ BẢNG GIÁ BÁN BUÔN

### 3.1. Bảng giá có sẵn

| Bảng giá | Channel | Mô tả |
|---|---|---|
| **Bảng giá bán buôn** | Wholesale | Mặc định cho đại lý — giảm 10-20% giá niêm yết theo số lượng |
| **Bảng giá bán lẻ** | Retail | Cho khách lẻ POS |

### 3.2. Quy tắc giảm giá theo số lượng (đã cấu hình sẵn)

| Số lượng đặt | Giảm giá |
|---|---|
| 1-9 SP | 10% |
| 10-49 SP | 15% |
| Từ 50 SP | 20% |

### 3.3. Tạo bảng giá riêng cho đại lý đặc biệt

> Dùng khi đại lý có chính sách khác biệt (vd: cam kết doanh số cao, hợp đồng đặc biệt).

1. Menu **Bán buôn** → **Sản phẩm** → **Bảng giá**
2. Bấm **"New"**
3. Nhập:
   - **Tên** (vd: "Bảng giá Đại lý ABC")
   - **Channel**: Bán buôn
   - **Tab Price Rules** → thêm các dòng giá đặc biệt
4. Save
5. Mở form đại lý → tab **Sales & Purchases** → field **"Pricelist"** → chọn bảng giá vừa tạo
6. Save → từ giờ mọi SO của đại lý này tự dùng bảng giá riêng

> 🔒 **Bí mật giá**: bảng giá không public lên web, chỉ user có quyền xem mới thấy.

---

## 4. TẠO BÁO GIÁ → ĐƠN HÀNG

### 4.1. Tạo báo giá (Quotation)

1. Menu **Bán buôn** → **Đơn hàng** → **Báo giá**
2. Bấm **"New"**
3. **Customer**: chọn đại lý (chỉ list ra khách có channel = Bán buôn ✓)
4. **Channel**: tự điền **"Bán buôn"** (read-only) ✓
5. **Pricelist**: tự điền theo cấu hình của đại lý ✓
6. Tab **Order Lines** — 3 cách thêm sản phẩm:

#### Cách 1: Thêm thủ công từng sản phẩm
- Bấm **"Add a product"** → chọn SP → nhập số lượng

#### Cách 2: Tải template Excel rồi import
- Bấm nút **"Tải template mẫu"** ở trên Order Lines → tải file Excel có sẵn cột chuẩn:
  - `default_code` (Mã SP)
  - `product_uom_qty` (Số lượng)
  - `price_unit` (Đơn giá)
  - `taxes` (Thuế: 5%, 8%, 10%)
- Điền dữ liệu vào file
- Bấm **"Import Excel"** → upload file → Kiểm thử → Import

> 💡 Phù hợp khi đại lý gửi danh sách 50+ SKU qua email/Zalo.

#### Cách 3: Copy từ đơn hàng cũ
- Mở SO cũ của đại lý → bấm **"Duplicate"** → sửa lại số lượng → confirm

### 4.2. Cảnh báo tồn kho tự động

- Khi nhập đủ sản phẩm, hệ thống **tự kiểm tra tồn kho**
- Nếu thiếu hàng → notification màu vàng góc trên-phải:
  ```
  ⚠️ Cảnh báo tồn kho không đủ
  • Gọng RB3025: cần 50, tồn 30
  • Tròng Crizal: cần 20, tồn 5
  ```
- Cách xử lý:
  - Giảm số lượng cho khớp tồn HOẶC
  - Đặt thêm hàng từ NCC (qua module mua hàng) HOẶC
  - Báo đại lý chia làm 2 đợt giao

### 4.3. Gửi báo giá cho đại lý

Có 2 nút ở header của Quotation:

| Nút | Tác dụng |
|---|---|
| **Send by Email** | Gửi báo giá PDF qua email tới đại lý |
| **Send PRO-FORMA Invoice** | Gửi hóa đơn pro-forma (có giá trị tham khảo, không thuế) |

> ⚠️ Bán **lẻ** thì 2 nút này tự ẩn (vì khách lẻ không cần gửi báo giá qua email).

### 4.4. Confirm thành đơn hàng

- Khi đại lý đồng ý → quay lại Quotation → bấm **"Confirm"** (nút xanh)
- State chuyển từ **Draft → Sale**
- Hệ thống tự sinh:
  - **1 Picking** (phiếu xuất kho) — đợi giao
  - **Số đơn** chính thức (vd: `S00001`)
- Số tiền thể hiện cả **bằng số** và **bằng chữ tiếng Việt** trên báo giá

---

## 5. ĐẶC THÙ: TRÒNG CẮT THEO Rx CHO ĐẠI LÝ

> Khi đại lý đặt **tròng cắt theo đơn kính** của khách cuối (KH của đại lý đã đo mắt), cần lưu **Rx** lên dòng SO để xưởng VNOF biết cắt độ nào.

### 5.1. Bật cột Rx trên đơn hàng

Mặc định các cột Rx **bị ẩn** để đỡ rối. Bật khi cần:

1. Trong form Sale Order → tab **Order Lines**
2. Bấm icon **⚙️ (settings)** góc phải đầu list
3. Tích các cột muốn hiển thị:
   - ☑ **Có Rx** (báo dòng nào đã có Rx)
   - ☑ **OD-SPH**, **OD-CYL**, **OD-AXIS**, **OD-ADD**
   - ☑ **OS-SPH**, **OS-CYL**, **OS-AXIS**, **OS-ADD**
   - ☑ **PD**
   - ☑ **Ghi chú Rx**

### 5.2. Nhập Rx vào dòng

- Cột **OD/OS-SPH/CYL...** đã hiện → nhập trực tiếp số đo từ đơn kính giấy
- Cột **PD**: khoảng cách đồng tử (mm)
- Cột **Ghi chú Rx**: ghi yêu cầu đặc biệt (vd: "cắt vát cạnh", "lắp gọng RB3025 sẵn")
- Cột **Có Rx** sẽ tự tích ✓ khi có ít nhất 1 trường được nhập

> 💡 Mỗi đôi tròng cắt theo Rx = **1 dòng SO riêng** (qty=1). Đừng gộp 2 đôi khác Rx vào 1 dòng.

### 5.3. Ví dụ thực tế

Đại lý "Kính thuốc Hà Đông" gửi 1 đơn:
- 50 đôi gọng RB3025 (hàng có sẵn) — **không cần Rx**
- 1 đôi tròng Crizal cắt theo đơn của KH Trần Thị B:
  - OD: -3.00 / -1.00 x 90 / +0.00
  - OS: -3.25 / -0.75 x 85 / +0.00
  - PD: 64.0
  - Ghi chú: "Đơn KH Trần Thị B - giao trong 3 ngày"

→ SO sẽ có **2 dòng**: dòng 1 (gọng, qty=50, không Rx) và dòng 2 (tròng, qty=1, có đầy đủ Rx).

---

## 6. KHUYẾN MẠI BÁN BUÔN

### 6.1. KM tự động đang chạy (channel = Wholesale)

| Tên | Điều kiện | Lợi ích |
|---|---|---|
| **Ưu đãi Khách buôn (đơn từ 5 triệu)** | Đơn ≥ 5.000.000đ | Giảm 25% toàn đơn |
| **KM Khai trương** (all channels) | Mọi đơn | Giảm 20% toàn đơn |
| **Black Friday** (all channels) | Mua từ 2 SP | Giảm 30% SP rẻ nhất |

> 🎯 Hệ thống **tự áp** khi đủ điều kiện. NV không cần can thiệp.

### 6.2. KM theo bảng giá (đã setup sẵn)

Bảng giá bán buôn có sẵn 3 nấc giảm theo số lượng:
- Mua 1-9: giảm 10%
- Mua 10-49: giảm 15%
- Mua từ 50: giảm 20%

> Đây là KM **trên đơn giá** (thay đổi giá bán cơ sở), khác với loyalty (giảm trên tổng đơn).

### 6.3. Áp KM thủ công (mã code)

Khi đại lý có mã giảm giá đặc biệt (vd: tham gia hội chợ):
1. Trong Sale Order → bấm nút **"Reward"** (nếu hiện)
2. Nhập mã code → áp dụng

---

## 7. GIAO HÀNG → HÓA ĐƠN → CÔNG NỢ

### 7.1. Xuất kho giao hàng

- Sau khi confirm SO → mở **smart button "Delivery"** trên form SO
- Vào phiếu picking → bấm **"Validate"** xác nhận đã giao
- Có thể chia làm nhiều lần xuất nếu giao theo đợt

### 7.2. Tạo hóa đơn

- Quay lại SO → bấm **"Create Invoice"**
- Chọn loại hóa đơn:
  - **Regular invoice** (HĐĐT chính thức)
  - **Down payment** (HĐ tạm ứng — khi đại lý ứng trước)
- Bấm **"Create and View Invoice"**
- Trên Invoice → bấm **"Confirm"** → push HĐĐT qua connector (VNPT/Viettel)

### 7.3. Theo dõi công nợ

- Menu **Invoicing** (Kế toán) → **Customer Invoices**
- Filter theo đại lý → xem các HĐ chưa thanh toán
- Báo cáo **"Aged Receivable"** — xem tuổi nợ (30/60/90 ngày)

### 7.4. Thu tiền

- Mở Invoice chưa thanh toán → bấm **"Pay"**
- Chọn:
  - **Journal**: Tiền mặt / Ngân hàng
  - **Amount**: số tiền nhận (có thể nhận một phần)
  - **Date**: ngày nhận
- Bấm **"Create Payment"** → hoàn tất

---

## 8. BÁO CÁO & XUẤT EXCEL

### 8.1. Báo cáo cốt lõi (có sẵn)

| Báo cáo | Đường dẫn |
|---|---|
| Bảng kê đơn bán theo khách | Bán buôn → Đơn hàng → filter + group by Customer |
| Bảng kê đơn bán theo mặt hàng | Bán buôn → Đơn hàng → group by Product |
| Tuổi nợ phải thu | Invoicing → Reporting → Aged Receivable |
| Doanh thu theo NV | Bán buôn → Đơn hàng → group by Salesperson |

### 8.2. Filter & search nhanh

- Trên list Sale Order, ô search góc trên có sẵn 2 filter:
  - **"Bán buôn"** — chỉ hiện đơn channel = wholesale
  - **"Bán lẻ"** — chỉ hiện đơn channel = retail
- Search text → chỉ tìm theo **mã đơn** (vd: `S00001`), không lan man (đã giới hạn để tránh nhầm)

### 8.3. Xuất Excel

- Trên list view → bấm icon **"Export"** (góc trên)
- Chọn cột → tải xuống .xlsx

---

## 9. XỬ LÝ TÌNH HUỐNG THƯỜNG GẶP

### ❓ Đại lý báo "đơn sai số lượng"

- Mở SO ở state `sale` → state này **đã lock**
- Cần sửa: bấm **"Set to Quotation"** (nút vàng) → quay lại draft → sửa → Confirm lại

> ⚠️ Nếu đã giao hàng + tạo HĐ rồi mà sai → tạo **Credit Note** (hoàn trả) thay vì sửa SO.

### ❓ Đại lý đặt 1 SP nhưng cần 2 mức giá khác nhau

- Tạo **2 dòng riêng**, mỗi dòng nhập đơn giá tay (không lấy từ pricelist)
- Vd: 30 cái × 100k + 20 cái × 90k

### ❓ Cần cảnh báo khi đại lý vượt hạn mức công nợ

- Đảm bảo đã setup `credit_limit` trên form đại lý (xem mục 2.3)
- Khi tạo SO → form sẽ hiển thị warning ở góc nếu công nợ + SO vượt trần
- Phase 1: chỉ cảnh báo. Phase 2 sẽ chặn cứng.

### ❓ Sale tạo SO bị "phá form" (nhầm dropdown)

- Hệ thống đã khoá:
  - **Customer** chỉ hiện khách buôn (không nhầm sang khách lẻ)
  - **Pricelist** read-only (không sửa tay được, bảo vệ chính sách giá)

### ❓ Đại lý gửi đơn 200 dòng qua email

- Dùng tính năng **Import Excel** (mục 4.1 cách 2)
- Tải template → đại lý điền → mình import → gọn

### ❓ Đơn cắt theo Rx, đại lý gửi sai Rx

- Mở SO → tab Order Lines → bật cột Rx → sửa lại số đo trên dòng tương ứng
- Save → xưởng VNOF nhận update qua phiếu picking

---

## 📞 LIÊN HỆ HỖ TRỢ

| Vấn đề | Liên hệ |
|---|---|
| Lỗi phần mềm | IT VNOptic — `it@vnoptic.vn` |
| Câu hỏi chính sách giá | Trưởng phòng kinh doanh |
| Câu hỏi công nợ / kế toán | Phòng Tài chính |
| Lỗi HĐĐT | NCC HĐĐT (VNPT / Viettel) |

---

## 🎯 CHECKLIST SALE NHẬN ĐƠN MỚI TỪ ĐẠI LÝ

- [ ] Đại lý đã có trong hệ thống chưa? Nếu chưa → tạo mới (mục 2.2)
- [ ] Đại lý có pricelist riêng / dùng pricelist chuẩn?
- [ ] Số lượng tồn kho đủ không? (xem cảnh báo tồn)
- [ ] Có dòng nào cần Rx không? Nếu có → bật cột Rx + nhập đầy đủ
- [ ] Công nợ hiện tại + đơn này có vượt trần không?
- [ ] Đã gửi báo giá cho đại lý xác nhận?
- [ ] Confirm SO → đẩy phiếu xuất kho
- [ ] Tạo Invoice + push HĐĐT
- [ ] Theo dõi giao hàng + thu nợ

---

## 📋 PHỤ LỤC: SƠ ĐỒ STATE CỦA SO

```
        ┌──────────┐  Confirm    ┌─────────┐  Send Quote   ┌──────────┐
        │  Draft   │ ─────────►  │  Sent   │ ────────────► │   Sale   │
        │ (Báo giá)│             │ (Đã gửi)│               │ (Đơn HĐ) │
        └────┬─────┘             └────┬────┘               └────┬─────┘
             │                        │                         │
             ▼                        ▼                         ▼
        Cancel                   Cancel                    Cancel
                                                          + Refund / CR

   * Bán lẻ POS: Draft → Sale (bỏ qua "Sent" để giao dịch nhanh)
   * Bán buôn:   Draft → Sent → Sale (có gửi báo giá email)
```

---

> 📅 **Phiên bản tài liệu:** v1.0 — 2026-05-01
> 📌 **Phù hợp cho:** Module `vnop_sale_channel` v18.0.1.0 + `vnop_promotion` v18.0.1.0
