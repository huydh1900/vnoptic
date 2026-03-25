# -*- coding: utf-8 -*-
import logging
import json
import os
import time
import random
import re
import unicodedata
from datetime import datetime
import requests
import urllib3
from collections import defaultdict
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..utils import lens_variant_utils

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_logger = logging.getLogger(__name__)
_SYNC_AUDIT_STORE = {}

class ProductSync(models.Model):
    _name = 'product.sync'
    _description = 'Product Synchronization'
    _order = 'last_sync_date desc'

    name = fields.Char('Tên đồng bộ', required=True, default='Đồng bộ sản phẩm')
    last_sync_date = fields.Datetime('Ngày đồng bộ cuối', readonly=True)
    sync_status = fields.Selection([
        ('never', 'Chưa đồng bộ'),
        ('in_progress', 'Đang đồng bộ'),
        ('success', 'Thành công'),
        ('error', 'Lỗi')])
    sync_log = fields.Text('Nhật ký', readonly=True)

    total_synced = fields.Integer('Tổng sản phẩm đã sync', readonly=True)
    total_failed = fields.Integer('Tổng thất bại', readonly=True)
    lens_count = fields.Integer('Sản phẩm Mắt', readonly=True)
    opts_count = fields.Integer('Sản phẩm Gọng', readonly=True)
    other_count = fields.Integer('Sản phẩm khác', readonly=True)

    progress = fields.Float('Tiến độ (%)', readonly=True, compute='_compute_progress')

    @api.depends('total_synced', 'total_failed')
    def _compute_progress(self):
        for record in self:
            total = record.total_synced + record.total_failed
            record.progress = (record.total_synced / total * 100) if total > 0 else 0

    def _init_sync_audit(self):
        """Initialize per-run audit context and attach a file handler.

        This keeps terminal logging intact while persisting logs to disk.
        """
        now = datetime.now()
        run_stamp = now.strftime('%Y-%m-%d_%H-%M-%S')

        module_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        base_dir = os.getenv('PRODUCT_SYNC_LOG_DIR') or os.path.join(module_root, 'logs', 'product_sync')
        os.makedirs(base_dir, exist_ok=True)

        text_log_path = os.path.join(base_dir, f'product_sync_{run_stamp}.log')
        error_json_path = os.path.join(base_dir, f'product_sync_errors_{run_stamp}.json')

        file_handler = logging.FileHandler(text_log_path, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
        _logger.addHandler(file_handler)

        _SYNC_AUDIT_STORE[self._sync_audit_key()] = {
            'run_stamp': run_stamp,
            'started_at': now.isoformat(),
            'text_log_path': text_log_path,
            'error_json_path': error_json_path,
            'file_handler': file_handler,
            'issues': [],
            'counts': {'input': 0, 'create': 0, 'update': 0, 'skip': 0, 'fail': 0},
            'counts_by_type': defaultdict(lambda: {'input': 0, 'create': 0, 'update': 0, 'skip': 0, 'fail': 0}),
            'error_type_counts': defaultdict(int),
            'field_counts': defaultdict(int),
            'source_value_counts': defaultdict(int),
        }

        _logger.info("[SYNC_AUDIT] Run started. text_log=%s error_json=%s", text_log_path, error_json_path)

    def _sync_audit_key(self):
        rec_id = self.id if len(self) == 1 and self.id else 0
        return (self._name, self.env.cr.dbname, id(self.env.cr), rec_id)

    def _get_sync_audit_ctx(self):
        return _SYNC_AUDIT_STORE.get(self._sync_audit_key())

    def _sync_audit_count(self, metric, product_type='unknown', amount=1):
        ctx = self._get_sync_audit_ctx()
        if not ctx or metric not in ctx['counts']:
            return
        ctx['counts'][metric] += amount
        ctx['counts_by_type'][product_type][metric] += amount

    def _extract_sync_identifiers(self, item=None, payload=None, product_tmpl=None):
        dto = (item or {}).get('productdto') if isinstance(item, dict) else {}
        if not isinstance(dto, dict):
            dto = {}

        rs_id = dto.get('id') or dto.get('externalId') or dto.get('cid')
        sku = (dto.get('cid') or '').strip() if isinstance(dto.get('cid'), str) else (dto.get('cid') or '')
        code = sku
        product_name = dto.get('fullname') or dto.get('name') or ''

        if isinstance(payload, dict):
            sku = sku or payload.get('default_code') or payload.get('sku') or ''
            code = code or payload.get('code') or payload.get('default_code') or ''
            product_name = product_name or payload.get('name') or ''

        if product_tmpl:
            sku = sku or (product_tmpl.default_code or '')
            code = code or (product_tmpl.default_code or '')
            product_name = product_name or (product_tmpl.name or '')

        return rs_id or None, sku or None, code or None, product_name or None

    def _sync_audit_record_issue(
        self,
        issue_kind,
        product_type,
        stage,
        item=None,
        payload=None,
        product_tmpl=None,
        field='unknown',
        source_value=None,
        normalized_value=None,
        error_type='UNKNOWN',
        error_message='',
    ):
        ctx = self._get_sync_audit_ctx()
        if not ctx:
            return

        rs_id, sku, code, product_name = self._extract_sync_identifiers(item=item, payload=payload, product_tmpl=product_tmpl)
        issue = {
            'timestamp': datetime.now().isoformat(),
            'issue_kind': issue_kind,
            'rs_id': rs_id,
            'product_type': product_type,
            'sku': sku,
            'code': code,
            'product_name': product_name,
            'stage': stage,
            'field': field,
            'source_value': source_value,
            'normalized_value': normalized_value,
            'error_type': error_type,
            'error_message': error_message,
        }
        ctx['issues'].append(issue)

        if issue_kind == 'skip':
            self._sync_audit_count('skip', product_type, 1)
        if issue_kind in ('error', 'fail'):
            self._sync_audit_count('fail', product_type, 1)

        ctx['error_type_counts'][error_type or 'UNKNOWN'] += 1
        ctx['field_counts'][field or 'unknown'] += 1
        sv_key = str(source_value) if source_value not in (None, '', False) else '<empty>'
        if len(sv_key) > 200:
            sv_key = sv_key[:200] + '...'
        ctx['source_value_counts'][sv_key] += 1

    def _sync_audit_top(self, data_dict, limit=10):
        return [
            {'value': key, 'count': count}
            for key, count in sorted(data_dict.items(), key=lambda pair: pair[1], reverse=True)[:limit]
        ]

    def _finalize_sync_audit(self, status='success'):
        ctx = self._get_sync_audit_ctx()
        if not ctx:
            return

        summary = {
            'status': status,
            'started_at': ctx['started_at'],
            'ended_at': datetime.now().isoformat(),
            'total_input': ctx['counts']['input'],
            'total_create': ctx['counts']['create'],
            'total_update': ctx['counts']['update'],
            'total_skip': ctx['counts']['skip'],
            'total_fail': ctx['counts']['fail'],
            'top_error_type': self._sync_audit_top(ctx['error_type_counts']),
            'top_field': self._sync_audit_top(ctx['field_counts']),
            'top_source_value': self._sync_audit_top(ctx['source_value_counts']),
            'counts_by_type': dict(ctx['counts_by_type']),
        }

        _logger.info("[SYNC_AUDIT][SUMMARY] status=%s input=%s create=%s update=%s skip=%s fail=%s",
                     summary['status'], summary['total_input'], summary['total_create'],
                     summary['total_update'], summary['total_skip'], summary['total_fail'])
        _logger.info("[SYNC_AUDIT][SUMMARY] top_error_type=%s", json.dumps(summary['top_error_type'], ensure_ascii=False))
        _logger.info("[SYNC_AUDIT][SUMMARY] top_field=%s", json.dumps(summary['top_field'], ensure_ascii=False))
        _logger.info("[SYNC_AUDIT][SUMMARY] top_source_value=%s", json.dumps(summary['top_source_value'], ensure_ascii=False))

        output_payload = {
            'summary': summary,
            'issues': ctx['issues'],
            'text_log_path': ctx['text_log_path'],
            'error_json_path': ctx['error_json_path'],
        }
        try:
            with open(ctx['error_json_path'], 'w', encoding='utf-8') as f:
                json.dump(output_payload, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            _logger.error("[SYNC_AUDIT] Cannot write error json file: %s", e)

        _logger.info("[SYNC_AUDIT] Run finished. text_log=%s error_json=%s",
                     ctx['text_log_path'], ctx['error_json_path'])

        handler = ctx.get('file_handler')
        if handler:
            _logger.removeHandler(handler)
            handler.close()
        _SYNC_AUDIT_STORE.pop(self._sync_audit_key(), None)

    @api.model
    def _load_env(self):
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            os.environ.setdefault(key.strip(), value.strip())
            except Exception as e:
                _logger.warning(f"Could not load .env file: {e}")

    @api.model
    def _get_api_config(self):
        self._load_env()
        
        base_url = os.getenv('SPRING_BOOT_BASE_URL')
        username = os.getenv('SPRINGBOOT_SERVICE_USERNAME')
        password = os.getenv('SPRINGBOOT_SERVICE_PASSWORD')

        # Kiểm tra nếu thiếu cấu hình bắt buộc
        if not all([base_url, username, password]):
            missing = []
            if not base_url: missing.append('SPRING_BOOT_BASE_URL')
            if not username: missing.append('SPRINGBOOT_SERVICE_USERNAME')
            if not password: missing.append('SPRINGBOOT_SERVICE_PASSWORD')
            raise UserError(_("Thiếu cấu hình môi trường bắt buộc: %s. "
                              "Vui lòng kiểm tra file .env") % ", ".join(missing))

        return {
            'base_url': base_url,
            'login_endpoint': os.getenv('API_LOGIN_ENDPOINT', '/api/auth/service-token'),
            'lens_endpoint': os.getenv('API_LENS_ENDPOINT', '/api/xnk/lens'),
            'lens_stock_endpoint': os.getenv('API_LENS_STOCK_ENDPOINT', '/api/warehouse/statistic/lens'),
            'opts_endpoint': os.getenv('API_OPTS_ENDPOINT', '/api/xnk/opts'),
            'types_endpoint': os.getenv('API_TYPES_ENDPOINT', '/api/xnk/types'),
            'service_username': username,
            'service_password': password,
            'ssl_verify': os.getenv('SSL_VERIFY', 'False').lower() == 'true',
            'login_timeout': int(os.getenv('LOGIN_TIMEOUT', '300')),
            'api_timeout': int(os.getenv('API_TIMEOUT', '9999')),
        }

    def _get_access_token(self):
        config = self._get_api_config()
        login_url = f"{config['base_url']}{config['login_endpoint']}"
        try:
            _logger.info(f"🔐 Getting token from: {login_url}")
            response = requests.post(
                login_url,
                json={'username': config['service_username'], 'password': config['service_password']},
                verify=config['ssl_verify'], timeout=config['login_timeout']
            )
            response.raise_for_status()
            token = response.json().get('token')
            if not token: raise UserError(_('Login failed: No token received'))
            return token
        except Exception as e:
            raise UserError(_(f"Authentication failed: {str(e)}"))

    def _make_session(self):
        """Tạo mới requests.Session (không cache trên self vì Odoo ORM không cho phép)."""
        from requests.adapters import HTTPAdapter
        session = requests.Session()
        session.mount('https://', HTTPAdapter(max_retries=0))
        session.mount('http://', HTTPAdapter(max_retries=0))
        return session

    def _fetch_paged_api(self, endpoint, token, page=0, size=100, max_retries=5, session=None):
        config = self._get_api_config()
        url = f"{config['base_url']}{endpoint}?page={page}&size={size}"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        for attempt in range(1, max_retries + 1):
            # Tạo session mới nếu chưa có hoặc sau khi retry
            _session = session if (session and attempt == 1) else self._make_session()
            try:
                response = _session.get(
                    url, headers=headers,
                    verify=config['ssl_verify'],
                    timeout=config['api_timeout']
                )
                response.raise_for_status()
                data = response.json()
                if endpoint == config.get('lens_endpoint'):
                    _logger.warning("========== LENS RAW JSON ==========")
                    _logger.warning("%s", response.text)
                    _logger.warning("===================================")
                return data
            except (requests.exceptions.ConnectTimeout,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.ConnectionError) as e:
                if attempt == max_retries:
                    raise UserError(_(f"API request failed after {max_retries} retries: {str(e)}"))
                wait = min(2 ** attempt + random.uniform(0, 2), 60)  # cap 60s
                _logger.warning(
                    f"⚠️ Timeout/Connection error trang {page} (lần {attempt}/{max_retries}). "
                    f"Thử lại sau {wait:.1f}s... Lỗi: {e}"
                )
                time.sleep(wait)
            except Exception as e:
                raise UserError(_(f"API request failed: {str(e)}"))

    def _fetch_all_items(self, endpoint, token, label, limit=None, page_delay=0.3):
        """Lấy toàn bộ dữ liệu phân trang với retry & delay giữa các trang.
        
        Args:
            page_delay: Giây tạm nghỉ giữa mỗi trang để tránh server quá tải (mặc định 0.3s).
        """
        items = []
        page = 0
        total_elements = 0
        config = self._get_api_config()
        log_lens_payload = os.getenv('LOG_LENS_PAYLOAD', 'False').lower() == 'true'
        
        _logger.info(f"🔍 Bắt đầu lấy dữ liệu {label} từ: {config['base_url']}{endpoint}")

        # Tạo session một lần duy nhất cho toàn bộ quá trình phân trang
        session = self._make_session()

        while True:
            res = self._fetch_paged_api(endpoint, token, page, 100, session=session)
            if log_lens_payload and label.lower() == 'lens':
                try:
                    _logger.info(
                        "🧾 Lens API payload (page %s): %s",
                        page,
                        json.dumps(res, ensure_ascii=True)
                    )
                except Exception as e:
                    _logger.warning(f"⚠️ Không log được payload Lens page {page}: {e}")
            
            if page == 0:
                debug_res = {k: v for k, v in res.items() if k != 'content'}
                _logger.info(f"🔍 Metadata API {label} (Trang 0): {debug_res}")
            
            content = res.get('content', [])
            if not content:
                break
            items.extend(content)
            
            total_elements = res.get('totalElements', 0)
            total_pages = res.get('totalPages', 1)
            
            _logger.info(
                f"📦 {label}: Trang {page + 1}/{total_pages} | "
                f"Lấy được {len(content)} bản ghi | Tổng: {len(items)}/{total_elements}"
            )

            # Cập nhật sync_log định kỳ (mỗi 10 trang) để UI hiển thị tiến độ
            if page % 10 == 0 and hasattr(self, 'id') and self.id:
                try:
                    self.write({'sync_log': f"Đang tải {label}: trang {page + 1}/{total_pages} ({len(items)}/{total_elements} bản ghi)..."})
                    self.env.cr.commit()
                except Exception:
                    pass
            
            if limit and len(items) >= limit:
                return items[:limit]
            
            page += 1
            if page >= total_pages:
                break

            # Nghỉ một chút giữa các trang để tránh connection timeout do quá tải
            if page_delay > 0:
                time.sleep(page_delay)
            
        if total_elements > len(items) and not limit:
            _logger.warning(
                f"⚠️ API báo có {total_elements} bản ghi {label} nhưng chỉ lấy được {len(items)}."
            )
            
        return items

    def _preload_all_data(self):
        _logger.info("📦 Pre-loading existing data...")
        cache = {'products': {}, 'categories': {}, 'suppliers': {}, 'taxes': {}, 'groups': {}, 'groups_by_id': {}, 'statuses': {}}
        
        # Currencies (ALL – kể cả inactive, vì Odoo 18 có VND mặc định nhưng inactive)
        cache['acc_currency'] = {}
        for cur in self.env['res.currency'].with_context(active_test=False).search_read(
            [], ['id', 'name', 'symbol', 'active']
        ):
            cache['acc_currency'][cur['name'].upper()] = cur['id']

        # Products
        for p in self.env['product.template'].search_read([('default_code', '!=', False)], ['id', 'default_code']):
            cache['products'][p['default_code']] = p['id']

        cache['lens_templates'] = {}
        for p in self.env['product.template'].search_read(
            [('lens_template_key', '!=', False)], ['id', 'lens_template_key']
        ):
            cache['lens_templates'][p['lens_template_key']] = p['id']
            
        # Categories
        for c in self.env['product.category'].search_read([], ['id', 'name', 'parent_id']):
            pid = c['parent_id'][0] if c['parent_id'] else False
            cache['categories'][(c['name'], pid)] = c['id']

        # Suppliers (prefer ref as official vendor code; keep compatibility with legacy code)
        for s in self.env['res.partner'].search_read([
            '|', ('ref', '!=', False), ('code', '!=', False)
        ], ['id', 'ref', 'code']):
            if s.get('ref'):
                cache['suppliers'][s['ref'].upper()] = s['id']
            if s.get('code'):
                cache['suppliers'][s['code'].upper()] = s['id']
            
        # Taxes (Purchase taxes only)
        for t in self.env['account.tax'].search_read([('type_tax_use', '=', 'purchase')], ['id', 'name']):
            cache['taxes'][t['name']] = t['id']

        # Statuses
        if 'product.status' in self.env:
            for s in self.env['product.status'].search_read([], ['id', 'name']):
                cache['statuses'][s['name'].upper()] = s['id']

        # Master Data Config
        MODELS = [
            ('brands', 'product.brand', 'code'),
            ('brands', 'product.brand', 'name'), # Fallback to name
            ('countries', 'product.country', 'code'),
            ('warranties', 'product.warranty', 'code'),
            ('groups', 'product.group', 'cid'),
            ('groups', 'product.group', 'name'),
            ('designs', 'product.design', 'name'),
            ('materials', 'product.material', 'cid'),   # Index CID trước (API dùng cid)
            ('materials', 'product.material', 'name'),  # Fallback theo name
            ('uvs', 'product.uv', 'cid'),
            ('coatings', 'product.coating', 'cid'),
            ('colors', 'product.cl', 'cid'),
            ('lens_indexes', 'product.lens.index', 'cid'),
            ('frames', 'product.frame', 'cid'),
            ('frame_types', 'product.frame.type', 'cid'),
            ('shapes', 'product.shape', 'cid'),
            ('ves', 'product.ve', 'cid'),
            ('temples', 'product.temple', 'cid'),
        ]
        # Chuẩn bị cache cho power, design, material
        cache['lens_powers'] = {'sph': {}, 'cyl': {}, 'add': {}}
        if 'product.lens.power' in self.env:
            for r in self.env['product.lens.power'].search_read([], ['id', 'value', 'type']):
                t = r['type']
                v = float(r['value'])
                cache['lens_powers'].setdefault(t, {})[v] = r['id']
        cache['lens_designs'] = {}
        if 'product.lens.design' in self.env:
            for r in self.env['product.lens.design'].search_read([], ['id', 'name']):
                cache['lens_designs'][r['name'].strip().lower()] = r['id']
        cache['lens_materials'] = {}
        if 'product.lens.material' in self.env:
            for r in self.env['product.lens.material'].search_read([], ['id', 'name']):
                cache['lens_materials'][r['name'].strip().lower()] = r['id']

        for key, model, _ in MODELS:
            if key not in cache: cache[key] = {}

        for key, model, field in MODELS:
            if model in self.env:
                for r in self.env[model].search_read([], ['id', field]):
                    val = r.get(field)
                    if val: cache[key][val.upper()] = r['id']
                    if model == 'product.group' and key == 'groups':
                        cache['groups_by_id'][r['id']] = r['id']

        # Also index uvs by name (fallback khi RS chỉ trả name, không có cid)
        if 'product.uv' in self.env:
            for r in self.env['product.uv'].search_read([], ['id', 'name']):
                nm = (r.get('name') or '').strip().upper()
                if nm:
                    cache['uvs'].setdefault(nm, r['id'])

        # Also index coatings by name
        if 'product.coating' in self.env:
            for r in self.env['product.coating'].search_read([], ['id', 'name']):
                nm = (r.get('name') or '').strip().upper()
                if nm:
                    cache['coatings'].setdefault(nm, r['id'])

        # Child Records (giữ lại opt)
        if 'product.opt' in self.env:
            cache['opt_records'] = {o['product_tmpl_id'][0]: o['id'] for o in self.env['product.opt'].search_read([], ['id', 'product_tmpl_id']) if o.get('product_tmpl_id')}

        # Also index colors by name for fallback (colorLensdto from API may have no cid)
        if 'product.cl' in self.env:
            for r in self.env['product.cl'].search_read([], ['id', 'name']):
                if r.get('name'):
                    cache['colors'].setdefault(r['name'].upper(), r['id'])

        # Accessory colors: product.color (KHÁC product.cl dành cho lens/opt)
        cache['acc_colors'] = {}
        if 'product.color' in self.env:
            for r in self.env['product.color'].search_read([], ['id', 'name', 'cid']):
                if r.get('cid'):
                    cache['acc_colors'][r['cid'].upper()] = r['id']
                if r.get('name'):
                    cache['acc_colors'].setdefault(r['name'].upper(), r['id'])

        # Accessory shapes (product.shape) — index thêm theo name ngoài cid
        if 'product.shape' in self.env:
            for r in self.env['product.shape'].search_read([], ['id', 'name']):
                if r.get('name'):
                    cache['shapes'].setdefault(r['name'].upper(), r['id'])

        # Accessory designs (product.design) — index thêm theo cid ngoài name
        if 'product.design' in self.env:
            for r in self.env['product.design'].search_read([], ['id', 'cid', 'name']):
                if r.get('cid'):
                    cache['designs'].setdefault(r['cid'].upper(), r['id'])

        return cache

    def _get_val(self, item, key, subkey='cid'):
        return (item.get(key) or {}).get(subkey)

    def _get_id(self, cache, key, val):
        return cache.get(key, {}).get(val.upper(), False) if val else False

    def _extract_rs_product_id(self, item):
        """Extract stable RS product identifier from payload.

        Priority: productdto.id -> productdto.externalId -> root id/externalId.
        Return string for robust persistence across mixed payload types.
        """
        dto = item.get('productdto') or {}
        for key in ('id', 'externalId'):
            value = dto.get(key)
            if value not in (None, ''):
                return str(value).strip()

        for key in ('id', 'externalId'):
            value = item.get(key)
            if value not in (None, ''):
                return str(value).strip()

        return False

    def _get_id_with_fallback(self, cache, key, dto):
        """Lookup id by cid first, then name as fallback.
        If not found and DTO has name, auto-create a product.cl record."""
        if not dto:
            return False
        cid = (dto.get('cid') or '').strip().upper()
        name = (dto.get('name') or '').strip()
        name_upper = name.upper()

        found = (cache.get(key, {}).get(cid) if cid else None) \
             or (cache.get(key, {}).get(name_upper) if name_upper else None)
        if found:
            return found

        # Auto-create product.cl record if we have at least a name
        if name and key == 'colors':
            try:
                vals = {'name': name}
                if cid:
                    vals['cid'] = cid
                rec = self.env['product.cl'].create(vals)
                rid = rec.id
                if cid:
                    cache.setdefault(key, {})[cid] = rid
                cache.setdefault(key, {})[name_upper] = rid
                _logger.info(f"✅ Auto-created product.cl cid={cid!r} name={name!r}")
                return rid
            except Exception as e:
                _logger.warning(f"⚠️ Không tạo được product.cl cid={cid!r} name={name!r}: {e}")
        return False

    # Mapping: cache key → (model name) cho các master data opt
    _MASTER_MODEL_MAP = {
        'frames':      'product.frame',
        'frame_types': 'product.frame.type',
        'shapes':      'product.shape',
        'ves':         'product.ve',
        'temples':     'product.temple',
        'materials':   'product.material',
    }

    def _get_or_create_master(self, cache, cache_key, dto):
        """Tra cứu id master data từ cache theo cid, sau đó fallback sang name.
        Nếu không tìm thấy, tự động tạo mới bản ghi trong Odoo và cập nhật cache.
        Áp dụng cho: frames, frame_types, shapes, ves, temples, materials.
        """
        if not dto or not isinstance(dto, dict):
            return False

        cid = (dto.get('cid') or '').strip().upper()
        name = (dto.get('name') or '').strip()
        name_upper = name.upper()

        # 1. Tra cứu cache: cid trước, name sau
        found = (cache.get(cache_key, {}).get(cid) if cid else None) \
             or (cache.get(cache_key, {}).get(name_upper) if name_upper else None)
        if found:
            return found

        # 2. Auto-create nếu không tìm thấy
        model_name = self._MASTER_MODEL_MAP.get(cache_key)
        if not model_name or not (name or cid):
            _logger.debug(f"⚠️ _get_or_create_master: không tìm thấy và không tạo được [{cache_key}] cid={cid!r} name={name!r}")
            return False

        try:
            vals = {'name': name or cid}
            if cid:
                vals['cid'] = cid
            with self.env.cr.savepoint():
                rec = self.env[model_name].create(vals)
            rid = rec.id
            if cid:
                cache.setdefault(cache_key, {})[cid] = rid
            if name_upper:
                cache.setdefault(cache_key, {})[name_upper] = rid
            _logger.info(f"✅ Auto-created [{model_name}] cid={cid!r} name={name!r} → id={rid}")
            return rid
        except Exception as e:
            _logger.warning(f"⚠️ Không tạo được [{model_name}] cid={cid!r} name={name!r}: {e}")
            return False

    def _color_dto_to_list(self, dto):
        """Chuyển single color DTO (dict) thành list để dùng với _resolve_m2m_ids."""
        if not dto:
            return []
        if isinstance(dto, dict):
            return [dto]
        if isinstance(dto, list):
            return dto
        return []

    def _get_or_create_color_by_string(self, color_str, cache):
        """Tra cứu hoặc tạo mới product.cl từ plain string (ví dụ: 'BLACK+GUN')."""
        if not color_str or not isinstance(color_str, str):
            return False
        name = color_str.strip()
        name_upper = name.upper()
        rid = cache.get('colors', {}).get(name_upper)
        if rid:
            return rid
        try:
            with self.env.cr.savepoint():
                rec = self.env['product.cl'].create({'name': name})
            cache.setdefault('colors', {})[name_upper] = rec.id
            _logger.info(f"✅ Auto-created product.cl name={name!r} id={rec.id}")
            return rec.id
        except Exception as e:
            _logger.warning(f"⚠️ Không tạo được product.cl name={name!r}: {e}")
            return False

    def _resolve_color_string_to_m2m(self, color_str, cache, log_label=''):
        """Chuyển plain color string → M2M command cho opt_color_*_ids.
        API trả về 'BLACK+GUN' thay vì DTO → cần xử lý riêng.
        """
        if not color_str or not isinstance(color_str, str):
            return [(5, 0, 0)]
        rid = self._get_or_create_color_by_string(color_str, cache)
        if rid:
            _logger.debug(f"🔍 [{log_label}]: map string {color_str!r} → cl.id={rid}")
            return [(6, 0, [rid])]
        return [(5, 0, 0)]

    def _get_or_create(self, cache, cache_key, model_name, dto):
        if not dto: return False
        cid = dto.get('cid')
        name = dto.get('name')
        if not cid: return False
        
        # Check cache
        cached_id = cache.get(cache_key, {}).get(cid.upper())
        if cached_id: return cached_id
        
        # Check name fallback in cache (for brands)
        if name and name.upper() in cache.get(cache_key, {}):
            return cache[cache_key][name.upper()]
            
        # Create
        try:
            vals = {'name': name or cid, 'code': cid}
           
            
            rec = self.env[model_name].create(vals)
            new_id = rec.id
            if cid: cache[cache_key][cid.upper()] = new_id
            return new_id
        except Exception as e:
            _logger.error(f"Failed to create {model_name} for {cid}: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # ACCESSORY-ONLY helper — KHÔNG dùng cho lens/opt
    # ─────────────────────────────────────────────────────────────────────────
    def _acc_get_or_create_ref(
        self, field, raw_input, cache, cache_key, model_name,
        name_field='name', code_field='cid', required=False, sku='N/A'
    ):
        """Safe get-or-create cho các field liên kết của accessory.
        Hoàn toàn độc lập với logic lens/opt. Chỉ gọi từ _process_accessory_batch.

        Returns:
            (id_or_False, error_str_or_None)
        """
        import traceback as _tb_acc

        action = 'init'
        input_repr = repr(raw_input)[:80]

        # ── 1. Chuẩn hoá input ────────────────────────────────────────────────
        EMPTY_VALS = (None, '', 'N/A', 'n/a', 'NA', 'na')
        if raw_input in EMPTY_VALS:
            if required:
                msg = "input is None/empty/N/A"
                _logger.warning(
                    "[ACC_SYNC][REF] field=%s input=%s action=skip result=None error=%s sku=%s",
                    field, input_repr, msg, sku
                )
                return False, msg
            _logger.debug(
                "[ACC_SYNC][REF] field=%s input=empty action=skip sku=%s", field, sku
            )
            return False, None

        if isinstance(raw_input, dict):
            cid = (raw_input.get('cid') or raw_input.get('code') or '').strip()
            name = (raw_input.get('name') or raw_input.get('value') or '').strip()
        elif isinstance(raw_input, str):
            cid = raw_input.strip().upper()
            name = raw_input.strip()
        else:
            cid = str(raw_input).strip().upper()
            name = str(raw_input).strip()

        if not cid and not name:
            if required:
                msg = "empty cid and name after normalise"
                _logger.warning(
                    "[ACC_SYNC][REF] field=%s input=%s action=skip result=None error=%s sku=%s",
                    field, input_repr, msg, sku
                )
                return False, msg
            return False, None

        try:
            # ── 2. Tìm trong cache ─────────────────────────────────────────────
            action = 'cache'
            rid = None
            if cid:
                rid = cache.get(cache_key, {}).get(cid.upper())
            if not rid and name:
                rid = cache.get(cache_key, {}).get(name.upper())
            if rid:
                _logger.debug(
                    "[ACC_SYNC][REF] field=%s input=%s action=cache result=%s sku=%s",
                    field, input_repr, rid, sku
                )
                return rid, None

            # ── 3. Tìm trong DB ────────────────────────────────────────────────
            action = 'search'
            model_fields = self.env[model_name]._fields
            domain = []
            if cid and code_field in model_fields:
                domain = [(code_field, '=', cid)]
            elif name:
                domain = [(name_field, '=', name)]
            if domain:
                # Với res.currency: search cả record inactive (VND mặc định của Odoo bị inactive)
                env_search = (
                    self.env[model_name].with_context(active_test=False)
                    if model_name == 'res.currency'
                    else self.env[model_name]
                )
                rec = env_search.search(domain, limit=1)
                if not rec and cid and name and name_field in model_fields:
                    rec = env_search.search(
                        [(name_field, '=', name)], limit=1
                    )
                # Nếu currency đang inactive → kích hoạt để dùng được
                if rec and model_name == 'res.currency' and not rec.active:
                    try:
                        rec.with_context(tracking_disable=True).write({'active': True})
                        _logger.info(
                            '[ACC_SYNC][REF] field=%s input=%s action=activate_currency '
                            'result=%s sku=%s', field, input_repr, rec.id, sku
                        )
                    except Exception as _act_err:
                        _logger.warning(
                            '[ACC_SYNC][REF] field=%s cannot activate currency %s: %s',
                            field, cid or name, _act_err
                        )
                if rec:
                    rid = rec.id
                    if cid:
                        cache.setdefault(cache_key, {})[cid.upper()] = rid
                    if name:
                        cache.setdefault(cache_key, {})[name.upper()] = rid
                    _logger.info(
                        "[ACC_SYNC][REF] field=%s input=%s action=search result=%s sku=%s",
                        field, input_repr, rid, sku
                    )
                    return rid, None

            # ── 4. Tạo mới ────────────────────────────────────────────────────
            action = 'create'
            create_vals = {name_field: name or cid}
            if (code_field and code_field != name_field
                    and code_field in model_fields and cid):
                create_vals[code_field] = cid
            # Nếu tạo currency thì luôn truyền symbol (required not-null)
            if model_name == 'res.currency':
                create_vals['symbol'] = cid or name or 'VND'

            try:
                with self.env.cr.savepoint():
                    rec = self.env[model_name].create(create_vals)
                    rid = rec.id
                if cid:
                    cache.setdefault(cache_key, {})[cid.upper()] = rid
                if name:
                    cache.setdefault(cache_key, {})[name.upper()] = rid
                _logger.info(
                    "[ACC_SYNC][REF] field=%s input=%s action=create result=%s sku=%s",
                    field, input_repr, rid, sku
                )
                return rid, None

            except Exception as create_err:
                err_str = str(create_err).lower()
                is_dup = any(k in err_str for k in ('unique', 'duplicate', 'integrity'))
                if is_dup:
                    _logger.warning(
                        "[ACC_SYNC][REF] field=%s input=%s action=create "
                        "error=integrity/duplicate → retry_search sku=%s",
                        field, input_repr, sku
                    )
                    # Retry search after integrity error (another process created it)
                    retry_dom = []
                    if cid and code_field in model_fields:
                        retry_dom = [(code_field, '=', cid)]
                    elif name:
                        retry_dom = [(name_field, '=', name)]
                    if retry_dom:
                        rec = self.env[model_name].search(retry_dom, limit=1)
                        if rec:
                            rid = rec.id
                            if cid:
                                cache.setdefault(cache_key, {})[cid.upper()] = rid
                            if name:
                                cache.setdefault(cache_key, {})[name.upper()] = rid
                            _logger.info(
                                "[ACC_SYNC][REF] field=%s input=%s "
                                "action=search_retry result=%s sku=%s",
                                field, input_repr, rid, sku
                            )
                            return rid, None

                # Không recover được
                if required:
                    _logger.warning(
                        "[ACC_SYNC][REF] field=%s input=%s action=%s "
                        "result=None error=%s sku=%s",
                        field, input_repr, action, create_err, sku
                    )
                    return False, str(create_err)
                else:
                    _logger.warning(
                        "[ACC_SYNC][REF] field=%s input=%s action=%s "
                        "result=None error=%s sku=%s (optional→set None)",
                        field, input_repr, action, create_err, sku
                    )
                    return False, None

        except Exception as outer_err:
            _logger.warning(
                "[ACC_SYNC][REF] field=%s input=%s action=%s "
                "result=None error=%s sku=%s",
                field, input_repr, action, outer_err, sku
            )
            if required:
                return False, str(outer_err)
            return False, None

    def _resolve_uv_id(self, uv_dto, cache):
        """Get-or-create product.uv từ uvdto. Hỗ trợ cả cid lẫn name fallback."""
        if not uv_dto:
            return False
        if isinstance(uv_dto, str):
            uv_dto = {'name': uv_dto.strip()}

        cid = (uv_dto.get('cid') or '').strip().upper()
        name = (uv_dto.get('name') or uv_dto.get('value') or cid or '').strip()

        # Tìm trong cache theo cid trước, rồi name
        if cid:
            found = cache.get('uvs', {}).get(cid)
            if found:
                return found
        if name:
            found = cache.get('uvs', {}).get(name.upper())
            if found:
                return found

        # Tìm trong DB
        domain = [('cid', '=', cid)] if cid else ([('name', '=', name)] if name else [])
        rec = self.env['product.uv'].search(domain, limit=1) if domain else False
        if not rec and cid and name:
            rec = self.env['product.uv'].search([('name', '=', name)], limit=1)
        if rec:
            if cid:
                cache.setdefault('uvs', {})[cid] = rec.id
            if name:
                cache.setdefault('uvs', {})[name.upper()] = rec.id
            return rec.id

        # Auto-create nếu có name
        if not name:
            return False
        try:
            create_vals = {'name': name}
            if cid and 'cid' in self.env['product.uv']._fields:
                create_vals['cid'] = cid
            with self.env.cr.savepoint():
                rec = self.env['product.uv'].create(create_vals)
            if cid:
                cache.setdefault('uvs', {})[cid] = rec.id
            cache.setdefault('uvs', {})[name.upper()] = rec.id
            _logger.info("✅ Auto-created product.uv cid=%s name=%s id=%s", cid or None, name, rec.id)
            return rec.id
        except Exception as e:
            _logger.warning("⚠️ Không tạo được product.uv cid=%s name=%s: %s", cid or None, name, e)
            return False

    def _resolve_opt_material_dtos(self, item, key_variants, cache, log_label=''):
        """Giống _resolve_m2m_ids nhưng thử nhiều key variant từ API (camelCase khác nhau).
        key_variants: list các key cần thử theo thứ tự ưu tiên.
        """
        raw = None
        for key in key_variants:
            raw = item.get(key)
            if raw is not None:
                _logger.debug(f"🔍 [{log_label}]: tìm thấy key={key!r}, value={raw!r}")
                break

        if not raw:
            _logger.debug(f"🔍 [{log_label}]: API không trả dữ liệu (thử: {key_variants})")
            return [(5, 0, 0)]

        # Nếu API trả về single dict thay vì list → bọc thành list
        if isinstance(raw, dict):
            raw = [raw]
        elif not isinstance(raw, list):
            _logger.debug(f"⚠️ [{log_label}]: kiểu dữ liệu không mong đợi: {type(raw)}")
            return [(5, 0, 0)]

        return self._resolve_m2m_ids(raw, 'materials', cache,
                                     model_name='product.material', log_label=log_label)

    def _resolve_lens_coatings(self, item, cache):
        coating_ids = []
        coating_codes = []
        raw_coatings = (
            item.get('coatingsdto')    # API thực tế: coatingsdto (s trước dto)
            or item.get('coatingdtos')
            or item.get('coatingDtos')
            or item.get('coatingDTOs')
            or item.get('coatingsdtos')
            or item.get('coatingdto')
            or item.get('coatingDto')
            or item.get('coatingDTO')
            or item.get('coatings')
            or item.get('coating')
            or item.get('coatingCode')
            or item.get('coatingName')
            or []
        )

        normalized = []
        if isinstance(raw_coatings, dict):
            normalized = [raw_coatings]
        elif isinstance(raw_coatings, str):
            # e.g. "HMC, BlueCut"
            normalized = [{'name': c.strip()} for c in raw_coatings.split(',') if c.strip()]
        elif isinstance(raw_coatings, (list, tuple)):
            for item_c in raw_coatings:
                if isinstance(item_c, dict):
                    normalized.append(item_c)
                elif isinstance(item_c, str) and item_c.strip():
                    normalized.append({'name': item_c.strip()})

        for c in normalized:
            c_cid = (c.get('cid') or '').strip().upper()
            c_name = (c.get('name') or '').strip()
            if c_cid:
                coating_codes.append(c_cid)
            elif c_name:
                coating_codes.append(c_name.upper())

            coating_id = False
            if c_cid:
                coating_id = cache.get('coatings', {}).get(c_cid)
            if not coating_id and c_name:
                coating_id = cache.get('coatings', {}).get(c_name.upper())

            if not coating_id and (c_cid or c_name):
                # Fallback DB lookup (cache có thể stale nếu data mới được tạo bên ngoài sync)
                domain = []
                if c_cid:
                    domain = [('cid', '=', c_cid)]
                elif c_name:
                    domain = [('name', '=', c_name)]
                found = self.env['product.coating'].search(domain, limit=1) if domain else False
                if found:
                    coating_id = found.id
                    if c_cid:
                        cache.setdefault('coatings', {})[c_cid] = coating_id
                    if c_name:
                        cache.setdefault('coatings', {})[c_name.upper()] = coating_id

            if not coating_id and c_name:
                # Tạo mới coating nếu RS chỉ trả name (đưa vào lens_coating_ids)
                try:
                    create_vals = {'name': c_name}
                    if c_cid and 'cid' in self.env['product.coating']._fields:
                        create_vals['cid'] = c_cid
                    with self.env.cr.savepoint():
                        rec = self.env['product.coating'].create(create_vals)
                    coating_id = rec.id
                    if c_cid:
                        cache.setdefault('coatings', {})[c_cid] = coating_id
                    cache.setdefault('coatings', {})[c_name.upper()] = coating_id
                    _logger.info("✅ Auto-created product.coating cid=%s name=%s", c_cid or None, c_name)
                except Exception as e:
                    _logger.warning("⚠️ Không tạo được product.coating cid=%s name=%s: %s", c_cid or None, c_name, e)

            if coating_id:
                coating_ids.append(coating_id)

        if not normalized:
            _logger.info("🔎 _resolve_lens_coatings: no coating payload found in known keys")

        return coating_ids, coating_codes

    def _build_lens_template_key(self, item, coating_codes):
        dto = item.get('productdto') or {}
        cid = (dto.get('cid') or '').strip()
        index_code = (self._get_val(item, 'indexdto') or '').strip()
        material_code = (item.get('material') or '').strip()
        diameter = str(item.get('diameter') or '').replace('mm', '').replace('MM', '').strip()
        brand_code = (dto.get('tmdto') or {}).get('cid') or (dto.get('tmdto') or {}).get('name') or ''

        return lens_variant_utils.build_lens_template_key(
            cid, index_code, material_code, coating_codes, diameter, brand_code
        )

    def _cleanup_lens_template_variants(self, tmpl):
        """Chuẩn hoá lens template: xóa attribute lines và giữ 1 variant duy nhất."""
        if not tmpl:
            return

        # 1) Xóa toàn bộ thuộc tính biến thể (SPH/CYL/ADD cũ)
        if tmpl.attribute_line_ids:
            attr_count = len(tmpl.attribute_line_ids)
            tmpl.with_context(tracking_disable=True).write({
                'attribute_line_ids': [(5, 0, 0)]
            })
            _logger.info("🧹 Lens cleanup tmpl=%s: removed attribute lines=%s", tmpl.id, attr_count)

        # 2) Giữ đúng 1 variant
        variants = tmpl.product_variant_ids.sorted('id')
        if len(variants) <= 1:
            return

        keep_variant = tmpl.product_variant_id or variants[0]
        extra_variants = variants - keep_variant
        if not extra_variants:
            return

        try:
            extra_count = len(extra_variants)
            extra_variants.with_context(tracking_disable=True, active_test=False).unlink()
            _logger.info(
                "🧹 Lens cleanup tmpl=%s: removed extra variants=%s keep=%s",
                tmpl.id, extra_count, keep_variant.id
            )
        except Exception as e:
            _logger.warning(
                "⚠️ Lens cleanup tmpl=%s: cannot unlink extra variants (%s). Error: %s",
                tmpl.id, len(extra_variants), e
            )

    def _get_or_create_lens_template(self, item, cache, return_action=False):
        coating_ids, coating_codes = self._resolve_lens_coatings(item, cache)
        template_key = self._build_lens_template_key(item, coating_codes)
        tmpl_id = cache.get('lens_templates', {}).get(template_key)

        vals, _ = self._prepare_base_vals(
            item, cache, 'lens',
            coating_ids=coating_ids,
            lens_template_key=template_key
        )

        if tmpl_id:
            tmpl = self.env['product.template'].browse(tmpl_id)
            _logger.info(
                "📝 [LENS UPDATE id=%s] uv=%s | coating=%s | cl_hmc=%s | cl_pho=%s | cl_tint=%s",
                tmpl_id,
                vals.get('lens_uv_id', 'SKIPPED'),
                vals.get('lens_coating_ids', 'SKIPPED'),
                vals.get('lens_cl_hmc_id', 'SKIPPED'),
                vals.get('lens_cl_pho_id', 'SKIPPED'),
                vals.get('lens_cl_tint_id', 'SKIPPED'),
            )
            seller_payloads = self._extract_seller_payloads(vals)
            tmpl.write(vals)
            self._upsert_supplierinfo_payloads(tmpl, seller_payloads)
            self._cleanup_lens_template_variants(tmpl)
            _logger.info(
                "🔍 Lens [UPDATE] %s | material=%s | index=%s | coatings=%s | design1=%s",
                tmpl.name,
                tmpl.lens_material_id.name if tmpl.lens_material_id else None,
                tmpl.lens_index_id.name if tmpl.lens_index_id else None,
                ', '.join(tmpl.lens_coating_ids.mapped('name')) or None,
                tmpl.lens_design1_id.name if tmpl.lens_design1_id else None,
            )
            return (tmpl, 'update') if return_action else tmpl

        _logger.info(
            "📝 [LENS CREATE] uv=%s | coating=%s | cl_hmc=%s | cl_pho=%s | cl_tint=%s",
            vals.get('lens_uv_id', 'SKIPPED'),
            vals.get('lens_coating_ids', 'SKIPPED'),
            vals.get('lens_cl_hmc_id', 'SKIPPED'),
            vals.get('lens_cl_pho_id', 'SKIPPED'),
            vals.get('lens_cl_tint_id', 'SKIPPED'),
        )
        seller_payloads = self._extract_seller_payloads(vals)
        tmpl = self.env['product.template'].with_context(tracking_disable=True).create(vals)
        self._upsert_supplierinfo_payloads(tmpl, seller_payloads)
        self._cleanup_lens_template_variants(tmpl)
        cache.setdefault('lens_templates', {})[template_key] = tmpl.id
        if tmpl.default_code:
            cache['products'][tmpl.default_code] = tmpl.id
        _logger.info(
            "🔍 Lens [CREATE] %s | material=%s | index=%s | coatings=%s | design1=%s",
            tmpl.name,
            tmpl.lens_material_id.name if tmpl.lens_material_id else None,
            tmpl.lens_index_id.name if tmpl.lens_index_id else None,
            ', '.join(tmpl.lens_coating_ids.mapped('name')) or None,
            tmpl.lens_design1_id.name if tmpl.lens_design1_id else None,
        )
        return (tmpl, 'create') if return_action else tmpl

    def _get_default_stock_location(self):
        # Prefer warehouse stock location for current company
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if warehouse and warehouse.lot_stock_id:
            return warehouse.lot_stock_id

        # Fallback to any internal location for current company
        return self.env['stock.location'].search([
            ('usage', '=', 'internal'),
            '|', ('company_id', '=', self.env.company.id), ('company_id', '=', False)
        ], limit=1)

    def _fetch_lens_stock(self, token, cfg):
        # Fetch stock snapshot from RS; no processing here
        session = self._make_session()
        url = f"{cfg['base_url']}{cfg['lens_stock_endpoint']}"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        try:
            response = session.get(
                url, headers=headers,
                verify=cfg['ssl_verify'],
                timeout=cfg['api_timeout']
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and 'content' in data:
                return data.get('content') or []
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            _logger.warning(f"⚠️ Không lấy được tồn kho lens: {e}")
            return []

    def _find_attribute_value(self, attr_name, value_name):
        attribute = self.env['product.attribute'].search([
            ('name', '=', attr_name)
        ], limit=1)
        if not attribute:
            return False

        return self.env['product.attribute.value'].search([
            ('attribute_id', '=', attribute.id),
            ('name', '=', value_name),
        ], limit=1)

    def _get_lens_variant(self, template, sph, cyl, add_val=None):
        sph_val = lens_variant_utils.format_power_value(sph)
        cyl_val = lens_variant_utils.format_power_value(cyl)
        if not sph_val or not cyl_val:
            return False

        add_fmt = lens_variant_utils.format_power_value(add_val) if add_val not in (None, '', False) else False

        val_sph = self._find_attribute_value('SPH', sph_val)
        val_cyl = self._find_attribute_value('CYL', cyl_val)
        if not val_sph or not val_cyl:
            return False

        value_ids = [val_sph.id, val_cyl.id]
        if add_fmt:
            val_add = self._find_attribute_value('ADD', add_fmt)
            if not val_add:
                return False
            value_ids.append(val_add.id)

        return lens_variant_utils.find_variant_by_values(template, value_ids)

    def _build_lens_template_key_from_stock(self, rec):
        coating_raw = rec.get('coating') or rec.get('coatings') or rec.get('coatingCodes') or []
        if isinstance(coating_raw, str):
            coating_codes = [c.strip() for c in coating_raw.split(',') if c.strip()]
        else:
            coating_codes = [str(c).strip() for c in coating_raw if str(c).strip()]

        return lens_variant_utils.build_lens_template_key(
            rec.get('cid') or rec.get('CID') or '',
            rec.get('index') or rec.get('Index') or '',
            rec.get('material') or rec.get('Material') or '',
            coating_codes,
            rec.get('diameter') or rec.get('Diameter') or '',
            rec.get('brand') or rec.get('Brand') or ''
        )

    def _sync_lens_stock(self, token, cfg, cache):
        # Update stock.quant for template default variant only (aggregate by template key)
        records = self._fetch_lens_stock(token, cfg)
        total = len(records)
        updated = 0
        skipped = 0
        missing_template = 0
        missing_variant = 0

        location = self._get_default_stock_location()
        if not location:
            _logger.warning("⚠️ Không tìm thấy internal stock location để cập nhật tồn kho lens.")
            return

        _logger.info(f"📦 Lens stock records: {total}")

        qty_by_template = defaultdict(int)
        for rec in records:
            try:
                try:
                    qty_val = int(float(rec.get('quantity') or 0))
                except (TypeError, ValueError):
                    qty_val = 0
                template_key = self._build_lens_template_key_from_stock(rec)
                if not template_key:
                    continue
                qty_by_template[template_key] += qty_val
            except Exception as e:
                _logger.warning(f"⚠️ Lỗi xử lý record tồn kho lens: {e}")

        for template_key, qty_val in qty_by_template.items():
            try:
                tmpl_id = cache.get('lens_templates', {}).get(template_key)
                if not tmpl_id:
                    tmpl = self.env['product.template'].search([
                        ('lens_template_key', '=', template_key)
                    ], limit=1)
                    tmpl_id = tmpl.id if tmpl else False

                if not tmpl_id:
                    missing_template += 1
                    continue

                tmpl = self.env['product.template'].browse(tmpl_id)
                variant = tmpl.product_variant_id
                if not variant:
                    missing_variant += 1
                    continue

                quant = self.env['stock.quant'].search([
                    ('product_id', '=', variant.id),
                    ('location_id', '=', location.id)
                ], limit=1)

                if quant:
                    if float(quant.quantity) == qty_val:
                        skipped += 1
                        continue
                    quant.write({'quantity': qty_val})
                else:
                    self.env['stock.quant'].create({
                        'product_id': variant.id,
                        'location_id': location.id,
                        'quantity': qty_val,
                    })
                updated += 1
            except Exception as e:
                _logger.warning(f"⚠️ Lỗi cập nhật tồn kho lens: {e}")

        _logger.info(
            "✅ Lens stock sync done: updated=%s, skipped=%s, missing_variant=%s, missing_template=%s",
            updated, skipped, missing_variant, missing_template
        )

    def _normalize_uom_token(self, text):
        """Normalize unit text for resilient matching (strip accents + lowercase)."""
        value = (text or '').strip().lower()
        if not value:
            return ''
        normalized = unicodedata.normalize('NFKD', value)
        return ''.join(ch for ch in normalized if not unicodedata.combining(ch))

    def _extract_uom_name_from_payload(self, item, dto):
        """Extract unit/UoM text from RS payload across known key variants."""

        def _coerce_name(raw):
            if raw in (None, '', False):
                return False
            if isinstance(raw, dict):
                for key in ('name', 'cid', 'code', 'value', 'label'):
                    val = raw.get(key)
                    if val not in (None, '', False):
                        return str(val).strip()
                return False
            if isinstance(raw, (list, tuple)) and raw:
                return _coerce_name(raw[0])
            return str(raw).strip()

        keys = (
            'unit', 'unitName', 'unit_name',
            'uom', 'uomName', 'uom_name',
            'unitDTO', 'unitDto', 'uomDTO', 'uomDto',
        )

        for source in (dto, item):
            for key in keys:
                value = _coerce_name(source.get(key))
                if value:
                    return value
        return False

    def _resolve_rs_uom_id(self, item, dto, cache):
        """Resolve RS unit string to standard uom.uom id; return False if unresolved."""
        unit_name = self._extract_uom_name_from_payload(item, dto)
        if not unit_name:
            return False

        uom_cache = cache.setdefault('uom_by_name', {})
        cache_key = unit_name.upper()
        if cache_key in uom_cache:
            return uom_cache[cache_key]

        uom_model = self.env['uom.uom'].with_context(active_test=False)
        uom = uom_model.search([('name', '=', unit_name)], limit=1)
        if not uom:
            uom = uom_model.search([('name', 'ilike', unit_name)], limit=1)

        # Common aliases used by RS/business users.
        if not uom:
            alias_xmlid_map = {
                'cai': 'uom.product_uom_unit',
                'chiec': 'uom.product_uom_unit',
                'piece': 'uom.product_uom_unit',
                'pcs': 'uom.product_uom_unit',
                'unit': 'uom.product_uom_unit',
                'met': 'uom.product_uom_meter',
                'meter': 'uom.product_uom_meter',
                'm': 'uom.product_uom_meter',
            }
            normalized = self._normalize_uom_token(unit_name)
            xmlid = alias_xmlid_map.get(normalized)
            if xmlid:
                uom = self.env.ref(xmlid, raise_if_not_found=False)

        if not uom:
            _logger.warning("⚠️ Không resolve được đơn vị từ RS: %r. Bỏ qua map uom_id.", unit_name)
            uom_cache[cache_key] = False
            return False

        if not uom.active:
            try:
                uom.write({'active': True})
            except Exception as e:
                _logger.warning("⚠️ Không kích hoạt được UoM %s (%s): %s", uom.name, uom.id, e)

        uom_cache[cache_key] = uom.id
        return uom.id

    def _rs_pick(self, source, keys, skip_placeholder=False):
        """Return first non-empty value from dict using alias key list."""
        if not isinstance(source, dict):
            return False
        for key in keys:
            value = source.get(key)
            if value not in (None, '', False):
                if skip_placeholder and self._is_placeholder_value(value):
                    continue
                return value
        return False

    def _is_supplier_sync_debug_enabled(self, supplier_ref=''):
        """Enable focused supplier sync logs via env flags.

        LOG_RS_SUPPLIER_SYNC=True enables logs.
        LOG_RS_SUPPLIER_TARGET_REF=5017 narrows to a specific supplier ref.
        SUPPLIER_SYNC_DEBUG=1 and SUPPLIER_SYNC_DEBUG_SUPPLIER_REFS=5017 are also supported.
        """
        log_rs_flag = os.getenv('LOG_RS_SUPPLIER_SYNC', 'False').lower() == 'true'
        debug_flag = os.getenv('SUPPLIER_SYNC_DEBUG', '0').strip().lower() in ('1', 'true', 'yes', 'on')
        if not (log_rs_flag or debug_flag):
            return False

        target_ref = (os.getenv('LOG_RS_SUPPLIER_TARGET_REF') or '').strip().upper()
        target_refs_csv = (os.getenv('SUPPLIER_SYNC_DEBUG_SUPPLIER_REFS') or '').strip().upper()
        target_refs = set()
        if target_ref:
            target_refs.add(target_ref)
        if target_refs_csv:
            target_refs.update([ref.strip() for ref in target_refs_csv.split(',') if ref and ref.strip()])

        if not target_refs:
            return True
        return (supplier_ref or '').strip().upper() in target_refs

    def _log_supplier_sync(self, supplier_ref, message, *args):
        if self._is_supplier_sync_debug_enabled(supplier_ref):
            _logger.info("[SUP_BANK_DEBUG][SUP_SYNC][%s] " + message, (supplier_ref or 'N/A'), *args)

    def _safe_debug_json(self, value):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return repr(value)

    def _is_placeholder_value(self, value):
        """Return True when value is empty/demo placeholder like 'khong', 'none', 'n/a'."""
        if value in (None, False):
            return True

        raw = str(value).strip()
        if not raw:
            return True

        normalized = self._normalize_uom_token(raw)
        compact = re.sub(r"[\s\-_/\.]+", "", normalized)
        return compact in {'khong', 'none', 'null', 'na', '""', "''"}

    def _clean_placeholder_text(self, value):
        """Normalize to stripped text and drop placeholders as False."""
        if value in (None, False):
            return False
        text = str(value).strip()
        if not text:
            return False
        return False if self._is_placeholder_value(text) else text

    def _log_debug_keys_recursive(self, supplier_ref, label, data, path='root', level=0, max_level=2):
        if not isinstance(data, dict):
            self._log_supplier_sync(supplier_ref, "%s keys at %s: not-a-dict type=%s", label, path, type(data).__name__)
            return

        keys = sorted(list(data.keys()))
        self._log_supplier_sync(supplier_ref, "%s keys at %s: %s", label, path, keys)
        if level >= max_level:
            return

        for key in keys:
            value = data.get(key)
            child_path = "%s.%s" % (path, key)
            if isinstance(value, dict):
                self._log_debug_keys_recursive(
                    supplier_ref,
                    label,
                    value,
                    path=child_path,
                    level=level + 1,
                    max_level=max_level,
                )
            elif isinstance(value, list):
                self._log_supplier_sync(
                    supplier_ref,
                    "%s keys at %s: list_len=%s",
                    label,
                    child_path,
                    len(value),
                )
                for idx, item in enumerate(value[:3]):
                    if isinstance(item, dict):
                        self._log_debug_keys_recursive(
                            supplier_ref,
                            label,
                            item,
                            path="%s[%s]" % (child_path, idx),
                            level=level + 1,
                            max_level=max_level,
                        )

    def _log_alias_lookup(self, supplier_ref, source, field_name, keys):
        if not isinstance(source, dict):
            self._log_supplier_sync(supplier_ref, "alias lookup for %s skipped: source is not dict", field_name)
            return
        selected_key = False
        selected_value = False
        for key in keys:
            value = source.get(key)
            self._log_supplier_sync(supplier_ref, "alias lookup for %s: tried %s -> %r", field_name, key, value)
            if selected_value in (None, '', False) and value not in (None, '', False):
                selected_key = key
                selected_value = value
        self._log_supplier_sync(
            supplier_ref,
            "alias lookup result for %s: selected_key=%r selected_value=%r",
            field_name,
            selected_key,
            selected_value,
        )

    def _resolve_country_id_any(self, value):
        """Resolve country from ISO code/name. Return False when uncertain."""
        if value in (None, '', False):
            return False
        country_model = self.env['res.country']
        raw = str(value).strip()
        if not raw:
            return False
        code = raw.upper()

        # Common aliases from RS payloads (VN text / ISO3 / short forms).
        normalized = re.sub(r'[^a-z0-9]', '', self._normalize_uom_token(raw))
        alias_to_code = {
            'trungquoc': 'CN',
            'china': 'CN',
            'chn': 'CN',
            'hanquoc': 'KR',
            'korea': 'KR',
            'kor': 'KR',
            'vietnam': 'VN',
            'vietnam': 'VN',
            'vnm': 'VN',
            'switzerland': 'CH',
            'thuysi': 'CH',
            'che': 'CH',
            'usa': 'US',
            'unitedstates': 'US',
        }
        mapped_code = alias_to_code.get(normalized)
        if mapped_code:
            country = country_model.search([('code', '=', mapped_code)], limit=1)
            if country:
                return country.id

        country = country_model.search([('code', '=', code)], limit=1)
        if country:
            return country.id

        country = country_model.search([('name', '=', raw)], limit=1)
        if country:
            return country.id

        # Keep ilike as last fallback only when token length is meaningful.
        if len(raw) < 4:
            return False
        country = country_model.search([('name', 'ilike', raw)], limit=1)
        return country.id if country else False

    def _extract_supplier_address_parts(self, address_text, city=False, country=False):
        """Split free-text address into street/city/country with simple, safe heuristics."""
        raw_address = str(address_text or '').strip()
        explicit_city = str(city or '').strip()
        explicit_country = str(country or '').strip()

        if not raw_address:
            return {
                'street': False,
                'city': explicit_city or False,
                'country_id': self._resolve_country_id_any(explicit_country),
            }

        parts = [part.strip() for part in raw_address.split(',') if part and part.strip()]
        if not parts:
            return {
                'street': raw_address,
                'city': explicit_city or False,
                'country_id': self._resolve_country_id_any(explicit_country),
            }

        country_id = self._resolve_country_id_any(explicit_country)
        country_idx = None
        if parts:
            last_part_country_id = self._resolve_country_id_any(parts[-1])
            if last_part_country_id:
                country_idx = len(parts) - 1
                if not country_id:
                    country_id = last_part_country_id

        city_value = explicit_city or False
        city_idx = None
        if not city_value:
            city_markers = ('thành phố', 'tp.', 'tp ', 'city', 'tỉnh', 'province')
            end_idx = country_idx if country_idx is not None else len(parts)
            search_parts = parts[:end_idx]
            for idx in range(len(search_parts) - 1, -1, -1):
                token = search_parts[idx].lower()
                if any(marker in token for marker in city_markers):
                    city_value = search_parts[idx]
                    city_idx = idx
                    break

        street_parts = list(parts)
        if country_idx is not None and country_idx < len(street_parts):
            street_parts.pop(country_idx)
        if city_idx is not None and city_idx < len(street_parts):
            # city_idx can shift if country was removed before it
            adjusted_city_idx = city_idx
            if country_idx is not None and country_idx < city_idx:
                adjusted_city_idx -= 1
            if 0 <= adjusted_city_idx < len(street_parts):
                street_parts.pop(adjusted_city_idx)

        street_value = ', '.join(street_parts).strip() if street_parts else False
        if not city_value and country_idx is not None and len(parts) >= 2:
            city_value = parts[-2]
            street_value = ', '.join(parts[:-2]).strip() if len(parts) > 2 else False

        return {
            'street': street_value or False,
            'city': city_value or False,
            'country_id': country_id,
        }

    def _extract_supplier_currency_code(self, dto, supplier_dto, supplier_detail):
        """Get supplier currency code from RS payload using known key aliases."""
        # Supplier-level currency must have priority over product-level currency.
        for source in (supplier_dto, supplier_detail):
            value = self._rs_pick(source, ['currencyCode', 'currency_code', 'currency'])
            if value:
                return str(value).strip()
            zone = source.get('currencyZoneDTO') if isinstance(source, dict) else {}
            if isinstance(zone, dict):
                zone_value = zone.get('cid') or zone.get('code') or zone.get('name')
                if zone_value:
                    return str(zone_value).strip()

        # IMPORTANT: do not fallback to product currency for supplier purchase currency.
        return ''

    def _extract_seller_payloads(self, vals):
        """Extract supplierinfo payload from sync vals and remove write-unsafe keys."""
        payloads = vals.pop('_seller_sync_payloads', []) or []
        seller_cmds = vals.pop('seller_ids', False)
        if seller_cmds and not payloads:
            for cmd in seller_cmds:
                if not isinstance(cmd, (list, tuple)) or len(cmd) < 3:
                    continue
                if cmd[0] == 0 and isinstance(cmd[2], dict):
                    payloads.append(dict(cmd[2]))
        return payloads

    def _upsert_supplierinfo_payloads(self, product_tmpl, payloads):
        """Upsert product.supplierinfo to avoid duplicate lines on repeated sync."""
        if not product_tmpl or not payloads:
            return

        supplierinfo_model = self.env['product.supplierinfo']
        default_currency_id = self.env.company.currency_id.id if self.env.company and self.env.company.currency_id else False
        for payload in payloads:
            partner_id = payload.get('partner_id')
            if not partner_id:
                self._sync_audit_record_issue(
                    issue_kind='skip',
                    product_type=product_tmpl.product_type or 'unknown',
                    stage='supplierinfo_upsert',
                    payload=payload,
                    product_tmpl=product_tmpl,
                    field='partner_id',
                    source_value=payload.get('partner_id'),
                    normalized_value=None,
                    error_type='MISSING_PARTNER',
                    error_message='Skip supplierinfo because partner_id is empty',
                )
                continue

            min_qty = float(payload.get('min_qty') or 1.0)
            delay = int(payload.get('delay') or 1)
            currency_id = payload.get('currency_id') or default_currency_id
            if not currency_id:
                _logger.warning(
                    "Skip supplierinfo upsert: currency_id unresolved for product_tmpl_id=%s partner_id=%s",
                    product_tmpl.id,
                    partner_id,
                )
                self._sync_audit_record_issue(
                    issue_kind='skip',
                    product_type=product_tmpl.product_type or 'unknown',
                    stage='supplierinfo_upsert',
                    payload=payload,
                    product_tmpl=product_tmpl,
                    field='currency_id',
                    source_value=payload.get('currency_id'),
                    normalized_value=currency_id,
                    error_type='MISSING_CURRENCY',
                    error_message='Skip supplierinfo because currency_id cannot be resolved',
                )
                continue

            domain = [
                ('product_tmpl_id', '=', product_tmpl.id),
                ('product_id', '=', False),
                ('partner_id', '=', partner_id),
                ('min_qty', '=', min_qty),
                ('delay', '=', delay),
                ('currency_id', '=', currency_id),
            ]
            try:
                seller = supplierinfo_model.search(domain, limit=1)
                seller_vals = {
                    'partner_id': partner_id,
                    'product_tmpl_id': product_tmpl.id,
                    'product_id': False,
                    'price': float(payload.get('price') or 0.0),
                    'min_qty': min_qty,
                    'delay': delay,
                    'currency_id': currency_id,
                }
                if seller:
                    seller.write(seller_vals)
                else:
                    supplierinfo_model.create(seller_vals)
            except Exception as e:
                self._sync_audit_record_issue(
                    issue_kind='error',
                    product_type=product_tmpl.product_type or 'unknown',
                    stage='supplierinfo_upsert',
                    payload=payload,
                    product_tmpl=product_tmpl,
                    field='supplierinfo',
                    source_value=payload,
                    normalized_value={
                        'partner_id': partner_id,
                        'currency_id': currency_id,
                        'min_qty': min_qty,
                        'delay': delay,
                    },
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                raise

    def _upsert_supplier_contact(self, partner, supplier_detail):
        """Store RS contact person as child contact for clean Odoo modeling."""
        if not partner or not supplier_detail:
            return

        contact_name = self._clean_placeholder_text(self._rs_pick(supplier_detail, [
            'contactName', 'contact_name', 'contactPerson', 'contact_person',
            'contactPersonName', 'personContact', 'nguoiLienHe',
        ]))
        if not contact_name:
            return

        contact_phone = self._clean_placeholder_text(self._rs_pick(supplier_detail, [
            'contactPhone', 'contact_phone', 'contactMobile', 'contact_mobile', 'mobile',
        ]))
        contact_email = self._clean_placeholder_text(self._rs_pick(supplier_detail, [
            'contactEmail', 'contact_email', 'email',
        ]))

        contact = self.env['res.partner'].search([
            ('parent_id', '=', partner.id),
            ('type', '=', 'contact'),
            ('name', '=', contact_name),
        ], limit=1)
        contact_vals = {
            'name': contact_name,
            'parent_id': partner.id,
            'type': 'contact',
            'is_company': False,
        }
        if contact_phone:
            contact_vals['phone'] = contact_phone
        if contact_email:
            contact_vals['email'] = contact_email

        if contact:
            contact.write(contact_vals)
        else:
            self.env['res.partner'].create(contact_vals)

    def _extract_bank_payload(self, supplier_detail, supplier_dto=None, supplier_details=None, supplier_ref='', supplier_name=False):
        """Extract bank payload from RS vendor data with fallback across multiple nodes."""
        self._log_supplier_sync(
            supplier_ref,
            "===== SUPPLIER BANK DEBUG BLOCK START ===== supplier_ref=%r supplier_name=%r",
            supplier_ref,
            supplier_name,
        )
        self._log_supplier_sync(
            supplier_ref,
            "raw supplier_detail object: %s",
            self._safe_debug_json(supplier_detail),
        )
        self._log_supplier_sync(
            supplier_ref,
            "raw supplier_dto object: %s",
            self._safe_debug_json(supplier_dto),
        )
        self._log_supplier_sync(
            supplier_ref,
            "raw supplier_details list object: %s",
            self._safe_debug_json(supplier_details),
        )
        if isinstance(supplier_dto, dict):
            self._log_supplier_sync(
                supplier_ref,
                "supplier_dto top-level keys: %s",
                sorted(list(supplier_dto.keys())),
            )
            detail_dtos = supplier_dto.get('supplierDetailDTOS')
            if isinstance(detail_dtos, list) and detail_dtos:
                self._log_supplier_sync(
                    supplier_ref,
                    "supplierDetailDTOS[0] raw: %s",
                    self._safe_debug_json(detail_dtos[0]),
                )
            self._log_supplier_sync(
                supplier_ref,
                "supplier_dto.bank raw: %s | supplier_dto.bankdto raw: %s",
                self._safe_debug_json(supplier_dto.get('bank')),
                self._safe_debug_json(supplier_dto.get('bankdto')),
            )

        self._log_debug_keys_recursive(supplier_ref, "supplier_detail", supplier_detail, path='supplier_detail', max_level=3)
        if isinstance(supplier_dto, dict):
            self._log_debug_keys_recursive(supplier_ref, "supplier_dto", supplier_dto, path='supplier_dto', max_level=3)
        if isinstance(supplier_details, list):
            for idx, node in enumerate(supplier_details[:3]):
                if isinstance(node, dict):
                    self._log_debug_keys_recursive(
                        supplier_ref,
                        "supplier_details",
                        node,
                        path='supplier_details[%s]' % idx,
                        max_level=3,
                    )

        records = []
        if isinstance(supplier_detail, dict):
            records.append(supplier_detail)
        if isinstance(supplier_dto, dict):
            records.append(supplier_dto)
        if isinstance(supplier_details, list):
            records.extend([rec for rec in supplier_details if isinstance(rec, dict)])

        if not records:
            self._log_supplier_sync(supplier_ref, "skip extract bank payload: no records found")
            return {}

        bank_records = []
        for rec in records:
            bank_obj = rec.get('bank') if isinstance(rec.get('bank'), dict) else {}
            bank_data = rec.get('bankdto') if isinstance(rec.get('bankdto'), dict) else {}
            if bank_obj:
                bank_records.append(bank_obj)
            if bank_data:
                bank_records.append(bank_data)
        self._log_supplier_sync(
            supplier_ref,
            "records prepared: supplier_records=%s bank_records=%s",
            len(records),
            len(bank_records),
        )
        for idx, node in enumerate(records[:3]):
            self._log_supplier_sync(supplier_ref, "supplier_record[%s] keys=%s", idx, sorted(list(node.keys())))
        for idx, node in enumerate(bank_records[:3]):
            self._log_supplier_sync(supplier_ref, "bank_record[%s] keys=%s", idx, sorted(list(node.keys())))

        account_aliases = [
            'acc_number', 'accnumber', 'account_number', 'accountnumber', 'account_no', 'accountno',
            'account', 'bank_account', 'bankaccount', 'bank_account_number', 'bankaccountnumber',
            'bank_account_no', 'bankaccountno', 'bank_no', 'bankno', 'bank_number', 'banknumber',
            'number', 'stk', 'so_tai_khoan', 'sotaikhoan', 'tai_khoan', 'taikhoan',
            'acctno', 'acct_no', 'iban',
        ]

        def _normalize_key(raw_key):
            return re.sub(r'[^a-z0-9]', '', str(raw_key or '').lower())

        normalized_aliases = {_normalize_key(key) for key in account_aliases}

        def _looks_like_account_value(raw_value):
            text = str(raw_value or '').strip()
            if len(text) < 4 or len(text) > 64:
                return False
            return any(ch.isdigit() for ch in text)

        def _pick_with_meta(keys):
            for rec in records:
                for key in keys:
                    value = self._rs_pick(rec, [key], skip_placeholder=True)
                    if value:
                        return value, key, 'supplier_record'
            for rec in bank_records:
                for key in keys:
                    value = self._rs_pick(rec, [key], skip_placeholder=True)
                    if value:
                        return value, key, 'bank_record'
            return False, False, False

        def _pick_account_number():
            # 1) Explicit aliases first (safer)
            explicit_keys = [
                'bankAccount', 'bank_account', 'accountNumber', 'account_number', 'accNumber', 'acc_number',
                'accountNo', 'account_no', 'bankNo', 'bank_no', 'bankNumber', 'bank_number',
                'stk', 'account', 'number', 'soTaiKhoan', 'so_tai_khoan',
            ]

            for alias_key in [
                'acc_number', 'account_number', 'accountNo', 'bankAccount', 'bank_account',
                'stk', 'soTaiKhoan', 'account', 'number', 'bankNo', 'bank_number',
            ]:
                supplier_values = [
                    rec.get(alias_key)
                    for rec in records
                    if isinstance(rec, dict) and alias_key in rec
                ]
                bank_values = [
                    rec.get(alias_key)
                    for rec in bank_records
                    if isinstance(rec, dict) and alias_key in rec
                ]
                chosen = False
                for candidate in (supplier_values + bank_values):
                    cleaned_candidate = self._clean_placeholder_text(candidate)
                    if cleaned_candidate:
                        chosen = cleaned_candidate
                        break
                self._log_supplier_sync(
                    supplier_ref,
                    "account alias lookup: tried %s -> supplier_values=%r bank_values=%r chosen_non_empty=%r",
                    alias_key,
                    supplier_values,
                    bank_values,
                    chosen,
                )

            value, source_key, source_node = _pick_with_meta(explicit_keys)
            if value and (_normalize_key(source_key) not in ('account', 'number') or _looks_like_account_value(value)):
                self._log_supplier_sync(
                    supplier_ref,
                    "account selected by explicit alias: source_key=%r source_node=%r value=%r",
                    source_key,
                    source_node,
                    value,
                )
                return value, source_key, source_node

            # 2) Heuristic scan for unknown keys in RS payload shape
            for rec, source_node in [(r, 'supplier_record') for r in records] + [(r, 'bank_record') for r in bank_records]:
                if not isinstance(rec, dict):
                    continue
                for raw_key, value in rec.items():
                    if value in (None, '', False):
                        continue
                    if self._is_placeholder_value(value):
                        continue
                    normalized_key = _normalize_key(raw_key)
                    if normalized_key in normalized_aliases:
                        if _normalize_key(raw_key) in ('account', 'number') and not _looks_like_account_value(value):
                            continue
                        self._log_supplier_sync(
                            supplier_ref,
                            "account selected by normalized alias: raw_key=%r source_node=%r value=%r",
                            raw_key,
                            source_node,
                            value,
                        )
                        return value, raw_key, source_node
                    has_account_token = any(token in normalized_key for token in ('account', 'acc', 'stk', 'iban', 'taikhoan'))
                    has_bank_number_token = 'bank' in normalized_key and 'number' in normalized_key
                    if has_account_token or has_bank_number_token:
                        if not _looks_like_account_value(value):
                            continue
                        self._log_supplier_sync(
                            supplier_ref,
                            "account selected by heuristic token: raw_key=%r source_node=%r value=%r",
                            raw_key,
                            source_node,
                            value,
                        )
                        return value, raw_key, source_node
            self._log_supplier_sync(supplier_ref, "account selection failed: no alias/heuristic match found")
            return False, False, False

        def _pick(keys, field_name=''):
            for rec_idx, rec in enumerate(records):
                for key in keys:
                    value = rec.get(key) if isinstance(rec, dict) else False
                    if field_name:
                        self._log_supplier_sync(
                            supplier_ref,
                            "field extract %s: tried supplier_record[%s].%s -> %r",
                            field_name,
                            rec_idx,
                            key,
                            value,
                        )
                    cleaned_value = self._clean_placeholder_text(value)
                    if cleaned_value:
                        if field_name:
                            self._log_supplier_sync(
                                supplier_ref,
                                "field extract %s selected from supplier_record[%s].%s -> %r",
                                field_name,
                                rec_idx,
                                key,
                                cleaned_value,
                            )
                        return cleaned_value
            for rec_idx, rec in enumerate(bank_records):
                for key in keys:
                    value = rec.get(key) if isinstance(rec, dict) else False
                    if field_name:
                        self._log_supplier_sync(
                            supplier_ref,
                            "field extract %s: tried bank_record[%s].%s -> %r",
                            field_name,
                            rec_idx,
                            key,
                            value,
                        )
                    cleaned_value = self._clean_placeholder_text(value)
                    if cleaned_value:
                        if field_name:
                            self._log_supplier_sync(
                                supplier_ref,
                                "field extract %s selected from bank_record[%s].%s -> %r",
                                field_name,
                                rec_idx,
                                key,
                                cleaned_value,
                            )
                        return cleaned_value
            if field_name:
                self._log_supplier_sync(supplier_ref, "field extract %s selected -> False", field_name)
            return False

        bank_account, bank_account_source_key, bank_account_source_node = _pick_account_number()
        bank_account = self._clean_placeholder_text(bank_account)
        if not bank_account:
            bank_account_source_key = False
            bank_account_source_node = False

        extracted_payload = {
            'bank_name': _pick(['bankName', 'bank_name', 'advisingBank'], 'bank_name'),
            'bank_address': _pick(['bankAddress', 'bank_address', 'address'], 'bank_street'),
            'bank_account': bank_account,
            'bank_account_source_key': bank_account_source_key,
            'bank_account_source_node': bank_account_source_node,
            'bank_branch': _pick(['bankBranch', 'bank_branch', 'branch', 'branchName', 'branchCode'], 'bank_branch'),
            'bank_swift': _pick(['swiftCode', 'swift_code', 'swift', 'bic', 'bankBic'], 'bank_bic'),
            'bank_country': _pick(['bankCountry', 'bank_country', 'country', 'countryCode', 'country_code'], 'bank_country'),
        }

        self._log_supplier_sync(
            supplier_ref,
            "bank payload final extracted: %s",
            self._safe_debug_json(extracted_payload),
        )
        self._log_supplier_sync(
            supplier_ref,
            "===== SUPPLIER BANK DEBUG BLOCK END ===== supplier_ref=%r",
            supplier_ref,
        )

        return extracted_payload

    def _cleanup_placeholder_partner_bank_accounts(self, partner, supplier_ref=''):
        """Delete partner bank rows containing placeholder account numbers."""
        if not partner:
            return 0

        removed = 0
        partner_banks = self.env['res.partner.bank'].search([('partner_id', '=', partner.id)])
        for bank_row in partner_banks:
            if self._is_placeholder_value(bank_row.acc_number):
                self._log_supplier_sync(
                    supplier_ref,
                    "cleanup placeholder partner.bank: remove account_id=%s acc_number=%r bank_name=%r",
                    bank_row.id,
                    bank_row.acc_number,
                    bank_row.bank_id.name if bank_row.bank_id else False,
                )
                bank_row.unlink()
                removed += 1

        if removed:
            self._log_supplier_sync(
                supplier_ref,
                "cleanup placeholder partner.bank completed: removed=%s partner_id=%s",
                removed,
                partner.id,
            )
        return removed

    def _upsert_supplier_bank_accounts(self, partner, supplier_detail, supplier_dto=None, supplier_details=None, currency_id=False, supplier_ref=''):
        """Upsert res.bank and res.partner.bank from RS payload."""
        if not partner:
            self._log_supplier_sync(supplier_ref, "skip bank upsert: partner missing (skip because partner not found)")
            return

        self._cleanup_placeholder_partner_bank_accounts(partner, supplier_ref=supplier_ref)

        payload = self._extract_bank_payload(
            supplier_detail,
            supplier_dto=supplier_dto,
            supplier_details=supplier_details,
            supplier_ref=supplier_ref,
            supplier_name=partner.name,
        )
        acc_number = self._clean_placeholder_text(payload.get('bank_account'))
        bank_name = self._clean_placeholder_text(payload.get('bank_name'))
        swift_code = self._clean_placeholder_text(payload.get('bank_swift'))
        bank_street = self._clean_placeholder_text(payload.get('bank_address'))
        bank_branch = self._clean_placeholder_text(payload.get('bank_branch'))
        bank_country = self._clean_placeholder_text(payload.get('bank_country'))
        self._log_supplier_sync(
            supplier_ref,
            "extract bank fields: bank_name=%r bank_bic=%r bank_street=%r bank_country=%r account_number=%r currency_id=%r",
            bank_name,
            swift_code,
            bank_street,
            bank_country,
            acc_number,
            currency_id,
        )
        self._log_supplier_sync(
            supplier_ref,
            "bank payload extracted: account=%r source_key=%r source_node=%r bank_name=%r swift=%r country=%r branch=%r address=%r",
            acc_number,
            payload.get('bank_account_source_key'),
            payload.get('bank_account_source_node'),
            bank_name,
            swift_code,
            bank_country,
            bank_branch,
            bank_street,
        )

        if not any([bank_name, swift_code]):
            self._log_supplier_sync(
                supplier_ref,
                "skip res.bank upsert: both bank_name and swift are empty/placeholder",
            )

        country_id = self._resolve_country_id_any(bank_country)
        bank_domain = []
        if swift_code:
            bank_domain = [('bic', '=', swift_code)]
        elif bank_name and country_id:
            bank_domain = [('name', '=', bank_name), ('country', '=', country_id)]
        elif bank_name:
            bank_domain = [('name', '=', bank_name)]

        bank = self.env['res.bank'].search(bank_domain, limit=1) if bank_domain else False
        self._log_supplier_sync(supplier_ref, "bank search domain=%s found_bank_id=%s", bank_domain, bank.id if bank else False)
        bank_vals = {}
        if bank_name:
            bank_vals['name'] = bank_name
        if swift_code:
            bank_vals['bic'] = swift_code
        if bank_street:
            bank_vals['street'] = bank_street
        if country_id:
            bank_vals['country'] = country_id
        if bank_branch and 'bank_branch_name' in self.env['res.bank']._fields:
            bank_vals['bank_branch_name'] = bank_branch

        if bank_vals and not bank_vals.get('name') and swift_code:
            bank_vals['name'] = swift_code

        if bank:
            if bank_vals:
                bank.write(bank_vals)
                self._log_supplier_sync(supplier_ref, "bank updated: bank_id=%s vals=%s", bank.id, bank_vals)
        elif bank_vals.get('name'):
            bank = self.env['res.bank'].create(bank_vals)
            self._log_supplier_sync(supplier_ref, "bank created: bank_id=%s vals=%s", bank.id, bank_vals)
        else:
            self._log_supplier_sync(
                supplier_ref,
                "skip res.bank create: validation failed because bank_vals has no name; bank_vals=%s",
                bank_vals,
            )

        if not acc_number:
            self._log_supplier_sync(
                supplier_ref,
                "skip partner.bank upsert: acc_number missing (skip because account_number is empty, matched_key=%r matched_node=%r)",
                payload.get('bank_account_source_key'),
                payload.get('bank_account_source_node'),
            )
            return

        self._log_supplier_sync(
            supplier_ref,
            "partner.bank upsert condition: partner_id=%s has_acc_number=%s has_bank_id=%s currency_id=%s",
            partner.id,
            bool(acc_number),
            bool(bank and bank.id),
            currency_id,
        )
        if not bank:
            self._log_supplier_sync(
                supplier_ref,
                "skip partner.bank upsert: bank_id missing (skip because bank_id is required)",
            )
            return

        account_vals = {
            'partner_id': partner.id,
            'acc_number': acc_number,
            'bank_id': bank.id,
        }
        if 'currency_id' in self.env['res.partner.bank']._fields:
            account_vals['currency_id'] = currency_id or False

        account = self.env['res.partner.bank'].search([
            ('partner_id', '=', partner.id),
            ('acc_number', '=', account_vals['acc_number']),
            ('bank_id', '=', account_vals['bank_id']),
        ], limit=1)
        if account:
            account.write(account_vals)
            self._log_supplier_sync(
                supplier_ref,
                "partner.bank updated: account_id=%s bank_id=%s currency_id=%s",
                account.id,
                account_vals.get('bank_id'),
                account_vals.get('currency_id'),
            )
        else:
            account = self.env['res.partner.bank'].create(account_vals)
            self._log_supplier_sync(
                supplier_ref,
                "partner.bank created: account_id=%s bank_id=%s currency_id=%s",
                account.id,
                account_vals.get('bank_id'),
                account_vals.get('currency_id'),
            )

    def _upsert_supplier_partner(self, supplier_dto, cache, currency_id=False):
        """Upsert supplier partner by ref (official code), then enrich contact/bank."""
        details = supplier_dto.get('supplierDetailDTOS', []) if isinstance(supplier_dto, dict) else []
        detail_candidates = [rec for rec in details if isinstance(rec, dict)]
        if isinstance(supplier_dto, dict):
            detail_candidates.append(supplier_dto)
        if not detail_candidates:
            self._log_supplier_sync('', "skip supplier upsert: no detail candidates in payload")
            return False

        detail = detail_candidates[0]
        supplier_ref = False
        supplier_name = False
        for candidate in detail_candidates:
            supplier_ref = self._rs_pick(candidate, ['cid', 'code', 'supplierCode', 'supplier_code'])
            supplier_name = self._rs_pick(candidate, ['name', 'supplierName', 'supplier_name'])
            if supplier_ref and supplier_name:
                detail = candidate
                break

        if not supplier_ref or not supplier_name:
            self._log_supplier_sync('', "skip supplier upsert: missing supplier_ref or supplier_name")
            return False

        ref = str(supplier_ref).strip().upper()
        self._log_supplier_sync(
            ref,
            "supplier candidate resolved: supplier_ref=%r supplier_name=%r details_count=%s currency_id=%s",
            ref,
            supplier_name,
            len(detail_candidates),
            currency_id,
        )
        partner = self.env['res.partner'].search([('ref', '=', ref)], limit=1)
        if not partner and 'code' in self.env['res.partner']._fields:
            partner = self.env['res.partner'].search([('code', '=', ref)], limit=1)

        phone = self._rs_pick(detail, ['phone', 'phoneNumber', 'telephone'])
        email = self._clean_placeholder_text(self._rs_pick(detail, ['mail', 'email']))
        vat = self._clean_placeholder_text(self._rs_pick(detail, ['taxCode', 'tax_code', 'taxNumber', 'tax_number', 'taxId', 'vat', 'mst']))
        fax = self._clean_placeholder_text(self._rs_pick(detail, ['fax', 'faxNumber', 'fax_number']))
        address_text = self._rs_pick(detail, ['address', 'street'])
        city = self._rs_pick(detail, ['city'])
        partner_country = self._rs_pick(detail, ['countryCode', 'country_code', 'country'])
        if not partner_country and isinstance(detail.get('coDTO'), dict):
            partner_country = (
                detail['coDTO'].get('cid')
                or detail['coDTO'].get('code')
                or detail['coDTO'].get('name')
            )
        contact_person = self._clean_placeholder_text(self._rs_pick(detail, [
            'contactName', 'contact_name', 'contactPerson', 'contact_person',
            'contactPersonName', 'personContact', 'nguoiLienHe',
        ]))
        self._log_alias_lookup(ref, detail, 'supplier_ref', ['cid', 'code', 'supplierCode', 'supplier_code'])
        self._log_alias_lookup(ref, detail, 'supplier_name', ['name', 'supplierName', 'supplier_name'])
        self._log_alias_lookup(ref, detail, 'phone', ['phone', 'phoneNumber', 'telephone'])
        self._log_alias_lookup(ref, detail, 'email', ['mail', 'email'])
        self._log_alias_lookup(ref, detail, 'address', ['address', 'street'])
        self._log_alias_lookup(ref, detail, 'vat', ['taxCode', 'tax_code', 'taxNumber', 'tax_number', 'taxId', 'vat', 'mst'])
        self._log_alias_lookup(ref, detail, 'contact_person', [
            'contactName', 'contact_name', 'contactPerson', 'contact_person',
            'contactPersonName', 'personContact', 'nguoiLienHe',
        ])
        self._log_alias_lookup(ref, detail, 'bank_name', ['bankName', 'bank_name', 'name'])
        self._log_alias_lookup(ref, detail, 'bank_bic', ['swiftCode', 'swift_code', 'swift', 'bic', 'bankBic'])
        self._log_alias_lookup(ref, detail, 'bank_street', ['bankAddress', 'bank_address', 'address'])
        self._log_alias_lookup(ref, detail, 'bank_country', ['bankCountry', 'bank_country', 'country', 'countryCode', 'country_code'])
        self._log_supplier_sync(
            ref,
            "extract fields: supplier_ref=%r supplier_name=%r phone=%r email=%r address=%r vat=%r contact_person=%r",
            ref,
            supplier_name,
            phone,
            email,
            address_text,
            vat,
            contact_person,
        )
        address_parts = self._extract_supplier_address_parts(
            address_text,
            city=city,
            country=partner_country,
        )
        self._log_supplier_sync(
            ref,
            "address parse: raw=%r city_in=%r country_in=%r => street=%r city=%r country_id=%r",
            address_text,
            city,
            partner_country,
            address_parts.get('street'),
            address_parts.get('city'),
            address_parts.get('country_id'),
        )

        vals = {
            'name': str(supplier_name).strip(),
            'ref': ref,
            'is_company': True,
            'supplier_rank': max(1, int(partner.supplier_rank or 0)) if partner else 1,
        }
        if phone:
            vals['phone'] = str(phone).strip()
        if email:
            vals['email'] = str(email).strip()
        if vat:
            vals['vat'] = str(vat).strip()
        if fax:
            # Odoo 18 base has no dedicated fax field; keep fax in mobile as safest standard slot.
            vals['mobile'] = str(fax).strip()
        if address_parts.get('street'):
            vals['street'] = address_parts['street']
        if address_parts.get('city'):
            vals['city'] = address_parts['city']
        if address_parts.get('country_id'):
            vals['country_id'] = address_parts['country_id']
        if 'property_purchase_currency_id' in self.env['res.partner']._fields:
            vals['property_purchase_currency_id'] = currency_id or False
        if 'code' in self.env['res.partner']._fields:
            vals['code'] = ref
        self._log_supplier_sync(
            ref,
            "partner vals prepared: has_phone=%s has_vat=%s has_city=%s has_country=%s purchase_currency_id=%s",
            bool(vals.get('phone')),
            bool(vals.get('vat')),
            bool(vals.get('city')),
            bool(vals.get('country_id')),
            vals.get('property_purchase_currency_id'),
        )

        if partner:
            partner.write(vals)
            self._log_supplier_sync(ref, "partner updated: partner_id=%s", partner.id)
        else:
            partner = self.env['res.partner'].create(vals)
            self._log_supplier_sync(ref, "partner created: partner_id=%s", partner.id)

        cache['suppliers'][ref] = partner.id
        if 'code' in self.env['res.partner']._fields and partner.code:
            cache['suppliers'][partner.code.upper()] = partner.id

        self._upsert_supplier_contact(partner, detail)
        self._upsert_supplier_bank_accounts(
            partner,
            detail,
            supplier_dto=supplier_dto,
            supplier_details=details,
            currency_id=currency_id,
            supplier_ref=ref,
        )

        partner_banks = self.env['res.partner.bank'].search([('partner_id', '=', partner.id)])
        bank_rows = [
            {
                'id': row.id,
                'acc_number': row.acc_number,
                'bank_name': row.bank_id.name if row.bank_id else False,
            }
            for row in partner_banks
        ]
        self._log_supplier_sync(
            ref,
            "supplier sync result: partner_id=%s bank_ids_count=%s bank_ids=%s",
            partner.id,
            len(partner_banks),
            self._safe_debug_json(bank_rows),
        )
        return partner.id

    def _prepare_base_vals(self, item, cache, product_type, coating_ids=None, lens_template_key=None):
        dto = item.get('productdto') or {}
        cid = (dto.get('cid') or '').strip()
        if not cid:
            raise ValueError("Missing CID")
        rs_product_id = self._extract_rs_product_id(item)

        # Gọng kính: mỗi màu = 1 template riêng, key định danh BẮT BUỘC là model-color
        default_code = cid
        if product_type == 'opt':
            model_code = (item.get('model') or '').strip()
            color_code = (item.get('color') or '').strip()
            if not model_code or not color_code:
                raise ValueError(
                    f"⚠️ Bỏ qua gọng cid={cid}: thiếu model='{model_code}' hoặc color='{color_code}'. "
                    f"default_code không thể xác định duy nhất."
                )
            default_code = f"{model_code}-{color_code}"
        
        # Category Logic with Code (for product code generation)
        grp_dto = dto.get('groupdto') or {}
        grp_type_name = (grp_dto.get('groupTypedto') or {}).get('name', 'Khác')
        
        # Map product type to category code (matches RS format)
        cat_map = {
            'Mắt': ('Lens Products', 'lens', '06'),      # Code 06 for Lens
            'Gọng': ('Optical OPT', 'opt', '27'),        # Code 27 for Opt
            'Khác': ('Accessories', 'accessory', '20')   # Code 20 for Accessory
        }
        main_cat, _, main_code = cat_map.get(grp_type_name, ('Accessories', 'accessory', '20'))
        
        # Get/Create Category
        cat_name = grp_dto.get('name', 'All Products')
        
        # 1. Ensure Parent Category with code
        parent_key = (main_cat, False)
        if parent_key in cache['categories']:
            parent_id = cache['categories'][parent_key]
        else:
            parent = self.env['product.category'].create({
                'name': main_cat,
                'code': main_code  # Set code for parent category
            })
            parent_id = parent.id
            cache['categories'][parent_key] = parent_id
            
        # 2. Ensure Child Category (inherit parent code if not set)
        cat_key = (cat_name, parent_id)
        if cat_key in cache['categories']:
            categ_id = cache['categories'][cat_key]
        else:
            cat = self.env['product.category'].create({
                'name': cat_name,
                'parent_id': parent_id,
                'code': main_code  # Child categories use same code as parent
            })
            categ_id = cat.id
            cache['categories'][cat_key] = categ_id

        # Group Logic
        grp_id = False
        if 'product.group' in self.env:
            g_id = grp_dto.get('id')
            g_cid = (grp_dto.get('cid') or '').strip().upper()
            g_name = (grp_dto.get('name') or '').strip()
            
            if g_id and g_id in cache['groups_by_id']: grp_id = g_id
            elif g_cid and g_cid in cache['groups']: grp_id = cache['groups'][g_cid]
            elif g_name and g_name.upper() in cache['groups']: grp_id = cache['groups'][g_name.upper()]
            elif g_name:
                # Create Group
                g_type_id = False
                if 'product.group.type' in self.env:
                    gt = self.env['product.group.type'].search([('name', '=', grp_type_name)], limit=1)
                    if not gt: gt = self.env['product.group.type'].create({'name': grp_type_name})
                    g_type_id = gt.id
                
                ng = self.env['product.group'].create({'name': g_name, 'cid': g_cid or '', 'group_type_id': g_type_id, 'product_type': product_type})
                grp_id = ng.id
                if g_cid: cache['groups'][g_cid] = grp_id
                cache['groups'][g_name.upper()] = grp_id
                cache['groups_by_id'][grp_id] = grp_id

        # Currency lookup (cần trước seller_ids để truyền currency_id đúng)
        s_dto = dto.get('supplierdto') or {}
        s_details = s_dto.get('supplierDetailDTOS', []) if isinstance(s_dto, dict) else []
        s_detail = s_details[0] if s_details and isinstance(s_details[0], dict) else {}
        supplier_currency_code = self._rs_pick(s_dto, ['currencyCode', 'currency_code', 'currency'])
        if not supplier_currency_code and isinstance(s_dto, dict):
            supplier_zone_obj = s_dto.get('currencyZoneDTO')
            if isinstance(supplier_zone_obj, dict):
                supplier_currency_code = supplier_zone_obj.get('cid') or supplier_zone_obj.get('code') or supplier_zone_obj.get('name')

        if not supplier_currency_code:
            supplier_currency_code = self._rs_pick(s_detail, ['currencyCode', 'currency_code', 'currency'])
            if not supplier_currency_code and isinstance(s_detail, dict):
                supplier_zone_obj = s_detail.get('currencyZoneDTO')
                if isinstance(supplier_zone_obj, dict):
                    supplier_currency_code = supplier_zone_obj.get('cid') or supplier_zone_obj.get('code') or supplier_zone_obj.get('name')

        currency_zone_cid = self._extract_supplier_currency_code(dto, s_dto, s_detail)
        supplier_ref_hint = self._rs_pick(s_detail, ['cid', 'code', 'supplierCode', 'supplier_code']) or self._rs_pick(s_dto, ['cid', 'code', 'supplierCode', 'supplier_code'])
        supplier_name_hint = self._rs_pick(s_detail, ['name', 'supplierName', 'supplier_name']) or self._rs_pick(s_dto, ['name', 'supplierName', 'supplier_name'])
        supplier_ref_hint = str(supplier_ref_hint or '').strip().upper()
        self._log_supplier_sync(
            supplier_ref_hint,
            "currency source resolved: code=%r dto_currencyZone=%r",
            currency_zone_cid,
            ((dto.get('currencyZoneDTO') or {}).get('cid') if isinstance(dto, dict) else ''),
        )
        self._log_supplier_sync(
            supplier_ref_hint,
            "currency source detail: supplier_currency=%r product_currency=%r",
            supplier_currency_code,
            ((dto.get('currencyZoneDTO') or {}).get('cid') if isinstance(dto, dict) else ''),
        )

        strict_supplier_currency_source = os.getenv('STRICT_SUPPLIER_CURRENCY_SOURCE', 'False').strip().lower() in ('1', 'true', 'yes', 'on')
        if strict_supplier_currency_source and not supplier_currency_code:
            raise ValueError(
                "Supplier currency source missing in supplier payload: supplier_ref=%s supplier_name=%s product_currency=%s"
                % (
                    supplier_ref_hint or 'N/A',
                    (self._rs_pick(s_detail, ['name', 'supplierName', 'supplier_name']) or self._rs_pick(s_dto, ['name', 'supplierName', 'supplier_name']) or 'N/A'),
                    (currency_zone_cid or 'EMPTY'),
                )
            )

        currency_id = False
        if currency_zone_cid:
            _cur_key = f'currency_{currency_zone_cid.upper()}'
            if _cur_key in cache.setdefault('misc', {}):
                currency_id = cache['misc'][_cur_key]
            else:
                # Ưu tiên dùng cache acc_currency đã preload (bao gồm cả inactive)
                _cached_cur_id = cache.get('acc_currency', {}).get(currency_zone_cid.upper())
                if _cached_cur_id:
                    currency_id = _cached_cur_id
                    _logger.info(f"✅ Found currency in cache: {currency_zone_cid.upper()} (id={currency_id})")
                else:
                    # Fallback: search trực tiếp, bắt buộc dùng active_test=False để tìm cả VND inactive
                    _cur = self.env['res.currency'].with_context(active_test=False).search([
                        '|',
                        ('name', '=', currency_zone_cid.upper()),
                        ('symbol', '=', currency_zone_cid.upper())
                    ], limit=1)
                    if _cur:
                        currency_id = _cur.id
                        # Nếu currency đang inactive, kích hoạt để dùng được
                        if not _cur.active:
                            try:
                                with self.env.cr.savepoint():
                                    _cur.write({'active': True})
                                _logger.info(f"✅ Activated inactive currency: {currency_zone_cid.upper()} (id={currency_id})")
                            except Exception as e:
                                _logger.warning(f"⚠️ Không kích hoạt được currency {currency_zone_cid!r}: {e}")
                    else:
                        _logger.warning(
                            "⚠️ Currency không tồn tại trong Odoo: code=%r | supplier_ref=%r supplier_name=%r",
                            currency_zone_cid,
                            supplier_ref_hint,
                            supplier_name_hint,
                        )
                    # Cập nhật cache để lần sau không cần search lại
                    if currency_id:
                        cache.setdefault('acc_currency', {})[currency_zone_cid.upper()] = currency_id
                cache['misc'][_cur_key] = currency_id
        else:
            self._log_supplier_sync(supplier_ref_hint, "currency unresolved: no currency code found in payload")

        strict_currency = os.getenv('STRICT_SUPPLIER_CURRENCY', 'False').strip().lower() in ('1', 'true', 'yes', 'on')
        supplier_has_identity = bool(supplier_ref_hint or supplier_name_hint)
        if strict_currency and supplier_has_identity and not currency_id:
            raise ValueError(
                "Supplier currency mapping failed: supplier_ref=%s supplier_name=%s raw_currency=%s"
                % (supplier_ref_hint or 'N/A', supplier_name_hint or 'N/A', currency_zone_cid or 'EMPTY')
            )

        self._log_supplier_sync(
            supplier_ref_hint,
            "currency resolved final: currency_id=%s",
            currency_id,
        )

        # Supplier Logic - upsert supplier by ref and defer supplierinfo upsert.
        seller_payloads = []
        sup_id = self._upsert_supplier_partner(s_dto, cache, currency_id=currency_id)
        if sup_id:
            seller_payloads.append({
                'partner_id': sup_id,
                'price': float(dto.get('orPrice') or 0),
                'min_qty': 1.0,
                'delay': 1,
                'currency_id': currency_id or False,
            })

        # Tax (Purchase tax for suppliers)
        tax_pct = float(dto.get('tax') or 0)
        tax_id = False
        if tax_pct > 0:
            t_name = f"Thuế mua hàng {tax_pct}%"
            if t_name in cache['taxes']:
                tax_id = cache['taxes'][t_name]
            else:
                nt = self.env['account.tax'].create({
                    'name': t_name, 
                    'amount': tax_pct, 
                    'amount_type': 'percent', 
                    'type_tax_use': 'purchase'
                })
                tax_id = nt.id
                cache['taxes'][t_name] = tax_id

        # Status
        status_id = False
        if 'product.status' in self.env:
            status_name = (dto.get('statusProductdto') or {}).get('name', '')
            if status_name:
                status_key = status_name.upper()
                if status_key in cache['statuses']:
                    status_id = cache['statuses'][status_key]
                else:
                    # Create new status if not exists
                    ns = self.env['product.status'].create({'name': status_name})
                    status_id = ns.id
                    cache['statuses'][status_key] = status_id

        is_storable = product_type in ['opt', 'lens']
        product_kind = 'consu'
        resolved_uom_id = self._resolve_rs_uom_id(item, dto, cache)

        # Basic Vals
        vals = {
            'name': dto.get('fullname') or 'Unknown',
            'default_code': default_code,
            'type': product_kind,
            'is_storable': is_storable,  # Gọng/Lens = storable
            'categ_id': categ_id,
            'list_price': float(dto.get('rtPrice') or 0),
            'standard_price': float(dto.get('orPrice') or 0) * float((dto.get('currencyZoneDTO') or {}).get('value') or 1),  # Giá vốn: orPrice * tỷ giá (= x_or_price)
            'supplier_taxes_id': [(6, 0, [tax_id])] if tax_id else False,
            'seller_ids': False,
            '_seller_sync_payloads': seller_payloads,
            'product_type': product_type,
            'brand_id': self._get_or_create(cache, 'brands', 'product.brand', dto.get('tmdto')),
            'country_id': self._get_or_create(cache, 'countries', 'product.country', dto.get('codto')),
            'warranty_id': self._get_or_create(cache, 'warranties', 'product.warranty', dto.get('warrantydto')),
            'group_id': grp_id,
            # Custom Fields (prefixed with x_)
            'x_eng_name': dto.get('engName', ''),
            'x_trade_name': dto.get('tradeName', ''),
            'description': dto.get('note', ''),
            'x_uses': dto.get('uses', ''),
            'x_guide': dto.get('guide', ''),
            'x_warning': dto.get('warning', ''),
            'x_preserve': dto.get('preserve', ''),
            'x_cid_ncc': dto.get('cidNcc', ''),
            'x_accessory_total': int(dto.get('accessoryTotal') or 0),
            'status_product_id': status_id,
            'x_currency_zone_code': (dto.get('currencyZoneDTO') or {}).get('cid', ''),
            'x_currency_zone_value': float((dto.get('currencyZoneDTO') or {}).get('value') or 0),
            'x_ws_price': float(dto.get('wsPrice') or dto.get('wsPriceMax') or 0),
            'x_ws_price_min': float(dto.get('wsPriceMin') or 0),
            'x_ws_price_max': float(dto.get('wsPriceMax') or 0),
            # x_or_price = giá nhập kho quy VND: orPrice (ngoại tệ) * tỷ giá
            'x_or_price': float(dto.get('orPrice') or 0) * float((dto.get('currencyZoneDTO') or {}).get('value') or 1),
            'manufacturer_months': int(
                (dto.get('warrantydto') or {}).get('manufacturerMonths')
                or dto.get('manufacturerWarrantyMonths')
                or 0
            ),
            'company_months': int(
                (dto.get('warrantydto') or {}).get('companyMonths')
                or dto.get('companyWarrantyMonths')
                or 0
            ),
            'x_group_type_name': grp_type_name,
        }

        if resolved_uom_id:
            vals['uom_id'] = resolved_uom_id
            vals['uom_po_id'] = resolved_uom_id

        # Keep RS source identifier independent from default_code business key.
        if rs_product_id:
            vals['x_rs_product_id'] = rs_product_id

        # ─── Lens specs (template-level only; no variants) ────────────────
        if product_type == 'lens':
            def safe_float(val):
                if val is None or val == '':
                    return None
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None

            def safe_int(val):
                if val is None or val == '':
                    return None
                try:
                    return int(str(val).replace('mm', '').replace('MM', '').strip())
                except (TypeError, ValueError):
                    return None

            def pick_value(source, keys):
                for key in keys:
                    if key in source:
                        val = source.get(key)
                        # Dùng `is not None` thay vì `not in (None, '', False)`
                        # vì 0 == False trong Python → 0.00 (ADD hợp lệ) bị bỏ qua sai
                        if val is not None and val != '':
                            return val
                return None

            def extract_number(raw):
                if isinstance(raw, dict):
                    raw = raw.get('value') or raw.get('val') or raw.get('name') or raw.get('cid')
                return raw

            def extract_label(value):
                if isinstance(value, dict):
                    return (value.get('name') or value.get('cid') or '').strip()
                if isinstance(value, (list, tuple)):
                    labels = [extract_label(v) for v in value]
                    labels = [l for l in labels if l]
                    return ', '.join(labels)
                if value in (None, '', False):
                    return ''
                return str(value).strip()

            def first_non_empty(*values):
                for val in values:
                    if isinstance(val, dict):
                        text = extract_label(val)
                    else:
                        text = str(val).strip() if val not in (None, '', False) else ''
                    if text:
                        return text
                return ''

            if coating_ids is None:
                coating_ids, coating_codes = self._resolve_lens_coatings(item, cache)
            else:
                coating_codes = []

            if lens_template_key is None:
                lens_template_key = self._build_lens_template_key(item, coating_codes)

            design_1 = first_non_empty(
                item.get('design1'),
                item.get('design'),
                item.get('design_1'),
                item.get('design1dto'),
                item.get('designdto')
            )
            design_2 = first_non_empty(
                item.get('design2'),
                item.get('design_2'),
                item.get('design2dto')
            )
            raw_index = (
                item.get('indexdto')
                or item.get('indexDto')
                or item.get('indexDTO')
                or item.get('lensIndexdto')
                or item.get('lensIndexDto')
                or item.get('refractiveIndexDto')
                or (item.get('productdto') or {}).get('indexdto')
                or (item.get('productdto') or {}).get('indexDto')
                or (item.get('productdto') or {}).get('refractiveIndexDto')
                or {}
            )
            if isinstance(raw_index, dict):
                index_dto = raw_index
            else:
                index_dto = {'name': str(raw_index).strip()} if raw_index not in (None, '', False) else {}

            if not index_dto:
                index_name = first_non_empty(
                    item.get('index'),
                    item.get('refractiveIndex'),
                    item.get('chietSuat'),
                    (item.get('productdto') or {}).get('index'),
                    (item.get('productdto') or {}).get('refractiveIndex')
                )

                # Fallback cuối: parse từ fullname (vd: "... 1.67 ...")
                if not index_name:
                    fullname = (item.get('productdto') or {}).get('fullname') or ''
                    match = re.search(r'\b1\.\d{2}\b', fullname)
                    if match:
                        index_name = match.group(0)

                if index_name:
                    index_dto = {'name': index_name}

            uv_dto = item.get('uvdto') or item.get('uvDto') or item.get('uvDTO') or {}
            hmc_val = (
                item.get('hmcDto') or item.get('hmcdto') or item.get('hmcDTO')
                or item.get('hmc') or item.get('HMC')
                or item.get('isHmc') or item.get('isHMC')
                or item.get('hmcCode') or item.get('hmccode')
                or item.get('hmcValue') or item.get('hmcName')
            )
            pho_val = (
                item.get('phoDto') or item.get('phodto') or item.get('phoDTO')
                or item.get('photochromicDto') or item.get('photochromic') or item.get('PHO')
                or item.get('isPhotochromic') or item.get('photochromicCode')
                or item.get('photochromicValue') or item.get('photochromicName')
            )
            tint_val = (
                item.get('tintDto') or item.get('tintdto') or item.get('tintDTO')
                or item.get('tint') or item.get('TINT') or item.get('tinted')
                or item.get('isTinted') or item.get('tintCode')
                or item.get('tintValue') or item.get('tintName')
                or item.get('tintLevel')
                # NOTE: colorInt KHÔNG đưa vào đây — nó đã map vào lens_color_int riêng
            )
            sph_raw = pick_value(item, ['sph', 'SPH', 'sphValue', 'sphVal', 'sphDTO', 'sphDto', 'sphdto'])
            cyl_raw = pick_value(item, ['cyl', 'CYL', 'cylValue', 'cylVal', 'cylDTO', 'cylDto', 'cyldto'])
            add_raw = pick_value(item, ['lensAdd', 'add', 'ADD', 'addValue', 'addVal', 'addDTO', 'addDto', 'adddto'])
            axis_raw = pick_value(item, ['axis', 'Axis', 'AXIS'])

            # ── Helper: get-or-create Many2one master data for lens ────────────────────
            def _goc_design(name_raw):
                """Get or create product.design by name."""
                nm = str(name_raw or '').strip()
                _logger.info("🔎 _goc_design called with=%s", nm or None)
                if not nm:
                    return False
                key = nm.upper()
                cid = cache.get('designs', {}).get(key)
                if cid:
                    _logger.info("✅ _goc_design cache hit name=%s id=%s", nm, cid)
                    return cid
                found = self.env['product.design'].search([('name', '=', nm)], limit=1)
                if found:
                    cache.setdefault('designs', {})[key] = found.id
                    _logger.info("✅ _goc_design search hit name=%s id=%s", nm, found.id)
                    return found.id
                try:
                    with self.env.cr.savepoint():
                        rec = self.env['product.design'].create({'name': nm})
                    cache.setdefault('designs', {})[key] = rec.id
                    _logger.info("✅ _goc_design created name=%s id=%s", nm, rec.id)
                    return rec.id
                except Exception as e:
                    _logger.warning(f"⚠️ Không tạo được product.design name={nm!r}: {e}")
                    return False

            def _goc_material(name_raw):
                """Get or create product.lens.material by name."""
                nm = str(name_raw or '').strip()
                _logger.info("🔎 _goc_material called with=%s", nm or None)
                if not nm:
                    return False
                key_lower = nm.lower()
                cid = cache.get('lens_materials', {}).get(key_lower)
                if cid:
                    _logger.info("✅ _goc_material cache hit name=%s id=%s", nm, cid)
                    return cid
                found = self.env['product.lens.material'].search([('name', '=', nm)], limit=1)
                if found:
                    cache.setdefault('lens_materials', {})[key_lower] = found.id
                    _logger.info("✅ _goc_material search hit name=%s id=%s", nm, found.id)
                    return found.id
                try:
                    with self.env.cr.savepoint():
                        rec = self.env['product.lens.material'].create({'name': nm})
                    cache.setdefault('lens_materials', {})[key_lower] = rec.id
                    _logger.info("✅ _goc_material created name=%s id=%s", nm, rec.id)
                    return rec.id
                except Exception as e:
                    _logger.warning(f"⚠️ Không tạo được product.lens.material name={nm!r}: {e}")
                    return False

            def _goc_index(dto):
                """Get or create product.lens.index from indexdto."""
                if not dto:
                    _logger.info("🔎 _goc_index called with empty dto")
                    return False
                cid = (dto.get('cid') or '').strip().upper()
                name = (dto.get('name') or dto.get('value') or cid or '').strip()
                _logger.info("🔎 _goc_index called cid=%s name=%s", cid or None, name or None)
                if cid:
                    cached = cache.get('lens_indexes', {}).get(cid)
                    if cached:
                        _logger.info("✅ _goc_index cache hit by cid=%s id=%s", cid, cached)
                        return cached
                if name:
                    cached = cache.get('lens_indexes', {}).get(name.upper())
                    if cached:
                        _logger.info("✅ _goc_index cache hit by name=%s id=%s", name, cached)
                        return cached
                found = False
                if cid:
                    found = self.env['product.lens.index'].search([('cid', '=', cid)], limit=1)
                if not found and name:
                    found = self.env['product.lens.index'].search([('name', '=', name)], limit=1)
                if found:
                    if cid:
                        cache.setdefault('lens_indexes', {})[cid] = found.id
                    if name:
                        cache.setdefault('lens_indexes', {})[name.upper()] = found.id
                    _logger.info("✅ _goc_index search hit cid=%s name=%s id=%s", cid or None, name or None, found.id)
                    return found.id
                if not name:
                    return False
                try:
                    create_vals = {'name': name}
                    if cid and 'cid' in self.env['product.lens.index']._fields:
                        create_vals['cid'] = cid
                    with self.env.cr.savepoint():
                        rec = self.env['product.lens.index'].create(create_vals)
                    if cid:
                        cache.setdefault('lens_indexes', {})[cid] = rec.id
                    cache.setdefault('lens_indexes', {})[name.upper()] = rec.id
                    _logger.info("✅ _goc_index created cid=%s name=%s id=%s", cid or None, name, rec.id)
                    return rec.id
                except Exception as e:
                    _logger.warning(f"⚠️ Không tạo được product.lens.index cid={cid!r} name={name!r}: {e}")
                    return False

            def _goc_power(raw_val, power_type):
                """Get or create product.lens.power by float value and type (sph/cyl/add)."""
                # Dùng `is None` thay vì `in (None, '', False)` vì 0.0 == False trong Python
                # → SPH=0.00, CYL=0.00, ADD=0.00 là giá trị hợp lệ, không được bỏ qua
                if raw_val is None or raw_val == '':
                    return False
                try:
                    fval = float(raw_val)
                except (TypeError, ValueError):
                    return False
                # Format: "+1.25", "-2.75", "+0.00"
                formatted = f"{fval:+.2f}"
                cache_key = f"{power_type}:{formatted}"
                cached = cache.get('lens_powers_m2o', {}).get(cache_key)
                if cached:
                    return cached
                found = self.env['product.lens.power'].search(
                    [('value', '=', fval), ('type', '=', power_type)], limit=1
                )
                if found:
                    cache.setdefault('lens_powers_m2o', {})[cache_key] = found.id
                    return found.id
                try:
                    with self.env.cr.savepoint():
                        rec = self.env['product.lens.power'].create({
                            'name': formatted,
                            'value': fval,
                            'type': power_type,
                        })
                    cache.setdefault('lens_powers_m2o', {})[cache_key] = rec.id
                    _logger.info("✅ _goc_power created type=%s value=%s id=%s", power_type, formatted, rec.id)
                    return rec.id
                except Exception as e:
                    _logger.warning("⚠️ Không tạo được product.lens.power type=%s value=%s: %s", power_type, formatted, e)
                    return False

            # Resolve Many2one IDs (get-or-create)
            d1_id = _goc_design(design_1)
            d2_id = _goc_design(design_2)
            material_raw = first_non_empty(item.get('material'), item.get('materialdto'))
            mat_id = _goc_material(material_raw)
            idx_id = _goc_index(index_dto)

            _logger.info(
                "🔍 Lens mapping candidates | design1=%s | design2=%s | material=%s | index_cid=%s | index_name=%s | coating_ids=%s",
                design_1 or None,
                design_2 or None,
                material_raw or None,
                (index_dto.get('cid') or None),
                (index_dto.get('name') or index_dto.get('value') or None),
                coating_ids,
            )

            lens_display_vals = {
                'lens_base_curve': float(item.get('base') or 0),
                # Many2one chuẩn (get-or-create)
                'lens_design1_id': d1_id,
                'lens_design2_id': d2_id,
                'lens_material_id': mat_id,
                'lens_index_id': idx_id,
                'lens_uv_id': self._resolve_uv_id(uv_dto, cache) or None,
                'lens_color_int': (item.get('colorInt') or '') or None,
                # Màu sắc HMC / Photochromic / Tinted (get-or-create product.cl)
                'lens_cl_hmc_id': self._get_id_with_fallback(
                    cache, 'colors',
                    item.get('clhmcdto') or item.get('clHmcdto') or item.get('clHMCdto') or item.get('clHmcDto')
                ) or None,
                'lens_cl_pho_id': self._get_id_with_fallback(
                    cache, 'colors',
                    item.get('clphodto') or item.get('clPhodto') or item.get('clPHOdto') or item.get('clPhoDto')
                ) or None,
                'lens_cl_tint_id': self._get_id_with_fallback(
                    cache, 'colors',
                    item.get('clTintdto') or item.get('cltintdto') or item.get('clTINTdto') or item.get('clTintDto')
                ) or None,
                # Many2many coating:
                #   coating_ids có phần tử  → [(6, 0, [id,...])] ghi vào DB
                #   coating_ids rỗng        → None → cleanup loop loại bỏ → giữ dữ liệu cũ
                'lens_coating_ids': [(6, 0, coating_ids)] if coating_ids else None,
                'lens_template_key': lens_template_key,
                # SPH / CYL / ADD → Many2one (get-or-create từ product.lens.power)
                'lens_sph_id': _goc_power(extract_number(sph_raw), 'sph'),
                'lens_cyl_id': _goc_power(extract_number(cyl_raw), 'cyl'),
                'lens_add_id': _goc_power(extract_number(add_raw), 'add'),
                # Giữ lại x_sph/x_cyl/x_add (float legacy) để migrate sau
                'x_sph': safe_float(extract_number(sph_raw)),
                'x_cyl': safe_float(extract_number(cyl_raw)),
                'x_add': safe_float(extract_number(add_raw)),
                'x_axis': safe_int(axis_raw),
                'x_prism': extract_label(item.get('prism')),
                'x_prism_base': extract_label(item.get('prismBase') or item.get('prism_base')),
                'x_mir_coating': extract_label(item.get('mirCoating')) or None,
                'x_diameter': safe_int(item.get('diameter')),
            }

            # ── Cleanup: CHỈ loại bỏ None ──────────────────────────────────────────────
            # Quy tắc:
            #   None              → key bị bỏ → ORM không ghi, giữ nguyên dữ liệu cũ
            #   False             → GIỮ LẠI  → ORM ghi False
            #   ''                → GIỮ LẠI  → ORM ghi '' (Char field trống)
            #   [(6, 0, [...])]   → GIỮ LẠI  → ORM cập nhật Many2many
            for _k, _v in list(lens_display_vals.items()):
                if _v is None:
                    lens_display_vals.pop(_k)

            _logger.info(
                "📝 [LENS VALS] uv=%s | coating=%s | cl_hmc=%s | cl_pho=%s | cl_tint=%s",
                lens_display_vals.get('lens_uv_id', 'SKIPPED'),
                lens_display_vals.get('lens_coating_ids', 'SKIPPED'),
                lens_display_vals.get('lens_cl_hmc_id', 'SKIPPED'),
                lens_display_vals.get('lens_cl_pho_id', 'SKIPPED'),
                lens_display_vals.get('lens_cl_tint_id', 'SKIPPED'),
            )

            vals.update(lens_display_vals)

        # ─── Opt specs (Hướng B: field trực tiếp trên template) ──────────────────────
        if product_type == 'opt':
            vals.update(self._prepare_opt_vals(item, cache))

        return vals, cache['products'].get(default_code)

    def _prepare_lens_vals(self, item, cache):
        # Xử lý SPH/CYL: API trả về string, cần ép kiểu float rồi tra cache
        def get_power_id(val, t):
            try:
                fval = float(val)
            except Exception:
                return False
            return cache['lens_powers'][t].get(fval)

        sph_val = item.get('sph')
        cyl_val = item.get('cyl')
        design_name = (item.get('design') or '').strip().lower()
        material_name = (item.get('material') or '').strip().lower()

        def safe_int(val, default=0):
            if val is None or val == '': return default
            try: return int(str(val).replace('mm', '').replace('MM', '').strip() or default)
            except Exception: return default

        def safe_float(val, default=0.0):
            try: return float(val) if val is not None and val != '' else default
            except Exception: return default

        v = {
            'sph_id': get_power_id(sph_val, 'sph'),
            'cyl_id': get_power_id(cyl_val, 'cyl'),
            'design_id': cache['lens_designs'].get(design_name),
            'material_id': cache['lens_materials'].get(material_name),
            'lens_add': safe_float(item.get('lensAdd')),   # FIX: len_add → lens_add
            'diameter': safe_int(item.get('diameter')),     # Integer field
            'base_curve': safe_float(item.get('base')),
            'axis': safe_int(item.get('axis')),
            'corridor': item.get('corridor') or '',
            'abbe': item.get('abbe') or '',
            'prism': item.get('prism') or '',
            'prism_base': item.get('prismBase') or '',
        }
        # Coating/Feature xử lý sau nếu cần
        return v

    def _resolve_m2m_ids(self, dtos, cache_key, cache, model_name=None, log_label=''):
        """Giải quyết list DTO từ API → danh sách Odoo IDs cho Many2many.

        Args:
            dtos       : list DTO từ API (mỗi phần tử là dict có 'cid' / 'name').
            cache_key  : key trong dict cache (ví dụ 'materials', 'coatings').
            cache      : dict cache đang dùng.
            model_name : nếu có, sẽ tự động create bản ghi chưa tồn tại.
            log_label  : nhãn log dể debug.

        Returns:
            Odoo M2M command list: [(6, 0, ids)] nếu có id, [(5, 0, 0)] nếu rỗng.
        """
        if not dtos:
            _logger.debug(f"🔍 M2M [{log_label}]: API không trả list hoặc rỗng.")
            return [(5, 0, 0)]

        ids = []
        for dto in dtos:
            if not isinstance(dto, dict):
                continue
            cid = (dto.get('cid') or '').strip().upper()
            name = (dto.get('name') or '').strip()
            if not cid and not name:
                _logger.debug(f"⚠️ M2M [{log_label}]: DTO không có cid/name hợp lệ: {dto}")
                continue

            # Tìm trong cache
            rid = cache.get(cache_key, {}).get(cid) if cid else None
            if not rid and name:
                rid = cache.get(cache_key, {}).get(name.upper())

            # Tự động create nếu có model_name và chưa tìm thấy
            if not rid and model_name:
                try:
                    model_fields = self.env[model_name]._fields
                    vals_create = {'name': name or cid}
                    if 'cid' in model_fields and cid:
                        vals_create['cid'] = cid
                    elif 'code' in model_fields and cid:
                        vals_create['code'] = cid
                    rec = self.env[model_name].create(vals_create)
                    rid = rec.id
                    if cid:
                        cache.setdefault(cache_key, {})[cid] = rid
                    if name:
                        cache.setdefault(cache_key, {})[name.upper()] = rid
                    _logger.debug(f"✅ M2M [{log_label}]: Tạo mới {model_name} cid={cid!r} name={name!r}")
                except Exception as e:
                    _logger.warning(f"⚠️ M2M [{log_label}]: Không tạo được {model_name} cid={cid!r}: {e}")

            if rid:
                ids.append(rid)
            else:
                _logger.debug(f"⚠️ M2M [{log_label}]: Không tìm thấy cid={cid!r} name={name!r} trong cache[{cache_key!r}]")

        return [(6, 0, ids)] if ids else [(5, 0, 0)]

    def _prepare_opt_vals(self, item, cache):
        """Map opt specs từ API trực tiếp vào opt_* fields trên product.template."""
        return {
            'opt_season': item.get('season', ''),
            'opt_model': item.get('model', ''),
            'opt_serial': item.get('serial', ''),
            'opt_oem_ncc': item.get('oemNcc', ''),
            'opt_sku': item.get('sku', ''),
            'opt_color': item.get('color', ''),
            'opt_gender': str(item.get('gender', '')) if item.get('gender') else False,
            'opt_temple_width': int(item.get('templeWidth') or 0),
            'opt_lens_width': int(item.get('lensWidth') or 0),
            'opt_lens_span': int(item.get('lensSpan') or 0),
            'opt_lens_height': int(item.get('lensHeight') or 0),
            'opt_bridge_width': int(item.get('bridgeWidth') or 0),
            'opt_color_lens_id': self._get_id_with_fallback(cache, 'colors', item.get('colorLensdto')),
            # ─── Thiết kế gọng – auto-create nếu chưa có bản ghi master ──────────────
            'opt_frame_id': self._get_or_create_master(cache, 'frames', item.get('framedto')),
            'opt_frame_type_id': self._get_or_create_master(cache, 'frame_types', item.get('frameTypedto')),
            'opt_shape_id': self._get_or_create_master(cache, 'shapes', item.get('shapedto')),
            'opt_ve_id': self._get_or_create_master(cache, 'ves', item.get('vedto')),
            'opt_temple_id': self._get_or_create_master(cache, 'temples', item.get('templedto')),
            # ─── Chất liệu gọng – auto-create nếu chưa có bản ghi master ─────────────
            'opt_material_ve_id': self._get_or_create_master(cache, 'materials', item.get('materialVedto')),
            'opt_material_temple_tip_id': self._get_or_create_master(cache, 'materials', item.get('materialTempleTipdto')),
            'opt_material_lens_id': self._get_or_create_master(cache, 'materials', item.get('materialLensdto')),
            # ─── Màu sắc (Many2one giữ lại tương thích, M2M mới bên dưới) ───────────────
            'opt_color_front_id': self._get_or_create_color_by_string(
                item.get('colorFront'), cache),
            'opt_color_temple_id': self._get_or_create_color_by_string(
                item.get('colorTemple'), cache),
            # ─── Chất liệu Many2many – key thực tế từ API: materialsFrontdto / materialsTempledto
            'opt_materials_front_ids': self._resolve_opt_material_dtos(
                item,
                ['materialsFrontdto', 'materialsFrontDto',       # ✅ key thực tế
                 'materialFrontdtos', 'materialFrontDtos',       # fallback cũ
                 'materialFrontdto',  'materialFrontDto'],
                cache, log_label='materialsFront'
            ),
            'opt_materials_temple_ids': self._resolve_opt_material_dtos(
                item,
                ['materialsTempledto', 'materialsTempleDto',     # ✅ key thực tế
                 'materialTempledtos', 'materialTempleDtos',     # fallback cũ
                 'materialTempledto',  'materialTempleDto'],
                cache, log_label='materialsTemple'
            ),
            # ─── Coating Many2many – key thực tế: coatingsdto ──────────────────────────
            'opt_coating_ids': self._resolve_m2m_ids(
                item.get('coatingsdto')                          # ✅ key thực tế
                or item.get('coatingdtos') or item.get('coatingDtos'),
                'coatings', cache,
                model_name=None, log_label='coatingsdto'
            ),
            # ─── Màu sắc Many2many – API trả plain string, không phải DTO ──────────────
            'opt_color_front_ids': self._resolve_color_string_to_m2m(
                item.get('colorFront'), cache, log_label='colorFront'
            ),
            'opt_color_temple_ids': self._resolve_color_string_to_m2m(
                item.get('colorTemple'), cache, log_label='colorTemple'
            ),
            # ─── RS adapter: field mới chuẩn hóa theo RS (dai_mat, ngang_mat, ...) ───
            'dai_mat': float(item.get('lensLength') or item.get('daiMat') or 0),
            'ngang_mat': float(item.get('lensWidth') or item.get('nangMat') or 0),
            'bao_hanh_ban_le': int(
                (item.get('productdto') or {}).get('retailWarrantyMonths')
                or item.get('baoHanhBanLe')
                or 0
            ),
        }

    def _debug_log_item_structure(self, item, idx):
        """Log RAW JSON structure của một item từ RS – dùng để phân tích cấu trúc.
        Bật/tắt bằng biến môi trường LOG_LENS_RAW_STRUCTURE=True (áp dụng cả lens lẫn opt).
        """
        if os.getenv('LOG_LENS_RAW_STRUCTURE', 'False').lower() != 'true':
            return

        prefix = f"[RAW ITEM idx={idx}]"

        # ── 1. Full pretty JSON ────────────────────────────────────────────────
        try:
            _logger.info("%s FULL JSON:\n%s", prefix,
                         json.dumps(item, ensure_ascii=False, indent=2, default=str))
        except Exception as e:
            _logger.warning("%s Không dump được JSON: %s", prefix, e)

        # ── 2. Danh sách key cấp 1 ────────────────────────────────────────────
        _logger.info("%s TOP-LEVEL KEYS (%d): %s", prefix, len(item), list(item.keys()))

        # ── 3. Kiểm tra key chứa attribute dạng list/dict ─────────────────────
        ATTR_KEYS = [
            'attributes', 'properties', 'lensProperties', 'options',
            'combos', 'productAttributes', 'specifications', 'flags',
            'coating', 'coatings', 'coatingdtos', 'coatingDtos', 'coatingsdto',
            'hmc', 'hmcDto', 'isHmc',
            'photochromic', 'phoDto', 'isPhotochromic',
            'tinted', 'tintDto', 'isTinted',
            # OPT material keys
            'materialFrontdtos', 'materialFrontDtos', 'materialFrontdto', 'materialFrontDto',
            'materialTempledtos', 'materialTempleDtos', 'materialTempledto', 'materialTempleDto',
            'materialVedto', 'materialVeDto', 'materialLensdto', 'materialLensDto',
            'materialTempleTipdto', 'materialTempleTipDto',
            # OPT color keys
            'colorFrontdto', 'colorFrontDto', 'colorTempledto', 'colorTempleDto',
            'colorFrontdtos', 'colorFrontDtos', 'colorTempledtos', 'colorTempleDtos',
        ]
        for k in ATTR_KEYS:
            if k not in item:
                continue
            v = item[k]
            if isinstance(v, list):
                _logger.info("%s KEY=%r → list (%d items):", prefix, k, len(v))
                for i, elem in enumerate(v):
                    if isinstance(elem, dict):
                        _logger.info("  [%d] dict keys=%s", i, list(elem.keys()))
                    else:
                        _logger.info("  [%d] %s = %r", i, type(elem).__name__, elem)
            elif isinstance(v, dict):
                _logger.info("%s KEY=%r → dict keys=%s", prefix, k, list(v.keys()))
            else:
                _logger.info("%s KEY=%r → %s = %r", prefix, k, type(v).__name__, v)

        # ── 4. Type map của toàn bộ item ──────────────────────────────────────
        type_map = []
        for k, v in item.items():
            if isinstance(v, list):
                type_map.append(f"{k}: list[{len(v)}]")
            elif isinstance(v, dict):
                type_map.append(f"{k}: dict({len(v)} keys)")
            else:
                type_map.append(f"{k}: {type(v).__name__}={v!r}")
        _logger.info("%s TYPE MAP:\n  %s", prefix, '\n  '.join(type_map))

    def _process_lens_variant_items(self, items, cache):
        total = len(items)
        success = failed = 0

        _logger.info(f"🔄 Processing {total} lens items (template-based)...")

        for idx, item in enumerate(items):
            try:
                with self.env.cr.savepoint():
                    # Mỗi item chạy trong savepoint riêng để tránh lỗi SQL làm hỏng cả transaction.
                    # ── Raw structure debug (bật bằng LOG_LENS_RAW_STRUCTURE=True) ──
                    self._debug_log_item_structure(item, idx)

                    tmpl, action = self._get_or_create_lens_template(item, cache, return_action=True)
                    if not tmpl:
                        failed += 1
                        self._sync_audit_record_issue(
                            issue_kind='skip',
                            product_type='lens',
                            stage='lens_template_upsert',
                            item=item,
                            field='template',
                            source_value=(item.get('productdto') or {}).get('cid'),
                            normalized_value=None,
                            error_type='NO_TEMPLATE',
                            error_message='Template creation/update returned empty result',
                        )
                        continue
                    success += 1
                    if action == 'create':
                        self._sync_audit_count('create', 'lens', 1)
                    elif action == 'update':
                        self._sync_audit_count('update', 'lens', 1)
            except Exception as e:
                failed += 1
                import traceback
                self._sync_audit_record_issue(
                    issue_kind='error',
                    product_type='lens',
                    stage='lens_template_upsert',
                    item=item,
                    field='template',
                    source_value=(item.get('productdto') or {}).get('cid'),
                    normalized_value=None,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                _logger.error(
                    f"Lens variant error idx={idx}: {e}\n{traceback.format_exc()}"
                )

        return success, failed

    def _process_accessory_batch(self, items, cache):
        """Xử lý accessories: mỗi record một savepoint độc lập + logging đầy đủ.
        HOÀN TOÀN TÁCH BIỆT khỏi lens/opt. Không sửa bất kỳ helper nào lens/opt dùng.
        """
        import json as _json_acc
        import traceback as _tb_acc

        self._load_env()
        log_raw   = os.getenv('LOG_ACCESSORY_RAW_STRUCTURE', 'False').lower() == 'true'
        log_debug = os.getenv('LOG_ACCESSORY_DEBUG',         'False').lower() == 'true'
        raw_limit = int(os.getenv('LOG_RAW_SAMPLE_LIMIT',   '3'))

        total   = len(items)
        success = 0
        skipped = 0
        errors  = 0
        raw_logged = 0
        err_by_step = {'currency': 0, 'map': 0, 'create': 0, 'write': 0, 'other': 0}

        _logger.info(
            "[ACC_SYNC] Starting batch: total=%d "
            "log_raw=%s log_debug=%s raw_limit=%d",
            total, log_raw, log_debug, raw_limit
        )
        # [ACC_SYNC][FETCH] — dữ liệu đã được fetch trước, log tổng ở đây
        _logger.info(
            "[ACC_SYNC][FETCH] status=pre-fetched duration_ms=N/A items=%d", total
        )

        for idx, item in enumerate(items):
            dto  = item.get('productdto') or {}
            cid  = (dto.get('cid') or '').strip()
            sku  = cid or f'idx_{idx}'
            ext_id = (dto.get('id') or dto.get('externalId') or cid or f'idx_{idx}')
            name = dto.get('fullname') or dto.get('name') or 'Unknown'

            _logger.info(
                "[ACC_SYNC][START] idx=%d ext_id=%s sku=%s name=%s",
                idx, ext_id, sku, name
            )

            step = 'init'
            try:
                with self.env.cr.savepoint():

                    # ── RAW_KEYS ────────────────────────────────────────────────
                    if log_debug:
                        _logger.info(
                            "[ACC_SYNC][RAW_KEYS] idx=%d keys=%s",
                            idx, list(item.keys())
                        )

                    # ── RAW_JSON sample (giới hạn raw_limit record + truncate 2KB) ──
                    if log_raw and raw_logged < raw_limit:
                        try:
                            raw_str = _json_acc.dumps(
                                item, ensure_ascii=False, default=str
                            )
                            if len(raw_str) > 2048:
                                raw_str = raw_str[:2048] + '...(truncated)'
                            _logger.info(
                                "[ACC_SYNC][RAW_JSON] idx=%d:\n%s", idx, raw_str
                            )
                            raw_logged += 1
                        except Exception as _je:
                            _logger.warning(
                                "[ACC_SYNC] json dump error idx=%d: %s", idx, _je
                            )

                    # ── MAP_IN ──────────────────────────────────────────────────
                    rs_uom = self._extract_uom_name_from_payload(item, dto) or 'N/A'
                    cz_dto = dto.get('currencyZoneDTO') or {}
                    _logger.info(
                        "[ACC_SYNC][MAP_IN] sku=%s important_fields={"
                        "currency=%s, brand=%s, country=%s, warranty=%s, "
                        "uom=%s, category=%s, price=%s, cost=%s, barcode=%s}",
                        sku,
                        cz_dto.get('cid') or 'N/A',
                        (dto.get('tmdto')      or {}).get('cid') or 'N/A',
                        (dto.get('codto')      or {}).get('cid') or 'N/A',
                        (dto.get('warrantydto') or {}).get('cid') or 'N/A',
                        rs_uom,
                        (dto.get('groupdto')   or {}).get('name') or 'N/A',
                        dto.get('rtPrice', 0),
                        dto.get('orPrice', 0),
                        dto.get('barcode') or 'N/A',
                    )

                    # ── currency: bắt buộc ──────────────────────────────────────
                    step = 'ref_currency'
                    cur_code = (cz_dto.get('cid') or '').strip()
                    _cur_id, _cur_err = self._acc_get_or_create_ref(
                        'currency',
                        cur_code or (cz_dto if cz_dto else None),
                        cache, 'acc_currency', 'res.currency',
                        name_field='name', code_field='name',
                        required=True, sku=sku
                    )
                    if _cur_err and not _cur_id:
                        raise ValueError(
                            f"currency invalid/not-creatable: {_cur_err}"
                        )

                    # ── brand: optional ─────────────────────────────────────────
                    step = 'ref_brand'
                    self._acc_get_or_create_ref(
                        'brand', dto.get('tmdto'), cache, 'brands', 'product.brand',
                        name_field='name', code_field='cid',
                        required=False, sku=sku
                    )

                    # ── country: optional ───────────────────────────────────────
                    step = 'ref_country'
                    self._acc_get_or_create_ref(
                        'country', dto.get('codto'), cache, 'countries',
                        'product.country',
                        name_field='name', code_field='cid',
                        required=False, sku=sku
                    )

                    # ── warranty: optional ──────────────────────────────────────
                    step = 'ref_warranty'
                    self._acc_get_or_create_ref(
                        'warranty', dto.get('warrantydto'), cache, 'warranties',
                        'product.warranty',
                        name_field='name', code_field='cid',
                        required=False, sku=sku
                    )

                    # ── map vals (dùng hàm chung — không sửa) ──────────────────
                    step = 'map'
                    vals, pid = self._prepare_base_vals(item, cache, 'accessory')

                    # ── Accessory-specific field mapping (chỉ cho accessory) ──────────
                    step = 'acc_fields'
                    _fdbg = os.getenv('LOG_ACCESSORY_FIELD_DEBUG', 'False').lower() == 'true'

                    # Helper: an toàn safe_float
                    def _sf(v):
                        try:
                            return float(v) if v not in (None, '', False) else 0.0
                        except (TypeError, ValueError):
                            return 0.0

                    # Helper: thử nhiều key từ item/dto
                    def _pick(*keys):
                        for k in keys:
                            v = item.get(k)
                            if v is not None:
                                return v
                            v = dto.get(k)
                            if v is not None:
                                return v
                        return None

                    # ── Đọc raw values từ RS ─────────────────────────────────────
                    raw_design   = _pick('designdto',  'designDto',  'design')
                    raw_shape    = _pick('shapedto',   'shapeDto',   'shape')
                    raw_material = _pick('materialdto', 'materialDto', 'material')
                    raw_color    = _pick('colordto',   'colorDto',   'color',
                                        'acc_color', 'accColor')
                    raw_width  = _pick('width',  'accWidth',  'acc_width',  'chieu_rong')
                    raw_length = _pick('length', 'accLength', 'acc_length', 'chieu_dai')
                    raw_height = _pick('height', 'accHeight', 'acc_height', 'chieu_cao')
                    raw_head   = _pick('head',   'accHead',   'acc_head',   'dau')
                    raw_body   = _pick('body',   'accBody',   'acc_body',   'than')

                    if _fdbg:
                        _logger.info(
                            "[ACC_FIELD][RAW] sku=%s design=%r shape=%r "
                            "material=%r color=%r "
                            "width=%r length=%r height=%r head=%r body=%r",
                            sku,
                            raw_design, raw_shape, raw_material, raw_color,
                            raw_width, raw_length, raw_height, raw_head, raw_body,
                        )

                    # ── Resolve Many2one IDs (accessory-specific) ────────────────
                    acc_design_id, _ = self._acc_get_or_create_ref(
                        'design_id', raw_design, cache, 'designs',
                        'product.design',
                        name_field='name', code_field='cid',
                        required=False, sku=sku
                    )
                    acc_shape_id, _ = self._acc_get_or_create_ref(
                        'shape_id', raw_shape, cache, 'shapes',
                        'product.shape',
                        name_field='name', code_field='cid',
                        required=False, sku=sku
                    )
                    acc_material_id, _ = self._acc_get_or_create_ref(
                        'material_id', raw_material, cache, 'materials',
                        'product.material',
                        name_field='name', code_field='cid',
                        required=False, sku=sku
                    )
                    # color_id → product.color (KHÁC product.cl của lens)
                    acc_color_id, _ = self._acc_get_or_create_ref(
                        'color_id', raw_color, cache, 'acc_colors',
                        'product.color',
                        name_field='name', code_field='cid',
                        required=False, sku=sku
                    )

                    # ── Cập nhật vals với các field phụ kiện ───────────────────────
                    acc_field_vals = {
                        'design_id':   acc_design_id or False,
                        'shape_id':    acc_shape_id  or False,
                        'material_id': acc_material_id or False,
                        'color_id':    acc_color_id  or False,
                        'acc_width':   _sf(raw_width),
                        'acc_length':  _sf(raw_length),
                        'acc_height':  _sf(raw_height),
                        'acc_head':    _sf(raw_head),
                        'acc_body':    _sf(raw_body),
                    }
                    vals.update(acc_field_vals)

                    if _fdbg:
                        _logger.info(
                            "[ACC_FIELD][MAPPED] sku=%s "
                            "design_id=%s shape_id=%s material_id=%s color_id=%s "
                            "acc_width=%s acc_length=%s acc_height=%s "
                            "acc_head=%s acc_body=%s",
                            sku,
                            acc_design_id, acc_shape_id, acc_material_id, acc_color_id,
                            _sf(raw_width), _sf(raw_length), _sf(raw_height),
                            _sf(raw_head), _sf(raw_body),
                        )

                    # ── MAP_OUT ─────────────────────────────────────────────────
                    _logger.info(
                        "[ACC_SYNC][MAP_OUT] sku=%s mapped_vals={"
                        "default_code=%s, name=%s, type=%s, is_storable=%s, "
                        "categ_id=%s, brand_id=%s, country_id=%s, warranty_id=%s, "
                        "list_price=%s, standard_price=%s}",
                        sku,
                        vals.get('default_code'),
                        vals.get('name'),
                        vals.get('type'),
                        vals.get('is_storable'),
                        vals.get('categ_id'),
                        vals.get('brand_id'),
                        vals.get('country_id'),
                        vals.get('warranty_id'),
                        vals.get('list_price'),
                        vals.get('standard_price'),
                    )

                    # ── create / write ──────────────────────────────────────────
                    seller_payloads = self._extract_seller_payloads(vals)
                    if pid:
                        step = 'write'
                        saved_rec = self.env['product.template'].browse(pid).with_context(
                            tracking_disable=True
                        )
                        saved_rec.write(vals)
                        self._upsert_supplierinfo_payloads(saved_rec, seller_payloads)
                        self._sync_audit_count('update', 'accessory', 1)
                        if log_debug:
                            _logger.info(
                                "[ACC_SYNC][WRITE_OK] sku=%s tmpl_id=%s", sku, pid
                            )
                    else:
                        step = 'create'
                        saved_rec = self.env['product.template'].with_context(
                            tracking_disable=True
                        ).create(vals)
                        self._upsert_supplierinfo_payloads(saved_rec, seller_payloads)
                        cache['products'][saved_rec.default_code] = saved_rec.id
                        self._sync_audit_count('create', 'accessory', 1)
                        if log_debug:
                            _logger.info(
                                "[ACC_SYNC][CREATE_OK] sku=%s new_tmpl_id=%s",
                                sku, saved_rec.id
                            )

                    # ── Readback log (chỉ khi LOG_ACCESSORY_FIELD_DEBUG=True) ──
                    if _fdbg:
                        try:
                            rb = saved_rec
                            _logger.info(
                                "[ACC_FIELD][ODB_READBACK] sku=%s tmpl_id=%s "
                                "design_id=%s(%s) shape_id=%s(%s) "
                                "material_id=%s(%s) color_id=%s(%s) "
                                "acc_width=%s acc_length=%s acc_height=%s "
                                "acc_head=%s acc_body=%s",
                                sku, rb.id,
                                rb.design_id.id if rb.design_id else None,
                                rb.design_id.name if rb.design_id else None,
                                rb.shape_id.id if rb.shape_id else None,
                                rb.shape_id.name if rb.shape_id else None,
                                rb.material_id.id if rb.material_id else None,
                                rb.material_id.name if rb.material_id else None,
                                rb.color_id.id if rb.color_id else None,
                                rb.color_id.name if rb.color_id else None,
                                rb.acc_width, rb.acc_length, rb.acc_height,
                                rb.acc_head, rb.acc_body,
                            )
                        except Exception as _rb_err:
                            _logger.warning("[ACC_FIELD][READBACK_ERR] sku=%s err=%s", sku, _rb_err)

                    success += 1

            except Exception as exc:
                errors  += 1
                skipped += 1
                self._sync_audit_count('skip', 'accessory', 1)

                # Phân loại step để thống kê
                step_key = step.replace('ref_', '')
                if step_key in err_by_step:
                    err_by_step[step_key] += 1
                else:
                    err_by_step['other'] += 1

                # Log raw JSON của record lỗi (lần đầu)
                if log_raw and raw_logged < raw_limit:
                    try:
                        raw_str = _json_acc.dumps(
                            item, ensure_ascii=False, default=str
                        )
                        if len(raw_str) > 2048:
                            raw_str = raw_str[:2048] + '...(truncated)'
                        _logger.info(
                            "[ACC_SYNC][RAW_JSON] ERROR_SAMPLE idx=%d:\n%s",
                            idx, raw_str
                        )
                        raw_logged += 1
                    except Exception:
                        pass

                _logger.exception(
                    "[ACC_SYNC][ERROR] sku=%s step=%s err=%s", sku, step, exc
                )
                _logger.warning("[ACC_SYNC][SKIP] sku=%s", sku)
                self._sync_audit_record_issue(
                    issue_kind='error',
                    product_type='accessory',
                    stage=step,
                    item=item,
                    field=step,
                    source_value=sku,
                    normalized_value=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )

        # ── Tổng kết ────────────────────────────────────────────────────────────
        _logger.info(
            "[ACC_SYNC][SUMMARY] total=%d success=%d skipped=%d errors=%d",
            total, success, skipped, errors
        )
        _logger.info(
            "[ACC_SYNC][ERROR_BY_STEP] currency=%d map=%d create=%d write=%d other=%d",
            err_by_step.get('currency', 0),
            err_by_step.get('map',      0),
            err_by_step.get('create',   0),
            err_by_step.get('write',    0),
            err_by_step.get('other',    0),
        )

        return success, errors

    def _process_batch(self, items, cache, product_type, child_model=None):
        """
        Xử lý batch create/update sản phẩm từ API.
        - Lens và Opt: specs đã được map trực tiếp vào template (Hướng B).
        - Accessory và các loại khác: chỉ tạo/update product.template.
        """
        if product_type == 'lens':
            return self._process_lens_variant_items(items, cache)

        # Accessory: xử lý per-record với savepoint riêng + logging đầy đủ
        # KHÔNG thay đổi gì ở đây liên quan lens/opt
        if product_type == 'accessory':
            return self._process_accessory_batch(items, cache)

        total = len(items)
        success = failed = 0
        to_create, to_update = [], []
        to_create_supplier_payloads = []
        to_create_meta = []

        has_child = False  # Hướng B: không còn dùng child model cho lens hay opt
        child_vals_map = {}    # tmpl_id → child_vals (cho opt)
        new_child_data = []    # [(idx, child_vals)] cho opt create

        _logger.info(f"🔄 Processing {total} {product_type} items...")

        # DEBUG: Log cấu trúc item đầu tiên để xác nhận field names từ API
        if items:
            first_item = items[0]
            _logger.info(f"🔍 DEBUG [{product_type}] item keys at root: {list(first_item.keys())}")
            dto0 = first_item.get('productdto') or {}
            _logger.info(f"🔍 DEBUG [{product_type}] productdto keys: {list(dto0.keys())}")
            _logger.info(f"🔍 DEBUG [{product_type}] model={first_item.get('model')!r}, color={first_item.get('color')!r}")
            _logger.info(f"🔍 DEBUG [{product_type}] cid={dto0.get('cid')!r}")
            if product_type == 'accessory':
                import json as _json
                _logger.info(f"🧩 ACCESSORY FULL ITEM SAMPLE:\n{_json.dumps(first_item, ensure_ascii=False, default=str, indent=2)}")

        # ─── Bước 1: Chuẩn bị dữ liệu ────────────────────────────────────
        for idx, item in enumerate(items):
            try:
                with self.env.cr.savepoint():
                    # Log RAW structure cho opt (bật bằng LOG_LENS_RAW_STRUCTURE=True)
                    if product_type == 'opt':
                        self._debug_log_item_structure(item, idx)
                    vals, pid = self._prepare_base_vals(item, cache, product_type)
                    c_vals = {}
                    # Log currency_id cho từng phụ kiện
                    if product_type == 'accessory':
                        _cur_code = (item.get('productdto') or {}).get('currencyZoneDTO', {}).get('cid', '')
                        _cur_id = vals.get('currency_id') or 'N/A'
                        _logger.info(f"🔸 Accessory idx={idx} currency_code={_cur_code} currency_id={_cur_id} default_code={vals.get('default_code')}")
                    if has_child and product_type == 'opt':
                        c_vals = self._prepare_opt_vals(item, cache)
                    seller_payloads = self._extract_seller_payloads(vals)
                    if pid:
                        to_update.append((pid, vals, seller_payloads, item))
                        if has_child:
                            child_vals_map[pid] = c_vals
                    else:
                        to_create.append(vals)
                        to_create_supplier_payloads.append(seller_payloads)
                        to_create_meta.append(item)
                        if has_child:
                            new_child_data.append((idx, c_vals))
            except Exception as e:
                failed += 1
                self._sync_audit_count('skip', product_type, 1)
                import traceback
                dto = item.get('productdto') or {}
                _dc = (dto.get('cid') or '').strip() or 'N/A'
                _logger.error(
                    f"Prepare error [{product_type}] idx={idx} default_code={_dc}: {e}\n{traceback.format_exc()}"
                )
                self._sync_audit_record_issue(
                    issue_kind='error',
                    product_type=product_type,
                    stage='prepare',
                    item=item,
                    field='prepare_base_vals',
                    source_value=_dc,
                    normalized_value=None,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        # ─── Bước 2: Batch Create ─────────────────────────────────────────
        if to_create:
            batch_size = 100
            for i in range(0, len(to_create), batch_size):
                b_vals = to_create[i:i + batch_size]
                b_supplier_payloads = to_create_supplier_payloads[i:i + batch_size]
                b_meta = to_create_meta[i:i + batch_size]
                b_child = new_child_data[i:i + batch_size] if has_child else []
                b_child_refs = b_child
                try:
                    with self.env.cr.savepoint():
                        recs = self.env['product.template'].with_context(
                            tracking_disable=True
                        ).create(b_vals)

                        for j, rec in enumerate(recs):
                            cache['products'][rec.default_code] = rec.id
                            if j < len(b_supplier_payloads):
                                self._upsert_supplierinfo_payloads(rec, b_supplier_payloads[j])
                        success += len(recs)
                        self._sync_audit_count('create', product_type, len(recs))
                except Exception as e:
                    failed += len(b_vals)
                    import traceback
                    _logger.error(f"Batch Create Error [{product_type}]: {e}\n{traceback.format_exc()}")
                    for meta_item in b_meta:
                        self._sync_audit_record_issue(
                            issue_kind='error',
                            product_type=product_type,
                            stage='batch_create',
                            item=meta_item,
                            field='create',
                            source_value=(meta_item.get('productdto') or {}).get('cid') if isinstance(meta_item, dict) else None,
                            normalized_value=None,
                            error_type=type(e).__name__,
                            error_message=str(e),
                        )
                    continue

                # Tạo child records riêng lẻ (savepoint độc lập)
                if has_child and b_child_refs:
                    for j, rec in enumerate(recs):
                        if j >= len(b_child_refs):
                            break
                        _, cv = b_child_refs[j]
                        if not cv:
                            _logger.warning(f"⚠️ Bỏ qua child record rỗng cho product {rec.id}")
                            continue
                        cv['product_tmpl_id'] = rec.id
                        try:
                            with self.env.cr.savepoint():
                                self.env[child_model].create(cv)
                        except Exception as e:
                            _logger.error(f"Child Create Error product {rec.id}: {e}")

        # ─── Bước 3: Batch Update ─────────────────────────────────────────
        for pid, vals, seller_payloads, source_item in to_update:
            try:
                with self.env.cr.savepoint():
                    product_tmpl = self.env['product.template'].browse(pid).with_context(
                        tracking_disable=True
                    )
                    product_tmpl.write(vals)
                    self._upsert_supplierinfo_payloads(product_tmpl, seller_payloads)

                    if has_child and pid in child_vals_map:
                        c_vals = child_vals_map[pid]
                        cmap = cache.get('opt_records', {})
                        if pid in cmap:
                            self.env[child_model].browse(cmap[pid]).write(c_vals)
                        else:
                            c_vals['product_tmpl_id'] = pid
                            new_id = self.env[child_model].create(c_vals).id
                            cmap[pid] = new_id

                    success += 1
                    self._sync_audit_count('update', product_type, 1)
            except Exception as e:
                failed += 1
                _logger.error(f"Update Error [{product_type}] tmpl_id={pid}: {e}")
                self._sync_audit_record_issue(
                    issue_kind='error',
                    product_type=product_type,
                    stage='update',
                    item=source_item,
                    field='write',
                    source_value=pid,
                    normalized_value=None,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        return success, failed


    def sync_products_from_springboot(self):
        # If called from cron/server action, self might be empty
        rec = self
        if not rec:
            rec = self.search([], limit=1, order='last_sync_date desc')
            if not rec:
                rec = self.create({'name': 'Đồng bộ tự động hàng ngày'})
        return rec._run_sync()

    def sync_products_limited(self, limit=200):
        return self._run_sync(limit)

    def _run_sync(self, limit=None):
        self.ensure_one()
        final_status = 'error'
        try:
            self._init_sync_audit()
            self.write({'sync_status': 'in_progress', 'sync_log': 'Đang đồng bộ...', 'last_sync_date': fields.Datetime.now()})
            self.env.cr.commit()
            
            token = self._get_access_token()
            cache = self._preload_all_data()
            cfg = self._get_api_config()
            stats = {}
            
            # Lens – specs đã map trực tiếp vào template (Hướng B)
            # Mỗi bản ghi lens từ API → 1 product.template (default variant duy nhất)
            items = self._fetch_all_items(cfg['lens_endpoint'], token, 'Lens', limit)
            self._sync_audit_count('input', 'lens', len(items))
            s, f = self._process_batch(items, cache, 'lens')  # Không truyền child_model
            stats['lens'] = s
            stats['failed'] = f
            self.env.cr.commit()

            try:
                self._sync_lens_stock(token, cfg, cache)
            except Exception as e:
                _logger.warning(f"⚠️ Bỏ qua sync tồn kho lens: {e}")
            
            # Opt – specs đã map trực tiếp vào template (Hướng B)
            items = self._fetch_all_items(cfg['opts_endpoint'], token, 'Optical', limit)
            self._sync_audit_count('input', 'opt', len(items))
            s, f = self._process_batch(items, cache, 'opt')  # Không dùng child_model
            stats['opt'] = s
            stats['failed'] += f
            self.env.cr.commit()

            # Access
            items = self._fetch_all_items(cfg['types_endpoint'], token, 'Types', limit)
            self._sync_audit_count('input', 'accessory', len(items))
            s, f = self._process_batch(items, cache, 'accessory')
            stats['acc'] = s
            stats['failed'] += f
            self.env.cr.commit()
            
            total = stats['lens'] + stats['opt'] + stats['acc']
            msg = f"Đã đồng bộ {total} (Mắt:{stats['lens']}, Gọng:{stats['opt']}, Khác:{stats['acc']}). Lỗi: {stats['failed']}"
            has_failed = stats['failed'] > 0
            final_status = 'error' if has_failed else 'success'

            audit_ctx = self._get_sync_audit_ctx() or {}
            text_log_path = audit_ctx.get('text_log_path', '')
            error_json_path = audit_ctx.get('error_json_path', '')
            if text_log_path or error_json_path:
                msg = f"{msg} | Log: {text_log_path} | Error JSON: {error_json_path}"

            self.write({'sync_status': 'error' if has_failed else 'success', 'sync_log': msg,
                       'total_synced': total, 'total_failed': stats['failed'], 
                       'lens_count': stats['lens'], 'opts_count': stats['opt'], 'other_count': stats['acc']})
            
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Đồng bộ hoàn tất', 'message': msg, 'type': 'danger' if has_failed else 'success'}}

        except Exception as e:
            self.env.cr.rollback()
            self._sync_audit_record_issue(
                issue_kind='error',
                product_type='system',
                stage='_run_sync',
                field='run',
                source_value='sync_products',
                normalized_value=None,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            self.write({'sync_status': 'error', 'sync_log': str(e)})
            self.env.cr.commit()
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Đồng bộ thất bại', 'message': str(e), 'type': 'danger'}}
        finally:
            self._finalize_sync_audit(status=final_status)

    def test_api_connection(self):
        try:
            token = self._get_access_token()
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Kết nối thành công', 'message': 'Đã lấy được token.', 'type': 'success'}}
        except Exception as e:
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Kết nối thất bại', 'message': str(e), 'type': 'danger'}}
