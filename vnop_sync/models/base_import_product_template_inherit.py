# -*- coding: utf-8 -*-

import json
import math

from odoo import _, api, models
from odoo.addons.base_import.models.base_import import ImportValidationError


class BaseImportProductTemplateInherit(models.TransientModel):
    _inherit = 'base_import.import'

    _VNOP_IMPORT_HEADER_MARKERS = {
        'categ_id',
        'group_id',
        'uom_id',
        'brand_id',
        'len_type',
        'opt_sku',
        'opt_model',
        'design_id',
        'shape_id',
        'material_id',
        'color_id',
    }

    def _vnop_normalize_header_cell(self, value):
        if value in (None, False):
            return ''
        return str(value).strip()

    def _vnop_find_technical_header_index(self, rows):
        product_fields = set(self.env['product.template']._fields)
        best_index = None
        best_score = -1

        for index, row in enumerate(rows):
            row_tokens = {
                self._vnop_normalize_header_cell(cell)
                for cell in row
                if self._vnop_normalize_header_cell(cell)
            }
            matched_tokens = row_tokens & product_fields
            if not matched_tokens:
                continue

            score = len(matched_tokens)
            has_name = 'name' in matched_tokens
            has_marker = bool(matched_tokens & self._VNOP_IMPORT_HEADER_MARKERS)
            if has_name and has_marker and score > best_score:
                best_index = index
                best_score = score

        if best_index is not None:
            return best_index

        for index, row in enumerate(rows):
            row_tokens = {
                self._vnop_normalize_header_cell(cell)
                for cell in row
                if self._vnop_normalize_header_cell(cell)
            }
            score = len(row_tokens & product_fields)
            if score >= 3 and score > best_score:
                best_index = index
                best_score = score

        return best_index

    def _vnop_find_data_start_index(self, rows, header_index, header_tokens):
        key_fields = {
            'name',
            'default_code',
            'categ_id',
            'group_id',
            'uom_id',
            'brand_id',
            'standard_price',
            'list_price',
            'len_type',
            'opt_model',
            'design_id',
            'shape_id',
        }
        key_indices = [idx for idx, token in enumerate(header_tokens) if token in key_fields]
        header_len = len(header_tokens)

        for row_index in range(header_index + 1, len(rows)):
            row = rows[row_index]
            non_empty_indices = [
                idx
                for idx in range(min(len(row), header_len))
                if self._vnop_normalize_header_cell(row[idx])
            ]
            if not non_empty_indices:
                continue

            if key_indices and any(idx in non_empty_indices for idx in key_indices):
                return row_index

            if len(non_empty_indices) >= 2:
                return row_index

        return len(rows)

    def _vnop_pad_row(self, row, target_len):
        if len(row) >= target_len:
            return list(row)
        return list(row) + [''] * (target_len - len(row))

    def _read_file(self, options):
        file_length, rows = super()._read_file(options)
        if self.res_model != 'product.template' or not options.get('has_headers') or not rows:
            return file_length, rows

        header_index = self._vnop_find_technical_header_index(rows)
        if header_index is None:
            return file_length, rows

        header_row = list(rows[header_index])
        header_tokens = [self._vnop_normalize_header_cell(cell) for cell in header_row]
        data_start = self._vnop_find_data_start_index(rows, header_index, header_tokens)

        normalized_rows = [header_row]
        if data_start < len(rows):
            normalized_rows.extend(rows[data_start:])

        header_len = len(header_row)
        normalized_rows = [self._vnop_pad_row(row, header_len) for row in normalized_rows]

        # Ensure preview has one data line even for empty templates.
        if len(normalized_rows) == 1:
            normalized_rows.append([''] * header_len)

        return len(normalized_rows), normalized_rows

    def _vnop_should_enqueue_import(self, dryrun):
        self.ensure_one()
        if self.res_model != 'product.template':
            return False
        if self.env.context.get('vnop_skip_queue_import'):
            return False
        return bool(self.file)

    def _vnop_enqueue_product_template_import(self, fields, columns, options):
        self.ensure_one()

        queue_options = dict(options or {})
        try:
            requested_skip = int(queue_options.get('skip') or 0)
        except Exception:
            requested_skip = 0
        requested_skip = max(0, requested_skip)

        try:
            requested_limit = int(queue_options.get('limit') or 0)
        except Exception:
            requested_limit = 0
        requested_limit = max(0, requested_limit)

        queue_options['skip'] = requested_skip
        if requested_limit > 0:
            queue_options['limit'] = requested_limit
        else:
            queue_options.pop('limit', None)

        try:
            input_file_data, import_fields = self._convert_import_data(fields, dict(queue_options))
        except ImportValidationError as error:
            return {'messages': [error.__dict__]}

        total_rows = len(input_file_data)
        if total_rows <= 0:
            return False

        session_model = self.env['product.import.queue.session']
        batch_size = requested_limit if requested_limit > 0 else session_model._get_default_batch_size()
        total_batches = int(math.ceil(float(total_rows) / float(batch_size))) if total_rows else 0
        product_type = self.env['product.template']._vnop_guess_import_type(import_fields)

        session = session_model.create({
            'name': _('Product Import Queue'),
            'res_model': self.res_model,
            'file_name': self.file_name or _('Import File'),
            'excel_file': self.file,
            'state': 'queued',
            'batch_size': batch_size,
            'total_rows': total_rows,
            'processed_rows': 0,
            'total_batches': total_batches,
            'current_batch': 0,
            'success_count': 0,
            'error_count': 0,
            'warning_count': 0,
            'product_type': product_type or False,
            'requested_by': self.env.user.id,
            'fields_json': json.dumps(fields, ensure_ascii=False),
            'columns_json': json.dumps(columns, ensure_ascii=False),
            'options_json': json.dumps(queue_options, ensure_ascii=False),
            'log_summary': _('Queued for background processing.'),
            'error_log': False,
        })

        description = 'Import Jobs Queue %s (%s dòng)' % (session.file_name, total_rows)
        session.with_delay(description=description)._run_import_queue_job(session.id)

        return {
            'ids': [],
            'messages': [],
            'nextrow': 0,
            'name': [],
            'queued': True,
            'queued_session_id': session.id,
            'queued_rows': total_rows,
        }

    def _vnop_enqueue_product_template_test(self, fields, columns, options):
        self.ensure_one()

        queue_options = dict(options or {})
        try:
            requested_skip = int(queue_options.get('skip') or 0)
        except Exception:
            requested_skip = 0
        requested_skip = max(0, requested_skip)

        try:
            requested_limit = int(queue_options.get('limit') or 0)
        except Exception:
            requested_limit = 0
        requested_limit = max(0, requested_limit)

        queue_options['skip'] = requested_skip
        if requested_limit > 0:
            queue_options['limit'] = requested_limit
        else:
            queue_options.pop('limit', None)

        try:
            input_file_data, import_fields = self._convert_import_data(fields, dict(queue_options))
        except ImportValidationError as error:
            return {'messages': [error.__dict__]}

        total_rows = len(input_file_data)
        if total_rows <= 0:
            return False

        session_model = self.env['product.import.queue.session']
        batch_size = requested_limit if requested_limit > 0 else session_model._get_default_batch_size()
        total_batches = int(math.ceil(float(total_rows) / float(batch_size))) if total_rows else 0
        product_type = self.env['product.template']._vnop_guess_import_type(import_fields)

        session = session_model.create({
            'name': _('Product Import Queue'),
            'res_model': self.res_model,
            'file_name': self.file_name or _('Import File'),
            'excel_file': self.file,
            'job_type': 'test',
            'state': 'queued',
            'batch_size': batch_size,
            'total_rows': total_rows,
            'processed_rows': 0,
            'total_batches': total_batches,
            'current_batch': 0,
            'success_count': 0,
            'error_count': 0,
            'warning_count': 0,
            'product_type': product_type or False,
            'requested_by': self.env.user.id,
            'fields_json': json.dumps(fields, ensure_ascii=False),
            'columns_json': json.dumps(columns, ensure_ascii=False),
            'options_json': json.dumps(queue_options, ensure_ascii=False),
            'log_summary': _('Queued for background testing.'),
            'error_log': False,
        })

        description = 'Kiểm thử Jobs Queue %s (%s dòng)' % (session.file_name, total_rows)
        session.with_delay(description=description)._run_test_queue_job(session.id)

        return {
            'ids': [],
            'messages': [],
            'nextrow': 0,
            'name': [],
            'queued': True,
            'queued_session_id': session.id,
            'queued_rows': total_rows,
        }

    @api.model
    def vnop_create_import_from_queue_session(self, session_id):
        session = self.env['product.import.queue.session'].browse(session_id)
        if not session.exists():
            raise ImportValidationError(_('Import session not found.'))
        if session.requested_by and session.requested_by != self.env.user:
            raise ImportValidationError(_('You are not allowed to reopen this import session.'))
        if session.res_model != 'product.template':
            raise ImportValidationError(_('Invalid import session target model.'))
        # Lấy lại mapping, options từ session queue
        fields = []
        columns = []
        options = {}
        import json
        try:
            fields = json.loads(session.fields_json or '[]')
            columns = json.loads(session.columns_json or '[]')
            options = json.loads(session.options_json or '{}')
        except Exception:
            pass
        import_rec = self.create({
            'res_model': session.res_model,
            'file': session.excel_file,
            'file_name': session.file_name,
        })
        # Lưu mapping vào context để parse_preview validate đúng
        self = self.with_context(
            vnop_queue_fields=fields,
            vnop_queue_columns=columns,
            vnop_queue_options=options,
        )
        return import_rec.id

    def execute_import(self, fields, columns, options, dryrun=False):
        if not self._vnop_should_enqueue_import(dryrun):
            return super().execute_import(fields, columns, options, dryrun=dryrun)

        if dryrun:
            queued_result = self._vnop_enqueue_product_template_test(fields, columns, options)
        else:
            queued_result = self._vnop_enqueue_product_template_import(fields, columns, options)

        if queued_result is False:
            return super().execute_import(fields, columns, options, dryrun=dryrun)
        return queued_result
