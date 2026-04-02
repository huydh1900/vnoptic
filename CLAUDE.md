# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VNOptic is an **Odoo 18.0 addons workspace** for an optical/eyewear business. Each top-level folder (e.g. `vnop_sync`, `vnop_delivery`, `vnop_contract`) is a standalone Odoo module with a `__manifest__.py`.

## Build, Test, and Development Commands

All commands run from repository root. Replace `<odoo.conf>` and `<db>` with your local values (default: `conf/vnoptic.conf`, DB `vnoptic82`).

```bash
# Update modules
odoo-bin -c <odoo.conf> --addons-path=/home/huytq/vnoptic/vnoptic -d <db> -u vnop_sync,vnop_delivery

# Run tests for a specific module (only attachment_preview has tests currently)
odoo-bin -c <odoo.conf> --addons-path=/home/huytq/vnoptic/vnoptic -d <db> --test-enable --test-tags attachment_preview --stop-after-init

# Install a module with dev mode
odoo-bin -c <odoo.conf> -d <db> -i <module_name> --dev=all
```

## Architecture

**12 modules** organized by domain:

### Core / Data Sync
- **vnop_sync** — Core module (`application=True`). Syncs lenses, frames, accessories from external Spring Boot API (`https://erp.vnoptictech.com.vn`). Handles product master data, Excel import/preview, image sync (parallel download via ThreadPoolExecutor), and server connector configuration. Credentials in `.env`.
- **vnop_currency_rate** — Auto-syncs currency rates from Vietcombank/SBV via cron. Standalone, no custom module deps.

### Procurement Chain
- **vnop_contract** — Contract and contract line management with document type classification. Links to stock pickings for receipt tracking.
- **vnop_purchase_offer** — Purchase quotation/proposal system with follow-up reminders (cron + email). Depends on `vnop_contract`.
- **vnop_delivery** — Delivery schedule planning and OTK (Order To Keep) logistics tracking with wizard operations. Depends on `vnop_contract`, `vnop_purchase_offer`.
- **vnop_purchase** — Purchase order extensions + landed cost product data (18 predefined cost types). Depends on `vnop_delivery`, `vnop_contract`, `stock_landed_costs`.

### Sales / Partner
- **vnop_sale** — Product variant uniqueness constraint (`default_code` unique check).
- **vnop_partner** — `res.partner` extensions: `ref` uniqueness SQL constraint.

### Frontend
- **vnop_theme** — Custom login UI with SCSS/JS assets.
- **vnop_chatter_toggle** — Collapsible form chatter (JS `@odoo-module`).
- **vnop_float_trim_zeros** — Hides trailing ",00" on natural numbers (JS formatter patch).

### Shared Utility
- **attachment_preview** — OCA-style module for previewing attachments via Viewer.js. Has the **only existing test suite**.

### Module Dependency Chain

```
vnop_purchase → vnop_delivery → vnop_contract → [purchase_stock, stock, mail, attachment_preview]
                                 ↑
vnop_purchase_offer ─────────────┘
```

Standalone: `vnop_sync`, `vnop_currency_rate`, `vnop_sale`, `vnop_partner`, `vnop_theme`, `vnop_chatter_toggle`, `vnop_float_trim_zeros`.

## Module Layout Convention

```
<module>/
├── models/          # Python ORM models and business logic
├── views/           # XML form/tree/search/kanban views
├── security/        # ir.model.access.csv, group rules
├── data/            # Seed data, cron jobs, sequences
├── static/src/      # JS (@odoo-module style), SCSS
├── wizard/          # Wizard dialogs (e.g. OTK operations)
├── i18n/            # Translations (vi.po, vi_VN.po)
└── tests/           # Python tests (test_*.py)
```

## Coding Conventions

- Python: 4-space indent, `snake_case` methods/fields, `PascalCase` model classes inheriting `models.Model`.
- XML IDs and filenames should be descriptive: `contract_line_views.xml`, `stock_otk_sequence.xml`.
- JS files use `/** @odoo-module **/` header or `.esm.js` pattern.
- Business rules belong in `models/`, not in views or controllers.
- Tests use Odoo base classes (`BaseCommon`, `TransactionCase`). Bug fixes should include a regression test.
- Custom fields/tabs on `product.template` form must include `invisible="type != 'consu'"` so they are hidden for service/combo products (landed costs use the base Odoo form).

## Commit Style

Short imperative subjects: `<scope>: <action>` (e.g. `delivery: fix schedule sync on cancel`). One logical change per commit. Vietnamese commit messages are acceptable per project history.

## External Dependencies

Python: `requests`, `Pillow`, `python-dotenv`, `openpyxl`, `xlsxwriter`. Declared in module `__manifest__.py` under `external_dependencies`.

## Environment Configuration

### `.env` (API credentials — never commit)
Required vars: `SPRING_BOOT_BASE_URL`, `SPRINGBOOT_SERVICE_USERNAME`, `SPRINGBOOT_SERVICE_PASSWORD`.
Optional: `SSL_VERIFY`, `LOGIN_TIMEOUT`, `API_TIMEOUT`, `PRODUCT_IMAGE_PARALLEL_WORKERS` (default 8), `PRODUCT_IMAGE_SYNC_MODE` (off/missing/changed/always).

### `conf/vnoptic.conf` (Odoo server config)
PostgreSQL on localhost:5432, HTTP port 8029, addons path includes `odoo18/addons`, `enterprise`, `vnoptic`.

