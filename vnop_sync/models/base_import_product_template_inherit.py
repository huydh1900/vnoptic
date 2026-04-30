# -*- coding: utf-8 -*-

from odoo import models


class BaseImportProductTemplateInherit(models.TransientModel):
    _inherit = 'base_import.import'

    _VNOP_IMPORT_HEADER_MARKERS = {
        'categ_id',
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
            'barcode',
            'categ_id',
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
