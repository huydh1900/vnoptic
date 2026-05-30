# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime, time, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Thứ tự cột Excel = đúng các cột bôi vàng trong file mẫu K018.
NXT_COLUMNS = [
    ('wh_code', 'Mã kho'),
    ('classif_code', 'Mã nhóm'),
    ('classif_name', 'Tên nhóm hàng'),
    ('default_code', 'Mã hàng'),
    ('barcode', 'Mã vạch NSX'),
    ('name', 'Tên hàng'),
    ('uom', 'Mã đơn vị'),
    ('tax', 'Mã thuế suất'),
    ('qty_open', 'SL tồn đầu'),
    ('val_open', 'GT tồn đầu'),
    ('qty_in', 'SL nhập'),
    ('val_in', 'GT nhập'),
    ('qty_out', 'SL xuất'),
    ('val_out', 'GT xuất'),
    ('qty_close', 'SL tồn cuối'),
    ('val_close', 'GT tồn cuối'),
    ('from_date', 'Từ ngày'),
    ('to_date', 'Đến ngày'),
]
NUM_KEYS = {'qty_open', 'val_open', 'qty_in', 'val_in',
            'qty_out', 'val_out', 'qty_close', 'val_close'}
# Số dòng tối đa trả về cho preview (full set vẫn xuất đủ ra Excel).
PREVIEW_LIMIT = 1000