## Security Notes

- `.env` contains API credentials — never commit secrets.
- New external Python deps must be declared in the module's `__manifest__.py` `external_dependencies`.
- `attachment_preview` controller validates binary field access against a whitelist (`ALLOWED_BINARY_FIELDS`).


# 🧠 AI Coding Rules / Development Guardrails

## 1. General Principles
- Không viết code linh tinh, code rác, hoặc code không cần thiết.
- Không tự ý thêm logic ngoài yêu cầu.
- Không đoán mò yêu cầu hoặc tự "bịa" chức năng.
- Luôn ưu tiên **đúng yêu cầu > thông minh > tối ưu sau**.
- Nếu không chắc chắn → phải **giữ nguyên code và ghi chú**, không tự sửa.

## 2. Code Safety Rules
- ❌ Không được xóa file, sửa file không liên quan nếu chưa có yêu cầu rõ ràng.
- ❌ Không refactor toàn bộ project nếu chỉ cần sửa nhỏ.
- ❌ Không thay đổi API, schema, hoặc cấu trúc dữ liệu khi chưa được yêu cầu.
- ❌ Không break backward compatibility.
- ✅ Chỉ thay đổi **đúng phạm vi task**.

## 3. Code Quality Standards
- Code phải:
  - Dễ đọc (readable)
  - Dễ hiểu (understandable)
  - Dễ maintain (maintainable)
- Đặt tên biến/hàm rõ nghĩa (semantic naming)
- Tránh:
  - Magic numbers
  - Hardcode không cần thiết
  - Logic lồng nhau quá sâu

## 4. Performance & Optimization
- Không viết code gây:
  - Loop thừa
  - Query/database call dư thừa
  - Re-render không cần thiết
- Tối ưu khi:
  - Có thể cải thiện rõ ràng
  - Không làm code khó đọc hơn
- Ưu tiên:
  - Clean > Fast > Clever

## 5. Error Handling
- Không bỏ qua error
- Không dùng try/catch để "che lỗi"
- Luôn:
  - Log lỗi rõ ràng
  - Trả message hợp lý
- Không silent fail

## 6. Consistency Rules
- Tuân thủ:
  - Coding convention của project
  - Format code hiện tại
- Không tự ý:
  - Đổi style code
  - Đổi naming convention
- Nếu có inconsistency → follow code hiện có

## 7. Minimal Change Principle
- Chỉ sửa **đúng chỗ cần sửa**
- Không:
  - Viết lại toàn bộ function nếu không cần
  - Refactor lan rộng
- Mọi thay đổi phải:
  - Nhỏ nhất có thể
  - Dễ review

## 8. No Hallucination Policy
- ❌ Không bịa function / API / library không tồn tại
- ❌ Không giả định logic backend khi chưa biết
- ❌ Không tự tạo config nếu không có trong project
- Nếu thiếu thông tin:
  → Giữ nguyên + comment TODO

## 9. Documentation & Comments
- Chỉ comment khi:
  - Logic phức tạp
  - Có business rule quan trọng
- Không comment thừa kiểu:
  // increase i by 1
- Comment phải:
  - Ngắn gọn
  - Có giá trị

## 10. Testing Awareness
- Không phá test hiện có
- Nếu sửa logic → đảm bảo:
  - Không ảnh hưởng case cũ
- Nếu có thể:
  - Thêm test cho logic mới

## 11. Security Rules
- Không:
  - Hardcode secret / API key
  - Log dữ liệu nhạy cảm
- Validate input nếu có user input
- Tránh injection / unsafe execution

## 12. Communication Rules (Quan trọng cho AI)
- Nếu yêu cầu không rõ:
  → Không đoán, không code bừa
- Nếu có nhiều cách làm:
  → Chọn cách:
  - Đơn giản nhất
  - Phù hợp project nhất
- Nếu thay đổi lớn:
  → Cần ghi chú rõ

## 13. Absolute Prohibitions 🚫
- Không code "cho có"
- Không fix bug kiểu random
- Không sửa cho "chạy được là được"
- Không over-engineering
- Không copy code mà không hiểu
- Nếu không chắc chắn:
  → KHÔNG code
  → hỏi lại

## 14. Golden Rule ✨
> Viết code như thể người maintain tiếp theo sẽ ghét bạn nếu bạn làm ẩu.

## 15. Context Awareness (VERY IMPORTANT)
- Luôn hiểu context project trước khi code:
  - Module đang làm gì?
  - Flow business ra sao?
- Không viết code nếu chưa hiểu:
  - Data flow
  - Call chain
- Nếu thiếu context:
  → hỏi lại hoặc giữ nguyên code

## 16. Odoo Specific Rules
- Không bypass ORM (trừ khi có lý do rõ ràng)
- Tránh:
  - N+1 query
  - search trong loop
- Ưu tiên:
  - recordset operations
  - batch processing
- Khi override:
  - Luôn gọi super() nếu cần
  - Không phá flow chuẩn của Odoo

## 17. Debug First Rule
- Khi có bug:
  - Không sửa ngay
  - Phải:
    1. Xác định root cause
    2. Trace flow
    3. Hiểu logic hiện tại
- Không fix kiểu thử-sai (trial-and-error)

## 18. Scope Control
- Chỉ làm đúng task được yêu cầu
- Không:
  - Tự mở rộng feature
  - Tự sửa phần không liên quan
- Nếu thấy vấn đề khác:
  → chỉ ghi chú, không sửa
