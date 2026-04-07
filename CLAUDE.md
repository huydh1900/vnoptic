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

**17 modules** organized by domain:

### Core / Data Sync
- **vnop_sync** — Core module (`application=True`). Syncs lenses, frames, accessories from external Spring Boot API. Handles product master data, Excel import/preview, image sync (parallel download via ThreadPoolExecutor), and server connector configuration. Credentials in `.env`.
- **vnop_currency_rate** — Auto-syncs currency rates from Vietcombank/SBV via cron.

### Procurement Chain
- **vnop_contract** — Contract and contract line management with document type classification. Links to stock pickings for receipt tracking.
- **vnop_purchase_offer** — Purchase quotation/proposal system with follow-up reminders (cron + email). Depends on `vnop_contract`.
- **vnop_delivery** — Delivery schedule planning and OTK (Order To Keep) logistics tracking with wizard operations. Depends on `vnop_contract`, `vnop_purchase_offer`.
- **vnop_purchase** — Purchase order extensions + landed cost product data (18 predefined cost types). Depends on `vnop_delivery`, `vnop_contract`, `stock_landed_costs`.

### Sales / Partner
- **vnop_sale_channel** — Dual-channel sales infrastructure (wholesale/retail). Adds `channel_type` field to `res.partner`, `product.pricelist`, and `sale.order`. Seeds default wholesale/retail pricelists.
- **vnop_promotion** — Channel-aware promotions. Extends `loyalty.program` with `channel_type` so promotions apply only to matching sales channel. Depends on `vnop_sale_channel`.
- **vnop_partner** — `res.partner` extensions: `ref` uniqueness SQL constraint.

### Inventory
- **vnop_stock** — Lens stock matrix view: 2D grid (SPH x CYL) showing on-hand quantities for lens products. Creates "Kho Tam" (temp/QC) and "Kho Loi" (defect) warehouse locations. Depends on `vnop_sync` for `product.lens.power` model.

### Localization
- **vnop_l10n_vn_fix** — Fixes broken WIP account template reference in `l10n_vn` (`chart154` -> `chart1541`). Prevents `stock_account` post-init crash.

### Frontend
- **vnop_theme** — Custom login UI with SCSS/JS assets.
- **vnop_chatter_toggle** — Collapsible form chatter (JS `@odoo-module`).
- **vnop_float_trim_zeros** — Hides trailing ",00" on natural numbers (JS formatter patch).

### Shared Utility / OCA
- **attachment_preview** — OCA-style module for previewing attachments via Viewer.js. Has the **only existing test suite**.
- **queue_job** — OCA async job queue framework. Provides `queue.job` model with state machine, channels, priorities, and retry logic.
- **queue_job_cron_jobrunner** — Cron-based job runner for `queue_job` (no external daemon needed). Depends on `queue_job`.

### Module Dependency Chain

```
vnop_purchase → vnop_delivery → vnop_contract → [purchase_stock, stock, mail, attachment_preview]
                                 ↑
vnop_purchase_offer ─────────────┘

vnop_promotion → vnop_sale_channel
vnop_stock → vnop_sync
queue_job_cron_jobrunner → queue_job
```

Standalone: `vnop_sync`, `vnop_currency_rate`, `vnop_sale_channel`, `vnop_partner`, `vnop_theme`, `vnop_chatter_toggle`, `vnop_float_trim_zeros`, `vnop_l10n_vn_fix`, `queue_job`.

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
