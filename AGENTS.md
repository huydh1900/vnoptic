# Repository Guidelines

## Project Structure & Module Organization
This repository is an Odoo addons workspace. Each top-level folder (for example `vnop_sync`, `vnop_delivery`, `vnop_contract`, `attachment_preview`) is a standalone module with a `__manifest__.py`.

Common layout inside modules:
- `models/`: Python business logic and model extensions.
- `views/`: form/tree/search/menu XML definitions.
- `security/`: `ir.model.access.csv` and group rules.
- `data/`: seed data, cron jobs, sequences.
- `static/src/`: frontend JS/SCSS assets.
- `i18n/`: translation files (`vi.po`, `vi_VN.po`, etc.).
- `tests/`: Python tests (currently present in `attachment_preview/tests`).

## Build, Test, and Development Commands
Run commands from repository root and point to your Odoo config/database.

- `odoo-bin -c <odoo.conf> --addons-path=/home/huytq/vnoptic/vnoptic -d <db> -u vnop_sync,vnop_delivery`
Updates selected modules in a local database.
- `odoo-bin -c <odoo.conf> --addons-path=/home/huytq/vnoptic/vnoptic -d <db> --test-enable --test-tags attachment_preview --stop-after-init`
Runs module tests and exits.
- `odoo-bin -c <odoo.conf> -d <db> -i vnop_theme --dev=all`
Installs a module with developer asset mode.

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case` methods/fields, `PascalCase` model classes inheriting `models.Model`.
- Keep Odoo IDs and XML file names descriptive: `contract_line_views.xml`, `stock_otk_sequence.xml`.
- JS in `static/src/js/` should use Odoo module style (`/** @odoo-module **/`) or existing `.esm.js` pattern.
- Prefer small, focused model methods and keep business rules in `models/` instead of views.

## Testing Guidelines
- Add tests under `<module>/tests/test_*.py`.
- Use Odoo test base classes (`BaseCommon`, `TransactionCase`, etc.) and validate real ORM behavior.
- For bug fixes, include at least one regression test that fails before the fix.

## Commit & Pull Request Guidelines
Git history favors short, imperative subjects (for example `Update logic OTK`, `fix form giao diện đăng nhập...`). Follow this pattern:
- Commit title: `<scope> <action>` (example: `delivery: fix schedule sync on cancel`).
- Keep one logical change per commit.
- PRs should include: affected modules, behavior summary, reproduction/verification steps, and screenshots for UI changes.

## Security & Configuration Tips
- Treat `.env` and connector credentials as sensitive; never commit secrets.
- Document any new external Python dependency in module manifests (`external_dependencies`).
