# -*- coding: utf-8 -*-

import json
import logging
import math
import os
import time
import base64

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules.registry import Registry

_logger = logging.getLogger(__name__)


class ProductImportQueueSession(models.Model):
    _name = 'product.import.queue.session'
    _description = 'Product Import Queue History'
    _order = 'id desc'

    name = fields.Char(default=lambda self: _('Product Import Queue'))
    res_model = fields.Char(string='Target Model', default='product.template', required=True, readonly=True)
    file_name = fields.Char(string='File Name', required=True)
    excel_file = fields.Binary(
        string='Excel File',
        required=True,
        attachment=False,
        help='Raw import payload used by background batches.',
    )

    job_type = fields.Selection([
        ('import', 'Import'),
        ('test', 'Test'),
    ], string='Job Type', default='import', required=True, readonly=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], default='draft', required=True)

    batch_size = fields.Integer(string='Batch Size', default=lambda self: self._get_default_batch_size(), required=True)
    total_rows = fields.Integer(string='Total Rows', readonly=True)
    processed_rows = fields.Integer(string='Processed Rows', readonly=True)
    total_batches = fields.Integer(string='Total Batches', readonly=True)
    current_batch = fields.Integer(string='Current Batch', readonly=True)

    success_count = fields.Integer(string='Success Count', readonly=True)
    error_count = fields.Integer(string='Error Count', readonly=True)
    warning_count = fields.Integer(string='Warning Count', readonly=True)
    progress_percent = fields.Float(string='Progress (%)', compute='_compute_progress_percent')

    product_type = fields.Selection([
        ('lens', 'Lens'),
        ('frame', 'Frame'),
        ('accessory', 'Accessory'),
    ], string='Detected Product Type', readonly=True)

    started_at = fields.Datetime(string='Started At', readonly=True)
    finished_at = fields.Datetime(string='Finished At', readonly=True)
    requested_by = fields.Many2one('res.users', string='Requested By', readonly=True)

    log_summary = fields.Text(string='Summary', readonly=True)
    error_log = fields.Text(string='Error Log', readonly=True)

    fields_json = fields.Text(string='Mapped Fields (JSON)', readonly=True)
    columns_json = fields.Text(string='Columns (JSON)', readonly=True)
    options_json = fields.Text(string='Options (JSON)', readonly=True)

    @api.depends('total_rows', 'processed_rows')
    def _compute_progress_percent(self):
        for rec in self:
            if not rec.total_rows:
                rec.progress_percent = 0.0
            else:
                rec.progress_percent = min(100.0, (float(rec.processed_rows) / float(rec.total_rows)) * 100.0)

    @api.model
    def _get_default_batch_size(self):
        try:
            size = int(os.getenv('PRODUCT_IMPORT_BATCH_SIZE', '200'))
        except Exception:
            size = 200
        return size if size > 0 else 200

    @api.model
    def _get_default_import_options(self):
        return {
            'has_headers': True,
            'advanced': True,
            'keep_matches': False,
            'quoting': '"',
            'separator': ',',
            'encoding': 'utf-8',
            'float_thousand_separator': ',',
            'float_decimal_separator': '.',
            'date_format': '',
            'datetime_format': '',
            'import_set_empty_fields': [],
            'import_skip_records': [],
        }

    @api.model
    def _build_import_fields(self, headers):
        model_fields = set(self.env['product.template']._fields)
        mapped = []
        for header in headers:
            token = str(header or '').strip()
            if not token:
                mapped.append(False)
                continue
            if token in model_fields or token in ('.id', 'id') or '/' in token:
                mapped.append(token)
                continue
            mapped.append(False)
        if not any(mapped):
            raise UserError(_('Cannot map any columns to product.template fields. Please check your template header row.'))
        return mapped

    def _safe_write_by_id(self, session_id, vals):
        dbname = self.env.cr.dbname
        max_retry = 3
        for attempt in range(1, max_retry + 1):
            try:
                with Registry(dbname).cursor() as cr:
                    env2 = api.Environment(cr, SUPERUSER_ID, {})
                    rec = env2[self._name].browse(session_id)
                    if rec.exists():
                        rec.write(vals)
                    cr.commit()
                return
            except Exception as exc:
                err_text = str(exc or '').lower()
                is_serialize_conflict = 'could not serialize access due to concurrent update' in err_text
                if is_serialize_conflict and attempt < max_retry:
                    _logger.warning(
                        '[vnop_sync] Retry safe write for session %s after serialization conflict (attempt %s/%s)',
                        session_id,
                        attempt,
                        max_retry,
                    )
                    continue
                raise

    def _get_excel_raw_bytes(self):
        self.ensure_one()
        data = self.excel_file or b''

        if isinstance(data, memoryview):
            data = data.tobytes()
        elif isinstance(data, str):
            data = data.encode('utf-8')

        if not isinstance(data, (bytes, bytearray)):
            data = bytes(data or b'')

        raw_data = bytes(data)
        file_name = (self.file_name or '').lower()
        is_xlsx_name = file_name.endswith('.xlsx')

        if not raw_data:
            _logger.warning('[vnop_sync] Empty excel_file payload for session %s', self.id)
            return raw_data

        # XLSX is a ZIP container and should start with PK when payload is raw.
        if raw_data.startswith(b'PK'):
            _logger.info('[vnop_sync] Session %s excel payload is raw bytes (len=%s)', self.id, len(raw_data))
            return raw_data

        decoded = None
        try:
            decoded = base64.b64decode(raw_data, validate=False)
        except Exception:
            decoded = None

        if decoded and decoded.startswith(b'PK'):
            _logger.info(
                '[vnop_sync] Session %s excel payload decoded from base64 to raw bytes (src_len=%s dst_len=%s)',
                self.id,
                len(raw_data),
                len(decoded),
            )
            return decoded

        if is_xlsx_name:
            _logger.warning(
                '[vnop_sync] Session %s xlsx payload does not look like ZIP (head=%s len=%s)',
                self.id,
                raw_data[:12],
                len(raw_data),
            )
        else:
            _logger.info(
                '[vnop_sync] Session %s non-xlsx payload kept as-is (head=%s len=%s)',
                self.id,
                raw_data[:12],
                len(raw_data),
            )
        return raw_data

    def _prepare_import_payload(self):
        self.ensure_one()
        excel_bytes = self._get_excel_raw_bytes()
        importer = self.env['base_import.import'].create({
            'res_model': 'product.template',
            'file': excel_bytes,
            'file_name': self.file_name,
        })
        options = self._get_default_import_options()
        preview = importer.parse_preview(dict(options), count=1)
        if preview.get('error'):
            raise UserError(_('Cannot read import file: %s') % preview['error'])

        headers = preview.get('headers') or []
        if not headers:
            raise UserError(_('Import file has no detectable header row.'))

        fields_map = self._build_import_fields(headers)
        input_file_data, import_fields = importer._convert_import_data(fields_map, dict(options))
        total_rows = len(input_file_data)
        if total_rows <= 0:
            raise UserError(_('Import file contains no data rows to process.'))

        batch_size = self.batch_size if self.batch_size > 0 else self._get_default_batch_size()
        total_batches = int(math.ceil(float(total_rows) / float(batch_size)))
        product_type = self.env['product.template']._vnop_guess_import_type(import_fields)

        return {
            'fields': fields_map,
            'columns': headers,
            'options': options,
            'total_rows': total_rows,
            'batch_size': batch_size,
            'total_batches': total_batches,
            'product_type': product_type or False,
        }

    def action_start_queue_import(self):
        self.ensure_one()
        if not self.excel_file:
            raise UserError(_('Please upload an Excel file first.'))
        if not self.file_name:
            raise UserError(_('Missing file name for the import file.'))

        payload = self._prepare_import_payload()
        self.write({
            'job_type': 'import',
            'state': 'queued',
            'res_model': 'product.template',
            'requested_by': self.env.user.id,
            'started_at': False,
            'finished_at': False,
            'total_rows': payload['total_rows'],
            'processed_rows': 0,
            'total_batches': payload['total_batches'],
            'current_batch': 0,
            'success_count': 0,
            'error_count': 0,
            'warning_count': 0,
            'error_log': False,
            'log_summary': False,
            'product_type': payload['product_type'],
            'fields_json': json.dumps(payload['fields'], ensure_ascii=False),
            'columns_json': json.dumps(payload['columns'], ensure_ascii=False),
            'options_json': json.dumps(payload['options'], ensure_ascii=False),
        })

        desc = '[Excel Import Queue] %s (%s rows)' % (self.file_name, payload['total_rows'])
        self.with_delay(description=desc)._run_import_queue_job(self.id)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_import_wizard(self):
        self.ensure_one()
        if self.requested_by and self.requested_by != self.env.user:
            raise UserError(_('You are not allowed to reopen this import session.'))
        if self.job_type != 'test' or self.state not in ('done', 'error'):
            raise UserError(_('Only completed test sessions can be reopened for import.'))

        try:
            fields_map = json.loads(self.fields_json or '[]')
            columns = json.loads(self.columns_json or '[]')
            options = json.loads(self.options_json or '{}')
        except Exception:
            fields_map = []
            columns = []
            options = {}

        return {
            'type': 'ir.actions.client',
            'tag': 'import',
            'params': {
                'active_model': self.res_model,
                'context': dict(
                    self.env.context,
                    vnop_queue_session_id=self.id,
                    vnop_queue_session_file_name=self.file_name,
                    vnop_queue_fields=fields_map,
                    vnop_queue_columns=columns,
                    vnop_queue_options=options,
                    vnop_queue_error_log=self.error_log or False,
                    vnop_queue_state=self.state,
                ),
            },
        }

    def _format_batch_messages(self, messages, batch_index, batch_skip):
        lines = []
        if not messages:
            return lines

        max_lines = 20
        for idx, msg in enumerate(messages[:max_lines], start=1):
            msg_type = (msg or {}).get('type', 'error')
            msg_text = (msg or {}).get('message') or _('Unknown error')
            row_label = ''
            record = (msg or {}).get('record')
            if isinstance(record, list) and record:
                row_label = ' | row_data=%s' % record
            lines.append('Batch %s (skip=%s) #%s [%s] %s%s' % (
                batch_index,
                batch_skip,
                idx,
                msg_type,
                msg_text,
                row_label,
            ))
        if len(messages) > max_lines:
            lines.append('Batch %s: truncated %s extra messages.' % (batch_index, len(messages) - max_lines))
        return lines

    def _run_single_batch(self, fields_map, columns, options, batch_skip, batch_size, batch_index):
        excel_bytes = self._get_excel_raw_bytes()
        importer = self.env['base_import.import'].create({
            'res_model': 'product.template',
            'file': excel_bytes,
            'file_name': self.file_name,
        })
        batch_options = dict(options)
        batch_options.pop('skip', None)
        batch_options.pop('limit', None)
        batch_options['skip'] = batch_skip
        batch_options['limit'] = batch_size

        result = importer.with_context(vnop_skip_queue_import=True, import_file=True).execute_import(
            fields_map,
            columns,
            batch_options,
            dryrun=False,
        )
        messages = result.get('messages') or []
        errors = [msg for msg in messages if (msg or {}).get('type') == 'error']
        warnings = [msg for msg in messages if (msg or {}).get('type') == 'warning']
        ids = result.get('ids') or []
        logs = self._format_batch_messages(messages, batch_index, batch_skip)
        return {
            'success': len(ids),
            'errors': len(errors),
            'warnings': len(warnings),
            'logs': logs,
        }

    def _run_single_test_batch(self, fields_map, columns, options, batch_skip, batch_size, batch_index):
        excel_bytes = self._get_excel_raw_bytes()
        importer = self.env['base_import.import'].create({
            'res_model': 'product.template',
            'file': excel_bytes,
            'file_name': self.file_name,
        })
        batch_options = dict(options)
        batch_options.pop('skip', None)
        batch_options.pop('limit', None)
        batch_options['skip'] = batch_skip
        batch_options['limit'] = batch_size

        result = importer.with_context(vnop_skip_queue_import=True, import_file=True).execute_import(
            fields_map,
            columns,
            batch_options,
            dryrun=True,
        )
        messages = result.get('messages') or []
        errors = [msg for msg in messages if (msg or {}).get('type') == 'error']
        warnings = [msg for msg in messages if (msg or {}).get('type') == 'warning']
        logs = self._format_batch_messages(messages, batch_index, batch_skip)
        return {
            'success': batch_size - len(errors),
            'errors': len(errors),
            'warnings': len(warnings),
            'logs': logs,
        }

    def _run_test_queue_job(self, session_id):
        session = self.browse(session_id)
        if not session.exists():
            return False

        try:
            with self.env.cr.savepoint():
                self._safe_write_by_id(session_id, {
                    'state': 'running',
                    'started_at': fields.Datetime.now(),
                    'finished_at': False,
                })

                session = self.browse(session_id)
                fields_map = json.loads(session.fields_json or '[]')
                columns = json.loads(session.columns_json or '[]')
                options = json.loads(session.options_json or '{}')

                try:
                    base_skip = int(options.get('skip') or 0)
                except Exception:
                    base_skip = 0
                base_skip = max(0, base_skip)

                total_rows = session.total_rows
                batch_size = session.batch_size if session.batch_size > 0 else self._get_default_batch_size()
                total_batches = int(math.ceil(float(total_rows) / float(batch_size))) if total_rows else 0

                _logger.info(
                    '[vnop_sync] Queue test start session=%s file=%s rows=%s batch_size=%s total_batches=%s base_skip=%s',
                    session_id,
                    session.file_name,
                    total_rows,
                    batch_size,
                    total_batches,
                    base_skip,
                )

                success_total = 0
                error_total = 0
                warning_total = 0
                log_lines = []

                for batch_index in range(1, total_batches + 1):
                    relative_skip = (batch_index - 1) * batch_size
                    batch_skip = base_skip + relative_skip
                    processed_rows = min(total_rows, relative_skip + batch_size)
                    batch_limit = min(batch_size, total_rows - relative_skip)

                    batch_success = 0
                    batch_errors = 0
                    batch_warnings = 0
                    batch_logs = []

                    batch_started = time.time()
                    _logger.info(
                        '[vnop_sync] Queue test batch start session=%s batch=%s/%s skip=%s limit=%s',
                        session_id,
                        batch_index,
                        total_batches,
                        batch_skip,
                        batch_limit,
                    )

                    try:
                        with self.env.cr.savepoint():
                            result = session._run_single_test_batch(
                                fields_map,
                                columns,
                                options,
                                batch_skip,
                                batch_limit,
                                batch_index,
                            )
                            batch_success = result['success']
                            batch_errors = result['errors']
                            batch_warnings = result['warnings']
                            batch_logs = result['logs']
                    except Exception as batch_error:
                        _logger.exception(
                            '[vnop_sync] Queue test batch failed session=%s batch=%s/%s skip=%s limit=%s',
                            session_id,
                            batch_index,
                            total_batches,
                            batch_skip,
                            batch_limit,
                        )
                        batch_errors = batch_limit
                        batch_logs = [
                            'Batch %s failed with exception: %s' % (batch_index, str(batch_error)),
                        ]

                    elapsed = time.time() - batch_started
                    _logger.info(
                        '[vnop_sync] Queue test batch end session=%s batch=%s/%s success=%s errors=%s warnings=%s elapsed=%.2fs',
                        session_id,
                        batch_index,
                        total_batches,
                        batch_success,
                        batch_errors,
                        batch_warnings,
                        elapsed,
                    )

                    success_total += batch_success
                    error_total += batch_errors
                    warning_total += batch_warnings
                    log_lines.extend(batch_logs)
                    if len(log_lines) > 500:
                        log_lines = log_lines[-500:]

                    summary = (
                        'Batches: %s/%s | Processed: %s/%s | Valid: %s | Errors: %s | Warnings: %s'
                        % (batch_index, total_batches, processed_rows, total_rows, success_total, error_total, warning_total)
                    )
                    self._safe_write_by_id(session_id, {
                        'current_batch': batch_index,
                        'processed_rows': processed_rows,
                        'success_count': success_total,
                        'error_count': error_total,
                        'warning_count': warning_total,
                        'log_summary': summary,
                        'error_log': '\n'.join(log_lines),
                    })

                final_summary = (
                    'Completed test file %s | Rows: %s | Valid: %s | Errors: %s | Warnings: %s'
                    % (session.file_name, total_rows, success_total, error_total, warning_total)
                )
                job_state = 'done'
                if error_total > 0:
                    job_state = 'error'
                self._safe_write_by_id(session_id, {
                    'state': job_state,
                    'finished_at': fields.Datetime.now(),
                    'current_batch': total_batches,
                    'processed_rows': total_rows,
                    'success_count': success_total,
                    'error_count': error_total,
                    'warning_count': warning_total,
                    'log_summary': final_summary,
                    'error_log': '\n'.join(log_lines),
                })
                _logger.info(
                    '[vnop_sync] Queue test %s session=%s rows=%s valid=%s errors=%s warnings=%s',
                    job_state,
                    session_id,
                    total_rows,
                    success_total,
                    error_total,
                    warning_total,
                )
                return job_state == 'done'
        except Exception as exc:
            _logger.exception('[vnop_sync] Queue test session %s failed', session_id)
            self._safe_write_by_id(session_id, {
                'state': 'error',
                'finished_at': fields.Datetime.now(),
                'log_summary': 'Queue test failed: %s' % str(exc),
            })
            return False

    def _run_import_queue_job(self, session_id):
        session = self.browse(session_id)
        if not session.exists():
            return False

        try:
            with self.env.cr.savepoint():
                self._safe_write_by_id(session_id, {
                    'state': 'running',
                    'started_at': fields.Datetime.now(),
                    'finished_at': False,
                })

                session = self.browse(session_id)
                fields_map = json.loads(session.fields_json or '[]')
                columns = json.loads(session.columns_json or '[]')
                options = json.loads(session.options_json or '{}')

                try:
                    base_skip = int(options.get('skip') or 0)
                except Exception:
                    base_skip = 0
                base_skip = max(0, base_skip)

                total_rows = session.total_rows
                batch_size = session.batch_size if session.batch_size > 0 else self._get_default_batch_size()
                total_batches = int(math.ceil(float(total_rows) / float(batch_size))) if total_rows else 0

                _logger.info(
                    '[vnop_sync] Queue import start session=%s file=%s rows=%s batch_size=%s total_batches=%s base_skip=%s',
                    session_id,
                    session.file_name,
                    total_rows,
                    batch_size,
                    total_batches,
                    base_skip,
                )

                success_total = 0
                error_total = 0
                warning_total = 0
                log_lines = []

                for batch_index in range(1, total_batches + 1):
                    relative_skip = (batch_index - 1) * batch_size
                    batch_skip = base_skip + relative_skip
                    processed_rows = min(total_rows, relative_skip + batch_size)
                    batch_limit = min(batch_size, total_rows - relative_skip)

                    batch_success = 0
                    batch_errors = 0
                    batch_warnings = 0
                    batch_logs = []

                    batch_started = time.time()
                    _logger.info(
                        '[vnop_sync] Queue batch start session=%s batch=%s/%s skip=%s limit=%s',
                        session_id,
                        batch_index,
                        total_batches,
                        batch_skip,
                        batch_limit,
                    )

                    try:
                        with self.env.cr.savepoint():
                            result = session._run_single_batch(
                                fields_map,
                                columns,
                                options,
                                batch_skip,
                                batch_limit,
                                batch_index,
                            )
                            batch_success = result['success']
                            batch_errors = result['errors']
                            batch_warnings = result['warnings']
                            batch_logs = result['logs']
                    except Exception as batch_error:
                        _logger.exception(
                            '[vnop_sync] Queue batch failed session=%s batch=%s/%s skip=%s limit=%s',
                            session_id,
                            batch_index,
                            total_batches,
                            batch_skip,
                            batch_limit,
                        )
                        batch_errors = batch_limit
                        batch_logs = [
                            'Batch %s failed with exception: %s' % (batch_index, str(batch_error)),
                        ]

                    elapsed = time.time() - batch_started
                    _logger.info(
                        '[vnop_sync] Queue batch end session=%s batch=%s/%s success=%s errors=%s warnings=%s elapsed=%.2fs',
                        session_id,
                        batch_index,
                        total_batches,
                        batch_success,
                        batch_errors,
                        batch_warnings,
                        elapsed,
                    )

                    success_total += batch_success
                    error_total += batch_errors
                    warning_total += batch_warnings
                    log_lines.extend(batch_logs)
                    if len(log_lines) > 500:
                        log_lines = log_lines[-500:]

                    summary = (
                        'Batches: %s/%s | Processed: %s/%s | Success: %s | Errors: %s | Warnings: %s'
                        % (batch_index, total_batches, processed_rows, total_rows, success_total, error_total, warning_total)
                    )
                    self._safe_write_by_id(session_id, {
                        'current_batch': batch_index,
                        'processed_rows': processed_rows,
                        'success_count': success_total,
                        'error_count': error_total,
                        'warning_count': warning_total,
                        'log_summary': summary,
                        'error_log': '\n'.join(log_lines),
                    })

                final_summary = (
                    'Completed import file %s | Rows: %s | Success: %s | Errors: %s | Warnings: %s'
                    % (session.file_name, total_rows, success_total, error_total, warning_total)
                )
                job_state = 'done'
                if error_total > 0:
                    job_state = 'error'
                self._safe_write_by_id(session_id, {
                    'state': job_state,
                    'finished_at': fields.Datetime.now(),
                    'current_batch': total_batches,
                    'processed_rows': total_rows,
                    'success_count': success_total,
                    'error_count': error_total,
                    'warning_count': warning_total,
                    'log_summary': final_summary,
                    'error_log': '\n'.join(log_lines),
                })
                _logger.info(
                    '[vnop_sync] Queue import %s session=%s rows=%s success=%s errors=%s warnings=%s',
                    job_state,
                    session_id,
                    total_rows,
                    success_total,
                    error_total,
                    warning_total,
                )
                return job_state == 'done'
        except Exception as exc:
            _logger.exception('[vnop_sync] Queue import session %s failed', session_id)
            self._safe_write_by_id(session_id, {
                'state': 'error',
                'finished_at': fields.Datetime.now(),
                'log_summary': 'Queue import failed: %s' % str(exc),
            })
            return False