class StockNxtWizard(models.TransientModel):
    _name = 'stock.nxt.wizard'
    _description = 'Báo cáo Nhập-Xuất-Tồn (NXT)'

    # Giữ model làm nơi chứa toàn bộ logic tính. UI là OWL client action,
    # gọi các @api.model method bên dưới với 1 dict `filters`.

    # ------------------------------------------------------------------
    # API cho OWL
    # ------------------------------------------------------------------
    @api.model
    def get_filter_options(self):
        company = self.env.company
        whs = self.env['stock.warehouse'].search([('company_id', '=', company.id)])
        cls = self.env['product.classification'].search([])
        return {
            'warehouses': [{'id': w.id, 'code': w.code or '', 'name': w.name or ''} for w in whs],
            'classifications': [{'id': c.id, 'code': c.code or '', 'name': c.name or ''} for c in cls],
        }

    @api.model
    def get_preview(self, filters):
        rows = self._build_rows_full(filters)
        totals = {k: 0.0 for k in NUM_KEYS}
        for r in rows:
            for k in NUM_KEYS:
                totals[k] += r[k]
        return {
            'rows': rows[:PREVIEW_LIMIT],
            'count': len(rows),
            'totals': totals,
            'limited': len(rows) > PREVIEW_LIMIT,
            'columns': [{'key': k, 'label': lbl} for k, lbl in NXT_COLUMNS],
        }

    @api.model
    def export_xlsx(self, filters):
        rows = self._build_rows_full(filters)
        from_date = fields.Date.to_date(filters.get('from_date'))
        to_date = fields.Date.to_date(filters.get('to_date'))
        data = self._write_xlsx(rows)
        fname = 'Bao_cao_NXT_%s_%s.xlsx' % (
            from_date.strftime('%Y%m%d'), to_date.strftime('%Y%m%d'))
        att = self.env['ir.attachment'].create({
            'name': fname,
            'type': 'binary',
            'datas': base64.b64encode(data),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'url': '/web/content/%s?download=true' % att.id, 'name': fname}

    # ------------------------------------------------------------------
    # Tính toán (param-based, không phụ thuộc record)
    # ------------------------------------------------------------------
    def _build_rows_full(self, filters):
        from_date = fields.Date.to_date(filters.get('from_date'))
        to_date = fields.Date.to_date(filters.get('to_date'))
        if not from_date or not to_date:
            raise UserError(_('Vui lòng chọn "Từ ngày" và "Đến ngày".'))
        if from_date > to_date:
            raise UserError(_('"Từ ngày" phải nhỏ hơn hoặc bằng "Đến ngày".'))

        company_id = self.env.company.id
        from_dt = datetime.combine(from_date, time.min)
        to_end_dt = datetime.combine(to_date + timedelta(days=1), time.min)

        wh_ids = [int(x) for x in (filters.get('warehouse_ids') or [])]
        if not wh_ids:
            wh_ids = self.env['stock.warehouse'].search(
                [('company_id', '=', company_id)]).ids
        if not wh_ids:
            raise UserError(_('Không tìm thấy kho nào cho công ty này.'))

        classif_ids = set(int(x) for x in (filters.get('classification_ids') or []))
        search = (filters.get('search') or '').strip().lower()
        only_movement = bool(filters.get('only_with_movement'))

        qty = self._fetch_qty(from_dt, to_end_dt, wh_ids, company_id)
        val = self._fetch_val(from_dt, to_end_dt, wh_ids, company_id)
        keys = set(qty) | set(val)
        if not keys:
            return []

        wh_recs = self.env['stock.warehouse'].browse(list({k[0] for k in keys}))
        wh_meta = {w.id: (w.code or '', w.name or '') for w in wh_recs}

        prods = self.env['product.product'].browse(list({k[1] for k in keys}))
        prod_meta = {}
        for p in prods:
            tmpl = p.product_tmpl_id
            classif = tmpl.classification_id
            if classif_ids and classif.id not in classif_ids:
                continue
            name = tmpl.name or ''
            dcode = p.default_code or ''
            bcode = p.barcode or ''
            if search and search not in name.lower() \
                    and search not in dcode.lower() and search not in bcode.lower():
                continue
            prod_meta[p.id] = {
                'default_code': dcode,
                'barcode': bcode,
                'name': name,
                'uom': tmpl.uom_id.name or '',
                'tax': ', '.join(tmpl.taxes_id.mapped('name')),
                'classif_code': classif.code or '',
                'classif_name': classif.name or '',
            }

        zero_q = {'qty_open': 0, 'qty_in': 0, 'qty_out': 0, 'qty_close': 0}
        zero_v = {'val_open': 0, 'val_in': 0, 'val_out': 0, 'val_close': 0}
        from_str = from_date.strftime('%d/%m/%Y')
        to_str = to_date.strftime('%d/%m/%Y')
        rows = []
        for (wh_id, pid) in keys:
            pm = prod_meta.get(pid)
            if pm is None:
                continue
            q = qty.get((wh_id, pid), zero_q)
            v = val.get((wh_id, pid), zero_v)
            if only_movement and not (q['qty_in'] or q['qty_out']):
                continue
            wh_code, _wh_name = wh_meta.get(wh_id, ('', ''))
            rows.append({
                'wh_code': wh_code,
                **pm, **q, **v,
                'from_date': from_str,
                'to_date': to_str,
            })
        rows.sort(key=lambda r: (r['wh_code'], r['classif_code'], r['default_code'], r['name']))
        return rows

    def _fetch_qty(self, from_dt, to_end_dt, wh_ids, company_id):
        """SL theo (warehouse_id, product_id) từ stock_move_line.
        Tồn đầu = nhập-xuất trước from_dt. Nhập/Xuất phân theo
        location.warehouse_id + usage='internal'.
        """
        self.env.cr.execute("""
            WITH ml AS (
                SELECT l.product_id, l.quantity, l.date,
                       src.warehouse_id AS src_wh, src.usage AS src_usage,
                       dst.warehouse_id AS dst_wh, dst.usage AS dst_usage
                  FROM stock_move_line l
                  JOIN stock_location src ON src.id = l.location_id
                  JOIN stock_location dst ON dst.id = l.location_dest_id
                 WHERE l.state = 'done'
                   AND l.company_id = %(company)s
                   AND l.date < %(to_end)s
            ),
            in_rows AS (
                SELECT dst_wh AS wh, product_id,
                       SUM(CASE WHEN date < %(from)s THEN quantity ELSE 0 END) AS open_in,
                       SUM(CASE WHEN date >= %(from)s THEN quantity ELSE 0 END) AS qty_in
                  FROM ml
                 WHERE dst_usage = 'internal' AND dst_wh = ANY(%(wh)s)
                   AND (src_usage <> 'internal' OR src_wh IS DISTINCT FROM dst_wh)
                 GROUP BY dst_wh, product_id
            ),
            out_rows AS (
                SELECT src_wh AS wh, product_id,
                       SUM(CASE WHEN date < %(from)s THEN quantity ELSE 0 END) AS open_out,
                       SUM(CASE WHEN date >= %(from)s THEN quantity ELSE 0 END) AS qty_out
                  FROM ml
                 WHERE src_usage = 'internal' AND src_wh = ANY(%(wh)s)
                   AND (dst_usage <> 'internal' OR dst_wh IS DISTINCT FROM src_wh)
                 GROUP BY src_wh, product_id
            )
            SELECT COALESCE(i.wh, o.wh) AS wh,
                   COALESCE(i.product_id, o.product_id) AS product_id,
                   COALESCE(i.open_in, 0) - COALESCE(o.open_out, 0) AS qty_open,
                   COALESCE(i.qty_in, 0) AS qty_in,
                   COALESCE(o.qty_out, 0) AS qty_out
              FROM in_rows i
              FULL OUTER JOIN out_rows o
                ON i.wh = o.wh AND i.product_id = o.product_id
        """, {'company': company_id, 'from': from_dt, 'to_end': to_end_dt, 'wh': wh_ids})
        res = {}
        for wh, pid, q_open, q_in, q_out in self.env.cr.fetchall():
            res[(wh, pid)] = {
                'qty_open': q_open, 'qty_in': q_in, 'qty_out': q_out,
                'qty_close': q_open + q_in - q_out,
            }
        return res

    def _fetch_val(self, from_dt, to_end_dt, wh_ids, company_id):
        """GT theo (warehouse_id, product_id) từ stock_valuation_layer,
        quy về kho qua stock_move -> location. GT theo kho là phân bổ xấp xỉ
        (Odoo track valuation cấp công ty) — đã thống nhất nghiệp vụ.
        """
        self.env.cr.execute("""
            WITH v AS (
                SELECT svl.product_id, svl.value, svl.create_date,
                       src.warehouse_id AS src_wh, src.usage AS src_usage,
                       dst.warehouse_id AS dst_wh, dst.usage AS dst_usage
                  FROM stock_valuation_layer svl
                  JOIN stock_move sm ON sm.id = svl.stock_move_id
                  JOIN stock_location src ON src.id = sm.location_id
                  JOIN stock_location dst ON dst.id = sm.location_dest_id
                 WHERE svl.company_id = %(company)s
                   AND svl.create_date < %(to_end)s
            ),
            attr AS (
                SELECT CASE WHEN value >= 0 THEN dst_wh ELSE src_wh END AS wh,
                       CASE WHEN value >= 0 THEN dst_usage ELSE src_usage END AS usage,
                       product_id, value, create_date
                  FROM v
            )
            SELECT wh, product_id,
                   SUM(CASE WHEN create_date < %(from)s THEN value ELSE 0 END) AS val_open,
                   SUM(CASE WHEN create_date >= %(from)s AND value > 0 THEN value ELSE 0 END) AS val_in,
                   SUM(CASE WHEN create_date >= %(from)s AND value < 0 THEN -value ELSE 0 END) AS val_out
              FROM attr
             WHERE usage = 'internal' AND wh = ANY(%(wh)s)
             GROUP BY wh, product_id
        """, {'company': company_id, 'from': from_dt, 'to_end': to_end_dt, 'wh': wh_ids})
        res = {}
        for wh, pid, v_open, v_in, v_out in self.env.cr.fetchall():
            res[(wh, pid)] = {
                'val_open': v_open, 'val_in': v_in, 'val_out': v_out,
                'val_close': v_open + v_in - v_out,
            }
        return res

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------
    def _write_xlsx(self, rows):
        import xlsxwriter
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = wb.add_worksheet('NXT')
        f_hdr = wb.add_format({'bold': True, 'bg_color': '#FFFF00',
                               'border': 1, 'align': 'center', 'valign': 'vcenter'})
        f_txt = wb.add_format({'border': 1})
        f_num = wb.add_format({'border': 1, 'num_format': '#,##0.##'})
        for col, (_key, label) in enumerate(NXT_COLUMNS):
            ws.write(0, col, label, f_hdr)
        for r, row in enumerate(rows, start=1):
            for col, (key, _label) in enumerate(NXT_COLUMNS):
                value = row.get(key, '')
                if key in NUM_KEYS:
                    ws.write_number(r, col, value or 0, f_num)
                else:
                    ws.write(r, col, value, f_txt)
        ws.freeze_panes(1, 0)
        wb.close()
        buf.seek(0)
        return buf.read()
