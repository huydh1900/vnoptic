# HƯỚNG DẪN BÁN LẺ TẠI QUẦY (POS Mắt Kính)

> Đối tượng: nhân viên thu ngân tại cửa hàng VNOptic.
> Phần mềm: Odoo 18 + module **VNOptic POS Bán Lẻ Mắt Kính**.

---

## MỤC LỤC

1. [Chuẩn bị trước khi bán](#1-chuẩn-bị-trước-khi-bán)
2. [Cấu hình sản phẩm cần đơn kính (Rx)](#2-cấu-hình-sản-phẩm-cần-đơn-kính-rx)
3. [Mở phiên bán hàng (Open Session)](#3-mở-phiên-bán-hàng-open-session)
4. [Quy trình bán hàng tại quầy](#4-quy-trình-bán-hàng-tại-quầy)
5. [Khuyến mại & voucher](#5-khuyến-mại--voucher)
6. [Đóng phiên cuối ca](#6-đóng-phiên-cuối-ca)
7. [Xử lý tình huống thường gặp](#7-xử-lý-tình-huống-thường-gặp)

---

## 1. CHUẨN BỊ TRƯỚC KHI BÁN

### 1.1. Đăng nhập hệ thống
- Mở trình duyệt → vào địa chỉ phần mềm (vd: `http://posmk.vnoptic.vn`)
- Đăng nhập bằng tài khoản nhân viên
- Chọn database (nếu có nhiều)

### 1.2. Vào ứng dụng POS
- Từ màn hình chính → click menu **"POS Mắt kính"** ở thanh trên
- Chọn **"Cấu hình điểm bán"** → thấy quầy "**Cửa hàng Mắt kính - Quầy chính**"

---

## 2. CẤU HÌNH SẢN PHẨM CẦN ĐƠN KÍNH (Rx)

> **Việc này chỉ làm 1 lần khi tạo sản phẩm tròng kính mới**, do quản lý cửa hàng/admin thực hiện.

**Mục đích:** đánh dấu sản phẩm nào là **tròng kính** để khi nhân viên bấm vào ở POS, hệ thống tự bật popup nhập độ.

### Cách làm

1. Vào menu **Inventory** (hoặc **Sales**) → **Products**
2. Mở sản phẩm tròng (vd: "Tròng Crizal 1.56 UV")
3. Vào tab **"Point of Sale"**
4. Tích chọn **"Tròng kính (cần đơn Rx)"**
5. Bấm **Save**

> 💡 **Mẹo:** Gọng kính, kính mát, phụ kiện thì **không tích** ô này — chúng bán bình thường, không cần độ.

| Loại sản phẩm | Tích `is_optical_lens`? | Có popup Rx? |
|---|---|---|
| Gọng kính | ❌ Không | Không |
| Tròng kính (làm sẵn / cắt theo Rx) | ✅ Có | Có |
| Kính mát | ❌ Không | Không |
| Kính áp tròng | ❌ Không | Không |
| Phụ kiện (hộp, khăn lau) | ❌ Không | Không |
| Dịch vụ đo mắt | ❌ Không | Không |

---

## 3. MỞ PHIÊN BÁN HÀNG (OPEN SESSION)

> Mỗi ca làm việc cần **mở 1 phiên** ở đầu ca và **đóng phiên** ở cuối ca.

### Bước 1: Vào quầy POS
- Menu **POS Mắt kính** → **Cấu hình điểm bán** → click **"Cửa hàng Mắt kính - Quầy chính"**
- Bấm nút **"Open Register"** (Mở quầy) màu xanh

### Bước 2: Đếm tiền mặt đầu ca
- Hệ thống hỏi "Tiền mặt đầu ca": nhập số tiền thực tế trong két
- Bấm **"Open Register"** xác nhận → vào màn hình bán hàng

---

## 4. QUY TRÌNH BÁN HÀNG TẠI QUẦY

### 🟢 BƯỚC 1: Chọn khách hàng

- Bấm icon 👤 **Customer** ở góc trên màn hình POS
- 3 trường hợp:
  - **Khách cũ:** Gõ số ĐT hoặc tên → chọn từ danh sách
  - **Khách mới:** Bấm **"Create"** → nhập tên + số ĐT → Save
  - **Khách vãng lai (không lấy thông tin):** bỏ qua bước này

> 💡 Lấy số ĐT giúp tích lũy lịch sử mua, áp dụng KM khách thân thiết sau này.

### 🟢 BƯỚC 2: Khách có cần đo mắt không?

#### TH1: Khách **đã có** đơn kính (Rx) sẵn từ lần đo trước
→ Bỏ qua, sang BƯỚC 3.

#### TH2: Khách **cần đo mắt** tại cửa hàng
→ Hướng dẫn khách qua phòng đo. Sau khi có đơn kính trên giấy:
- Quay lại POS → tiếp tục BƯỚC 3
- Khi click sản phẩm tròng (BƯỚC 4), popup Rx sẽ tự bật → nhập số đo

### 🟢 BƯỚC 3: Chọn GỌNG kính

- Trên màn hình bán hàng, danh mục **"Gọng kính"** ở thanh bên trái
- Cách thêm gọng vào giỏ:
  - **Cách 1 - Quét barcode:** Quét mã vạch trên gọng → tự thêm vào giỏ
  - **Cách 2 - Click trực tiếp:** Click ảnh gọng trong danh mục → thêm vào giỏ
  - **Cách 3 - Tìm kiếm:** Gõ tên gọng vào ô search

> ✅ Sau khi click, dòng gọng xuất hiện bên trái cart với giá tiền.

### 🟢 BƯỚC 4: Chọn TRÒNG kính (popup Rx tự bật)

1. Click danh mục **"Tròng kính"**
2. Chọn loại tròng phù hợp (vd: Crizal 1.56 UV)
3. **Popup "Nhập đơn kính" tự bật** ⚡

#### Giao diện popup Rx

```
┌─────────────────────────────────────────────────────┐
│  Nhập đơn kính - Tròng Crizal 1.56 UV              │
├─────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐        │
│  │  OD - Mắt phải   │  │  OS - Mắt trái   │        │
│  │                  │  │                  │        │
│  │ SPH:  [-][-2.50][+] SPH:  [-][-2.25][+]        │
│  │ CYL:  [-][-0.75][+] CYL:  [-][-0.50][+]        │
│  │ AXIS: [-][180  ][+] AXIS: [-][175  ][+]        │
│  │ ADD:  [-][ 0.00][+] ADD:  [-][ 0.00][+]        │
│  └──────────────────┘  └──────────────────┘        │
│                                                     │
│  PD - Khoảng cách đồng tử (mm): [-][62.0][+]       │
│  Ghi chú: [Cắt vát cạnh, lắp gọng nhanh        ]   │
│                                                     │
│             [ Bỏ qua ]  [ Xác nhận đơn kính ]      │
└─────────────────────────────────────────────────────┘
```

#### Cách nhập độ

- **Nút `-` và `+`**: bấm để giảm/tăng từng nấc 0.25 (cho SPH/CYL/ADD), 1° (cho AXIS), 0.5mm (cho PD)
- **Hoặc bấm vào ô số** → gõ tay → Enter
- **Mặc định** AXIS = 0, ADD = 0 (không cần đổi nếu đơn kính của khách không có)

#### Diễn giải các trường

| Trường | Ý nghĩa | Dải hợp lệ |
|---|---|---|
| **SPH** | Độ cầu (cận / viễn) | -20.00 đến +20.00 |
| **CYL** | Độ trụ (loạn) | -10.00 đến +10.00 |
| **AXIS** | Trục loạn (độ °) | 0 đến 180 |
| **ADD** | Số cộng (cho người đa tròng) | 0 đến +4.00 |
| **PD** | Khoảng cách đồng tử (mm) | 40 đến 80 |
| **Ghi chú** | VD: "cắt vát", "lắp gấp" | Tự do |

#### Hoàn tất

- Bấm **"Xác nhận đơn kính"** → tròng được thêm vào cart
- Trong cart, dưới dòng tròng sẽ thấy **badge xanh** hiển thị tóm tắt:
  ```
  👁 Rx: OD: -2.50/-0.75x180 +0.00 | OS: -2.25/-0.50x175 +0.00 | PD 62.0 | Cắt vát cạnh
  ```

> ⚠️ Nếu bấm **"Bỏ qua"** → tròng vẫn được thêm nhưng KHÔNG có Rx (chỉ dùng cho trường hợp khách mua tròng làm sẵn không cần đo).

### 🟢 BƯỚC 5: Thêm sản phẩm khác (nếu có)

- Hộp đựng kính, khăn lau, dung dịch áp tròng… → click bình thường
- Nếu khách muốn 2 đôi kính → lặp lại BƯỚC 3-4 cho đôi thứ 2

### 🟢 BƯỚC 6: Kiểm tra giỏ + áp khuyến mại tự động

- Hệ thống **TỰ ĐỘNG** áp các KM thỏa điều kiện:
  - "KM Khai trương" — giảm 20% toàn đơn
  - "Mua từ 3 SP giảm 15%" — đếm số sản phẩm
  - "Black Friday giảm 30% SP rẻ nhất"
- Nếu có code voucher → bấm nút **"Reward"** ở dưới cart → nhập mã → áp

> 💡 Cashier không cần biết logic — hệ thống tự áp đúng. Nếu thấy thiếu, gọi quản lý.

### 🟢 BƯỚC 7: Thanh toán

1. Bấm nút **"Payment"** màu xanh ở góc dưới cart
2. Chọn phương thức thanh toán (có thể chia nhiều phương thức cho 1 đơn):

| Phương thức | Khi nào dùng |
|---|---|
| **Tiền mặt** | Khách trả tiền mặt |
| **Quẹt thẻ (POS Bank)** | Khách quẹt thẻ ATM/Visa qua máy POS ngân hàng |
| **Chuyển khoản ngân hàng** | Khách chuyển khoản, NV xác nhận đã nhận |
| **Ví MoMo / VNPay / ZaloPay** | Khách quét QR thanh toán điện tử |
| **Voucher / Phiếu quà tặng** | Khách dùng voucher có giá trị |

3. Nhập số tiền nhận (hệ thống tự gợi ý mệnh giá: 1k, 2k, 5k, 10k, 20k, 50k, 100k, 200k, 500k)
4. Bấm **"Validate"** xác nhận

### 🟢 BƯỚC 8: In bill + giao kính

- Hệ thống tự in bill (nếu có máy in) — bill **có in cả Rx** dưới dòng tròng để khách đối chiếu khi nhận
- Bấm **"New Order"** chuẩn bị đơn tiếp theo

#### TH cắt theo Rx (không có sẵn ở kho):
- In thêm **phiếu giao kính** với hẹn ngày nhận (3-5 ngày tùy loại tròng)
- Đưa khách số phiếu để khi nhận quay lại tra cứu

---

## 5. KHUYẾN MẠI & VOUCHER

### Các KM đang chạy mặc định

| Tên chương trình | Loại | Áp dụng |
|---|---|---|
| KM Khai trương | Tự động | Giảm 20% toàn đơn |
| Ưu đãi Mua nhiều | Tự động | Mua từ 3 SP giảm 15% |
| Khuyến mãi Black Friday | Tự động | Giảm 30% SP rẻ nhất khi mua từ 2 SP |
| Mã MATKINH2026 | Mã code | Nhập mã → giảm 100k (đơn từ 500k) |
| Mã STUDENT10 | Mã code | Sinh viên → giảm 10% toàn đơn |

### Cách áp KM bằng mã code
1. Sau khi thêm hết sản phẩm, bấm nút **"Reward"** ở dưới cart
2. Nhập mã (vd: `MATKINH2026`)
3. Hệ thống kiểm tra điều kiện → áp giảm giá tự động

> ⚠️ Mỗi đơn chỉ áp được 1 mã code. KM tự động vẫn được áp song song.

---

## 6. ĐÓNG PHIÊN CUỐI CA

1. Bấm icon **menu** (3 gạch) ở góc trên-trái màn hình POS
2. Chọn **"Close Register"** (Đóng quầy)
3. Hệ thống hiện bảng thống kê:
   - Tổng tiền mặt theo hệ thống
   - Tổng từng phương thức (thẻ, MoMo, VNPay…)
4. **Đếm tiền mặt thực tế** → nhập vào ô "Tiền mặt cuối ca"
5. Nếu **chênh lệch** → ghi lý do vào "Ghi chú" (vd: thiếu 50k đã mượn của thu ngân khác)
6. Bấm **"Close Register"** xác nhận
7. Hệ thống in báo cáo cuối ca → giao cho quản lý

---

## 7. XỬ LÝ TÌNH HUỐNG THƯỜNG GẶP

### ❓ Khách đổi ý đơn kính giữa chừng (đã nhập Rx sai)

- Click vào dòng tròng đã thêm trong cart
- Bấm nút 🗑 **xóa dòng**
- Click lại sản phẩm tròng → popup Rx bật lại → nhập đúng

### ❓ Cùng 1 mẫu tròng nhưng 2 mắt khác nhau? Hay khách mua 2 đôi?

- Click sản phẩm 2 lần → mỗi lần popup Rx riêng → 2 dòng riêng (KHÔNG bị gộp)
- Hệ thống nhận biết 2 đôi kính có Rx khác nhau → giữ riêng tự động

### ❓ Khách trả lại hàng

- Bấm nút **"Refund"** trong menu POS
- Chọn đơn cũ → chọn dòng cần trả
- Hệ thống tạo đơn refund → nhập tiền hoàn → in phiếu trả

### ❓ Khách hỏi tra cứu lịch sử mua

- Bấm icon **"Orders"** (Đơn hàng) ở góc trên
- Tab **"Receipt"** → tìm theo số ĐT khách → xem đơn cũ + Rx cũ
- Có thể in lại Rx cho khách

### ❓ Lỡ tay tắt popup Rx mà chưa nhập

→ Popup là **không bắt buộc**: tròng vẫn thêm vào cart bình thường, nhưng không có Rx. Cách xử lý:

1. Vào **backend** (Settings) → **POS Mắt kính** → **Đơn hàng** → tìm phiên hiện tại
2. Mở dòng đơn → nhập Rx vào tab "Đơn kính (Rx)" → Save

> 💡 Nếu chưa thanh toán, đơn giản hơn: xóa dòng tròng → click lại → popup bật lại.

### ❓ Lỗi không in được bill

- Kiểm tra máy in bật, kết nối USB ổn
- Bấm icon **menu** → **"Print Receipt"** trên đơn vừa tạo
- Nếu vẫn lỗi → xuất bill PDF qua email khách

---

## 📞 LIÊN HỆ HỖ TRỢ

| Vấn đề | Liên hệ |
|---|---|
| Lỗi phần mềm | IT VNOptic — `it@vnoptic.vn` |
| Lỗi máy POS / máy in | Quản lý cửa hàng |
| Câu hỏi nghiệp vụ | Trưởng ca |

---

## 🎯 CHECKLIST NV THU NGÂN ĐẦU CA

- [ ] Đã đăng nhập hệ thống
- [ ] Đã mở phiên POS + đếm tiền mặt đầu ca
- [ ] Máy in bill OK (in thử 1 bill mẫu)
- [ ] Máy quẹt thẻ ngân hàng kết nối OK
- [ ] Có sẵn voucher giấy/coupon nếu có chương trình tặng

## 🎯 CHECKLIST NV THU NGÂN CUỐI CA

- [ ] Hoàn tất tất cả đơn dở dang (không còn đơn draft)
- [ ] Đã đóng phiên POS
- [ ] Đếm tiền mặt khớp hệ thống (hoặc đã ghi chú chênh lệch)
- [ ] In + nộp báo cáo cuối ca cho quản lý
- [ ] Bàn giao ca cho NV ca sau (nếu có)
