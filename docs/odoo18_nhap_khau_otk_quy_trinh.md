# Đề xuất kiến trúc Odoo 18 cho nghiệp vụ nhập khẩu nhiều PO, nhiều đợt OTK

## 1) Mục tiêu thiết kế
- Quản lý 1 **Hợp đồng nhập khẩu** có nhiều **Đơn mua (PO)** và nhiều sản phẩm.
- 1 **Lịch giao hàng** theo hợp đồng có thể phát sinh nhiều lần **OTK/kiểm định chất lượng** theo thực tế.
- Hàng **đạt** nhập kho đạt để bán; hàng **lỗi** vào kho lỗi.
- Tính được **giá vốn thực tế theo từng đợt hàng về** để có thể bán ngay cả khi mới về một phần.
- Theo dõi rõ trạng thái **đã nhận / còn thiếu** trên từng dòng PO; khi tái sử dụng đơn cho hợp đồng sau chỉ đề xuất phần còn lại.

## 2) Nguyên tắc tối ưu: tận dụng base Odoo tối đa
Ưu tiên dùng các chức năng chuẩn trước, chỉ custom phần liên kết nghiệp vụ đặc thù:

1. **Purchase**: chuẩn quản lý PO, nhận hàng từng phần (partial receipt), backorder.
2. **Inventory**: chuẩn dùng incoming picking + quality check + putaway/location.
3. **Quality**: chuẩn tạo Quality Control Point và Quality Checks theo incoming shipment.
4. **Landed Costs**: chuẩn phân bổ chi phí nhập khẩu (freight, insurance, duty, local charges) vào tồn kho.
5. **Valuation**: dùng **AVCO** (khuyến nghị cho bài toán nhận hàng nhiều đợt, giá về biến động).

Custom tối thiểu:
- Model “hợp đồng nhập khẩu” để gom nhiều PO.
- Rule đề xuất số lượng còn lại khi kéo PO/dòng PO sang hợp đồng/lịch mới.
- Báo cáo điều phối nghiệp vụ hợp đồng – PO – đợt nhận – OTK – tồn đạt/lỗi.

## 3) Mô hình dữ liệu đề xuất
### 3.1 Model chính (custom nhẹ)
- `import.contract` (Hợp đồng nhập khẩu)
  - Số hợp đồng, NCC, Incoterm, currency, ETD/ETA, chi phí dự kiến.
  - One2many đến `purchase.order` (thêm field `import_contract_id` trên PO).
  - One2many đến lịch giao (`import.delivery.schedule`).

- `import.delivery.schedule` (Lịch giao theo hợp đồng)
  - Thuộc 1 hợp đồng.
  - Gắn nhiều incoming picking thực tế (nhiều đợt hàng về).

### 3.2 Dữ liệu chuẩn Odoo tái sử dụng
- `purchase.order.line`
  - Dùng sẵn `product_qty`, `qty_received`, `qty_invoiced`.
  - Bổ sung computed/stored `qty_remaining = product_qty - qty_received`.

- `stock.picking` + `stock.move`
  - Mỗi đợt hàng về là 1 incoming picking.
  - Partial receipt tự sinh backorder chuẩn Odoo.

- `quality.check`
  - Kiểm đạt/lỗi theo lot/serial hoặc theo quantity.
  - Kết quả check là đầu vào cho split move đạt/lỗi.

## 4) Quy trình vận hành end-to-end
## Bước A: Lập hợp đồng và PO
1. Tạo `import.contract`.
2. Tạo nhiều PO thuộc cùng hợp đồng (`import_contract_id`).
3. Confirm PO để sinh incoming shipment chuẩn.

## Bước B: Hàng về từng phần
1. Mỗi lần hàng về: validate incoming picking theo số lượng thực nhận.
2. Nếu nhận thiếu (ví dụ 3/4):
   - Odoo tự backorder phần còn lại.
   - `qty_received` trên PO line cập nhật đúng (75%).
   - `qty_remaining` hiển thị phần thiếu (25%).

