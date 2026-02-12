# Review kiến trúc & quy trình (vai trò Senior System Architect)

## Bối cảnh rà soát
- Phạm vi: các module Odoo tùy biến `vnop_contract`, `vnop_delivery`, `vnop_purchase`, `vnop_sale`, `vnop_partner`.
- Mục tiêu: phát hiện điểm bất hợp lý về **code design**, **nghiệp vụ**, và **quy trình phát triển**.

## Tóm tắt điều hành
Hệ thống đã có nền tảng module hóa hợp lý theo domain (contract/delivery/purchase/sale/partner), tuy nhiên đang có một số vấn đề có thể gây lỗi runtime hoặc sai lệch dữ liệu nghiệp vụ:

1. Có lỗi ghi đè method compute trong `contract` làm logic đếm sản phẩm bị sai so với mục tiêu ban đầu.
2. Có sai tên field khi tạo stock move từ hợp đồng, nguy cơ lỗi khi chạy nghiệp vụ tạo phiếu nhập.
3. Một số ràng buộc chỉ đặt ở `onchange` (UI), chưa đảm bảo ở tầng server/database.
4. Workflow nghiệp vụ có hard-code theo tên kho/loại phiếu, kém bền vững khi triển khai đa môi trường.
5. Quy trình kỹ thuật còn thiếu chuẩn chất lượng tối thiểu (lint/test/CI/metadata manifest).

## Chi tiết phát hiện

### 1) Trùng tên method compute trong model `contract` (mức độ: High)
- Trong `contract.py`, method `_compute_product_count` được khai báo **2 lần**.
- Method sau sẽ ghi đè method trước, khiến logic đếm sản phẩm unique không còn tác dụng.

**Tác động:**
- Chỉ tiêu `product_count` có thể sai định nghĩa nghiệp vụ (đếm dòng thay vì đếm SKU).
- Dễ gây hiểu nhầm khi bảo trì do code “nhìn như có 2 lựa chọn” nhưng thực tế chỉ chạy 1.

**Khuyến nghị:**
- Giữ lại 1 method duy nhất và đặt tên rõ theo nghiệp vụ, ví dụ:
  - `_compute_product_count_lines` (đếm dòng), hoặc
  - `_compute_product_count_distinct_products` (đếm sản phẩm distinct).
- Cập nhật label/help field để phản ánh đúng cách đếm.

### 2) Sai field trên `contract.line` khi tạo stock move (mức độ: High)
- `delivery_schedule.py` sử dụng `line.product_uom.id` trong khi model `contract.line` đang khai báo field là `uom_id`.

**Tác động:**
- Khi bấm tạo receipt có thể crash do truy cập field không tồn tại.
- Nghiệp vụ nhập kho bị gián đoạn ở bước quan trọng.

**Khuyến nghị:**
- Thay `line.product_uom` bằng `line.uom_id`.
- Bổ sung validation: nếu `uom_id` rỗng thì fallback `line.product_id.uom_id` trước khi tạo move.

### 3) Ràng buộc dữ liệu đặt ở `onchange` thay vì tầng model (mức độ: High)
- Kiểm tra “mỗi contract chỉ gắn 1 delivery schedule” đang nằm trong `@api.onchange('contract_id')`.

**Tác động:**
- Dữ liệu tạo qua import/API/server action có thể bypass `onchange`.
- Có nguy cơ trùng schedule theo cùng contract.

**Khuyến nghị:**
- Thêm `@api.constrains('contract_id')` hoặc SQL constraint ở `delivery.schedule`.
- Với rule mang tính toàn cục dữ liệu, ưu tiên SQL constraint.

### 4) Hard-code tên kho và loại phiếu trong luồng OTK/receipt (mức độ: Medium)
- Wizard OTK tìm location theo name (`Kho chính`, `Kho lỗi`).
- Tạo receipt tìm picking type theo name `'Phiếu nhập kho tạm'`.

**Tác động:**
- Dễ vỡ khi đổi ngôn ngữ, đổi dữ liệu master hoặc môi trường khác tên chuẩn.
- Khó mở rộng multi-company, multi-warehouse.

**Khuyến nghị:**
- Dùng XML-ID (`env.ref`) hoặc field cấu hình theo company.
- Tạo settings model (res.config.settings / ir.config_parameter) để quản trị nghiệp vụ linh hoạt.

### 5) Thiếu kiểm soát trạng thái và idempotency khi approve contract (mức độ: Medium)
- `action_approve` tạo mới `delivery.schedule` trực tiếp, chưa thấy guard tránh tạo trùng khi click nhiều lần.

**Tác động:**
- Dễ sinh bản ghi trùng lặp, làm sai dashboard/kế hoạch giao nhận.

**Khuyến nghị:**
- Kiểm tra trạng thái hiện tại trước khi approve.
- Chỉ tạo schedule nếu chưa tồn tại (hoặc chuyển sang one2one logic rõ ràng).

### 6) Rủi ro hiệu năng và integrity ở uniqueness nghiệp vụ (mức độ: Medium)
- `product.default_code` uniqueness dùng `@api.constrains + search_count`.

**Tác động:**
- Có thể gặp race condition ở concurrent transaction.

**Khuyến nghị:**
- Cân nhắc SQL constraint (nếu nghiệp vụ yêu cầu unique toàn hệ thống).
- Nếu unique theo company, thiết kế composite index/constraint phù hợp.

### 7) Thiếu metadata chuẩn trong manifest và guideline đóng gói (mức độ: Low)
- Manifest còn tối giản, thiếu các trường phổ biến: `version`, `license`, `summary`, `application`, `installable`.

**Tác động:**
- Khó quản trị release, compliance và triển khai theo môi trường.

**Khuyến nghị:**
- Chuẩn hóa manifest theo policy nội bộ.
- Đồng bộ versioning giữa các module có phụ thuộc chéo.

## Đề xuất lộ trình cải thiện

### Sprint 1 (ưu tiên nóng)
1. Sửa lỗi compute trùng tên ở `contract`.
2. Sửa mapping UoM khi tạo stock move từ delivery schedule.
3. Chuyển rule uniqueness contract-schedule sang constraint tầng model/SQL.

### Sprint 2 (ổn định hệ thống)
1. Cấu hình hóa toàn bộ hard-code kho/picking type bằng XML-ID hoặc settings.
2. Gia cố guard trạng thái approve và chống tạo trùng schedule.
3. Chuẩn hóa xử lý lỗi nghiệp vụ (`UserError` vs `ValidationError`) theo guideline thống nhất.

### Sprint 3 (nâng chuẩn quy trình)
1. Thiết lập CI: lint (ruff/pylint-odoo), test tự động, kiểm tra manifest.
2. Bổ sung test cho luồng chính: approve contract -> create schedule -> create receipt -> OTK.
3. Thiết lập checklist code review theo domain (ORM constraints, state machine, multi-company, idempotency).

## Kết luận
Codebase đang ở trạng thái “đủ chạy nghiệp vụ cơ bản”, nhưng còn một số điểm thiết kế có thể tạo lỗi vận hành hoặc sai dữ liệu khi scale/triển khai nhiều môi trường. Nên xử lý ngay các lỗi mức High trước, sau đó nâng chuẩn quy trình phát triển để giảm regression.