## Bước C: OTK (nhiều lần trong cùng đợt hoặc nhiều đợt)
1. Quality checks được tạo theo cấu hình QCP (operation type incoming).
2. Sau kiểm tra:
   - Hàng đạt: move sang **Kho đạt** (location đạt).
   - Hàng lỗi: move sang **Kho lỗi** (location lỗi / quality hold / scrap tùy chính sách).
3. Dùng route nội bộ + quality locations để tự động hóa điều chuyển.

## Bước D: Tính giá vốn sau khi hàng về
1. Product category dùng **Automated Valuation + AVCO**.
2. Mỗi lần receipt hợp lệ cập nhật giá vốn bình quân tức thời.
3. Khi phát sinh chi phí nhập khẩu, tạo **Landed Cost** phân bổ vào các receipt tương ứng (theo trọng lượng/giá trị/số lượng).
4. Giá vốn bán hàng (COGS) phản ánh đúng theo lượng đã nhận + landed cost đã phân bổ đến thời điểm bán.

## 5) Đáp ứng yêu cầu “hợp đồng sau chỉ hiện phần còn lại”
Thiết kế wizard “Chọn PO nguồn” cho hợp đồng/lịch mới:
- Nguồn dữ liệu: các `purchase.order.line` còn mở (`qty_remaining > 0`).
- Cột hiển thị: PO, sản phẩm, đặt mua, đã nhận, còn lại, ETA, hợp đồng cũ.
- Khi chọn dòng, mặc định số lượng đề xuất = `qty_remaining`.
- Không cho chọn vượt `qty_remaining` (constraint).

Như vậy với ví dụ “đã về 3/4”, lần sau hệ thống chỉ đề xuất 1/4 còn thiếu.

## 6) Kiến trúc kho đạt/lỗi
- Tạo 2 location rõ ràng:
  - `WH/Stock/OK` (hàng đạt, available for sale).
  - `WH/Stock/NG` (hàng lỗi, blocked).
- Quy tắc:
  - Chỉ `WH/Stock/OK` được đưa vào reservation cho SO.
  - `WH/Stock/NG` không khả dụng bán.
- Nếu có quy trình đổi trả NCC: thêm flow RTV từ kho lỗi.

## 7) KPI & báo cáo cần có
1. Theo hợp đồng: tổng đặt, đã nhận, còn thiếu, tỷ lệ đạt lỗi.
2. Theo PO line: `ordered / received / remaining`.
3. Theo đợt hàng về: planned vs actual, pass/fail rate.
4. Theo giá vốn: before/after landed cost, sai lệch theo đợt.

## 8) Lộ trình triển khai khuyến nghị
### Phase 1 (Go-live nhanh, ít custom)
- Bật Purchase + Inventory + Quality + Landed Cost.
- Cấu hình kho đạt/lỗi + QCP incoming.
- Thêm `import_contract_id` trên PO và báo cáo còn thiếu.

### Phase 2 (Tối ưu vận hành)
- Wizard chọn phần còn lại (`qty_remaining`) cho hợp đồng/lịch mới.
- Dashboard điều độ hợp đồng – PO – shipment – OTK.

### Phase 3 (Nâng cao)
- Tự động phân bổ landed cost theo rule doanh nghiệp.
- Cảnh báo ETA trễ, thiếu hàng kéo dài, tỷ lệ lỗi theo NCC.

## 9) Khuyến nghị kiến trúc tổng kết
- Trọng tâm là **không phá chuẩn stock move/valuation của Odoo**.
- Dùng chuẩn partial receipt + backorder để phản ánh thiếu hàng tự nhiên.
- Dùng quality + location để tách đạt/lỗi rõ ràng.
- Dùng AVCO + landed cost để có giá vốn sát thực tế ngay khi bán từng phần.
- Custom chỉ làm lớp “orchestration” theo hợp đồng nhập khẩu và wizard chọn phần còn lại.
