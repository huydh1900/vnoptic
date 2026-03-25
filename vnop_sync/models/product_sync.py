# -*- coding: utf-8 -*-
import logging
import json
from psycopg2 import errors
import time
import os
import time
import random
import re
import requests
import urllib3
from collections import defaultdict
from odoo import models, fields, api, _
from odoo.modules.registry import Registry
from odoo.exceptions import UserError
from ..utils import lens_variant_utils

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_logger = logging.getLogger(__name__)


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
                # _logger.warning(f"Could not load .env file: {e}")
                pass

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

    def _init_sync_error_ctx(self):
        """Context thu thập lỗi để hiển thị trong UI (sync_log), tránh phải đọc server log."""
        try:
            sample_limit = int(os.getenv('SYNC_ERROR_SAMPLE_LIMIT', '50'))
        except (TypeError, ValueError):
            sample_limit = 50

        try:
            max_chars = int(os.getenv('SYNC_ERROR_LOG_MAX_CHARS', '20000'))
        except (TypeError, ValueError):
            max_chars = 20000

        return {
            'sample_limit': max(0, sample_limit),
            'max_chars': max(2000, max_chars),
            'samples': [],
            'counts': defaultdict(int),
        }

    def _record_sync_error(self, error_ctx, product_type, stage, ref, exc):
        """Ghi nhận lỗi dạng tóm tắt + sample (không làm phình DB/log quá mức)."""
        if not error_ctx:
            return

        key = f"{(product_type or 'unknown').upper()}:{stage}"
        error_ctx['counts'][key] += 1

        if len(error_ctx['samples']) >= error_ctx['sample_limit']:
            return

        try:
            msg = str(exc)
        except Exception:
            msg = repr(exc)
        msg = (msg or 'Unknown error').replace('\n', ' ')[:500]
        ref_str = (str(ref) if ref is not None else 'N/A')
        error_ctx['samples'].append(f"[{key}] ref={ref_str} err={msg}")

    def _to_float(self, val, default=0.0):
        """Float an toàn cho payload API (hay trả string 'none'/'null')."""
        if val is None:
            return default
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return default
            if s.lower() in ('none', 'null', 'nan', 'n/a', 'na'):
                return default
            s = s.replace(',', '')
            try:
                return float(s)
            except (TypeError, ValueError):
                return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _get_access_token(self):
        config = self._get_api_config()
        login_url = f"{config['base_url']}{config['login_endpoint']}"
        try:
            # _logger.info(f"🔐 Getting token from: {login_url}")
            pass
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

    def _get_sync_batch_size(self):
        """Đọc kích thước batch (mặc định 1000)."""
        try:
            size = int(os.getenv('SYNC_BATCH_SIZE', '200'))
        except (TypeError, ValueError):
            size = 1000
        return max(1, size)

    def _fetch_paged_api(self, endpoint, token, page=0, size=100, max_retries=5, session=None, config=None):
        if config is None:
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
                return data
            except (requests.exceptions.ConnectTimeout,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.ConnectionError) as e:
                if attempt == max_retries:
                    raise UserError(_(f"API request failed after {max_retries} retries: {str(e)}"))
                wait = min(2 ** attempt + random.uniform(0, 2), 60)  # cap 60s
                # _logger.warning(
                # f"⚠️ Timeout/Connection error trang {page} (lần {attempt}/{max_retries}). "
                # f"Thử lại sau {wait:.1f}s... Lỗi: {e}"
                # )
                time.sleep(wait)
            except Exception as e:
                raise UserError(_(f"API request failed: {str(e)}"))

    def _iter_batches(self, endpoint, token, batch_size=200, limit=None):
        """Generator: yield từng batch items, không giữ toàn bộ data trong memory."""
        config = self._get_api_config()
        session = self._make_session()
        page = 0
        fetched = 0

        while True:
            res = self._fetch_paged_api(endpoint, token, page, batch_size, session=session, config=config)
            content = res.get('content', [])
            if not content:
                break

            if limit:
                remaining = limit - fetched
                content = content[:remaining]

            yield content
            fetched += len(content)

            if limit and fetched >= limit:
                break

            total_pages = res.get('totalPages', 1)
            page += 1
            if page >= total_pages:
                break

    def _sync_streaming(self, endpoint, token, product_type, child_model=None, cache=None, error_ctx=None, limit=None):
        """Fetch → process → commit từng batch. Không giữ data trong memory."""
        db = self.env.cr.dbname
        rec_id = self.id
        batch_size = self._get_sync_batch_size()
        total_success = total_failed = 0

        for batch_idx, items in enumerate(self._iter_batches(endpoint, token, batch_size, limit), start=1):
            try:
                with Registry(db).cursor() as cr:
                    env = self.env(cr=cr)
                    self_batch = env[self._name].browse(rec_id)
                    with cr.savepoint():
                        success, failed = self_batch._process_batch(
                            items, cache, product_type, child_model, error_ctx=error_ctx
                        )
                    cr.commit()
                total_success += success
                total_failed += failed
            except Exception as exc:
                total_failed += len(items)
                self._record_sync_error(error_ctx, product_type, 'CHUNK_ERR', ref=f"chunk={batch_idx}", exc=exc)
                continue

        return total_success, total_failed

    def _preload_all_data(self):
        # _logger.info("📦 Pre-loading existing data...")
        pass
        cache = {'products': {}, 'categories': {}, 'suppliers': {}, 'taxes': {}, 'groups': {}, 'groups_by_id': {},
                 'statuses': {}}

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

        # Suppliers
        for s in self.env['res.partner'].search_read([('ref', '!=', False)], ['id', 'ref']):
            cache['suppliers'][s['ref'].upper()] = s['id']

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
            ('brands', 'product.brand', 'name'),  # Fallback to name
            ('countries', 'res.country', 'code'),
            ('warranties', 'product.warranty', 'code'),
            ('groups', 'product.group', 'cid'),
            ('groups', 'product.group', 'name'),
            ('designs', 'product.design', 'name'),
            ('materials', 'product.material', 'cid'),  # Index CID trước (API dùng cid)
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
            cache['opt_records'] = {o['product_tmpl_id'][0]: o['id'] for o in
                                    self.env['product.opt'].search_read([], ['id', 'product_tmpl_id']) if
                                    o.get('product_tmpl_id')}

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
                with self.env.cr.savepoint():
                    rec = self.env['product.cl'].create(vals)
                rid = rec.id
                if cid:
                    cache.setdefault(key, {})[cid] = rid
                cache.setdefault(key, {})[name_upper] = rid
                # _logger.info(f"✅ Auto-created product.cl cid={cid!r} name={name!r}")
                return rid
            except Exception as e:
                # _logger.warning(f"⚠️ Không tạo được product.cl cid={cid!r} name={name!r}: {e}")
                pass
        return False

    # Mapping: cache key → (model name) cho các master data opt
    _MASTER_MODEL_MAP = {
        'frames': 'product.frame',
        'frame_types': 'product.frame.type',
        'shapes': 'product.shape',
        'ves': 'product.ve',
        'temples': 'product.temple',
        'materials': 'product.material',
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
            # _logger.debug(f"⚠️ _get_or_create_master: không tìm thấy và không tạo được [{cache_key}] cid={cid!r} name={name!r}")
            pass
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
            # _logger.info(f"✅ Auto-created [{model_name}] cid={cid!r} name={name!r} → id={rid}")
            return rid
        except Exception as e:
            # _logger.warning(f"⚠️ Không tạo được [{model_name}] cid={cid!r} name={name!r}: {e}")
            pass
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
            # _logger.info(f"✅ Auto-created product.cl name={name!r} id={rec.id}")
            return rec.id
        except Exception as e:
            # _logger.warning(f"⚠️ Không tạo được product.cl name={name!r}: {e}")
            pass
            return False

    def _resolve_color_string_to_m2m(self, color_str, cache, log_label=''):
        """Chuyển plain color string → M2M command cho opt_color_*_ids.
        API trả về 'BLACK+GUN' thay vì DTO → cần xử lý riêng.
        """
        if not color_str or not isinstance(color_str, str):
            return [(5, 0, 0)]
        rid = self._get_or_create_color_by_string(color_str, cache)
        if rid:
            # _logger.debug(f"🔍 [{log_label}]: map string {color_str!r} → cl.id={rid}")
            pass
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

        # res.country is standard Odoo data — only lookup, never create
        if model_name == 'res.country':
            rec = self.env['res.country'].search([('code', '=ilike', cid)], limit=1)
            if not rec and name:
                rec = self.env['res.country'].search([('name', 'ilike', name)], limit=1)
            if rec:
                if cid: cache.setdefault(cache_key, {})[cid.upper()] = rec.id
                return rec.id
            return False

        # Create
        try:
            vals = {'name': name or cid, 'code': cid}
            with self.env.cr.savepoint():
                rec = self.env[model_name].create(vals)
            new_id = rec.id
            if cid: cache[cache_key][cid.upper()] = new_id
            return new_id
        except Exception as e:
            # _logger.error(f"Failed to create {model_name} for {cid}: {e}")
            pass
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
                # _logger.warning(
                # "[ACC_SYNC][REF] field=%s input=%s action=skip result=None error=%s sku=%s",
                # field, input_repr, msg, sku
                # )
                return False, msg
            # _logger.debug(
            # "[ACC_SYNC][REF] field=%s input=empty action=skip sku=%s", field, sku
            # )
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
                # _logger.warning(
                # "[ACC_SYNC][REF] field=%s input=%s action=skip result=None error=%s sku=%s",
                # field, input_repr, msg, sku
                # )
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
                # _logger.debug(
                # "[ACC_SYNC][REF] field=%s input=%s action=cache result=%s sku=%s",
                # field, input_repr, rid, sku
                # )
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
                        # _logger.info(
                        # '[ACC_SYNC][REF] field=%s input=%s action=activate_currency '
                        # 'result=%s sku=%s', field, input_repr, rec.id, sku
                        # )
                    except Exception as _act_err:
                        # _logger.warning(
                        # '[ACC_SYNC][REF] field=%s cannot activate currency %s: %s',
                        # field, cid or name, _act_err
                        # )
                        pass
                if rec:
                    rid = rec.id
                    if cid:
                        cache.setdefault(cache_key, {})[cid.upper()] = rid
                    if name:
                        cache.setdefault(cache_key, {})[name.upper()] = rid
                    # _logger.info(
                    # "[ACC_SYNC][REF] field=%s input=%s action=search result=%s sku=%s",
                    # field, input_repr, rid, sku
                    # )
                    return rid, None

            # ── 4. Tạo mới ────────────────────────────────────────────────────
            action = 'create'
            # res.country là dữ liệu chuẩn Odoo — không tạo mới
            if model_name == 'res.country':
                if required:
                    return False, f"res.country not found: cid={cid} name={name}"
                return False, None
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
                # _logger.info(
                # "[ACC_SYNC][REF] field=%s input=%s action=create result=%s sku=%s",
                # field, input_repr, rid, sku
                # )
                return rid, None

            except Exception as create_err:
                err_str = str(create_err).lower()
                is_dup = any(k in err_str for k in ('unique', 'duplicate', 'integrity'))
                if is_dup:
                    # _logger.warning(
                    # "[ACC_SYNC][REF] field=%s input=%s action=create "
                    # "error=integrity/duplicate → retry_search sku=%s",
                    # field, input_repr, sku
                    # )
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
                            # _logger.info(
                            # "[ACC_SYNC][REF] field=%s input=%s "
                            # "action=search_retry result=%s sku=%s",
                            # field, input_repr, rid, sku
                            # )
                            return rid, None

                # Không recover được
                if required:
                    # _logger.warning(
                    # "[ACC_SYNC][REF] field=%s input=%s action=%s "
                    # "result=None error=%s sku=%s",
                    # field, input_repr, action, create_err, sku
                    # )
                    return False, str(create_err)
                else:
                    # _logger.warning(
                    # "[ACC_SYNC][REF] field=%s input=%s action=%s "
                    # "result=None error=%s sku=%s (optional→set None)",
                    # field, input_repr, action, create_err, sku
                    # )
                    return False, None

        except Exception as outer_err:
            # _logger.warning(
            # "[ACC_SYNC][REF] field=%s input=%s action=%s "
            # "result=None error=%s sku=%s",
            # field, input_repr, action, outer_err, sku
            # )
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
            # _logger.info("✅ Auto-created product.uv cid=%s name=%s id=%s", cid or None, name, rec.id)
            return rec.id
        except Exception as e:
            # _logger.warning("⚠️ Không tạo được product.uv cid=%s name=%s: %s", cid or None, name, e)
            pass
            return False

    def _resolve_opt_material_dtos(self, item, key_variants, cache, log_label=''):
        """Giống _resolve_m2m_ids nhưng thử nhiều key variant từ API (camelCase khác nhau).
        key_variants: list các key cần thử theo thứ tự ưu tiên.
        """
        raw = None
        for key in key_variants:
            raw = item.get(key)
            if raw is not None:
                # _logger.debug(f"🔍 [{log_label}]: tìm thấy key={key!r}, value={raw!r}")
                pass
                break

        if not raw:
            # _logger.debug(f"🔍 [{log_label}]: API không trả dữ liệu (thử: {key_variants})")
            pass
            return [(5, 0, 0)]

        # Nếu API trả về single dict thay vì list → bọc thành list
        if isinstance(raw, dict):
            raw = [raw]
        elif not isinstance(raw, list):
            # _logger.debug(f"⚠️ [{log_label}]: kiểu dữ liệu không mong đợi: {type(raw)}")
            pass
            return [(5, 0, 0)]

        return self._resolve_m2m_ids(raw, 'materials', cache,
                                     model_name='product.material', log_label=log_label)

    def _resolve_lens_coatings(self, item, cache):
        coating_ids = []
        coating_codes = []
        raw_coatings = (
                item.get('coatingsdto')  # API thực tế: coatingsdto (s trước dto)
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
                    # _logger.info("✅ Auto-created product.coating cid=%s name=%s", c_cid or None, c_name)
                except Exception as e:
                    # _logger.warning("⚠️ Không tạo được product.coating cid=%s name=%s: %s", c_cid or None, c_name, e)
                    pass

            if coating_id:
                coating_ids.append(coating_id)

        if not normalized:
            # _logger.info("🔎 _resolve_lens_coatings: no coating payload found in known keys")
            pass

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
            # _logger.info("🧹 Lens cleanup tmpl=%s: removed attribute lines=%s", tmpl.id, attr_count)

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
            # _logger.info(
            # "🧹 Lens cleanup tmpl=%s: removed extra variants=%s keep=%s",
            # tmpl.id, extra_count, keep_variant.id
            # )
        except Exception as e:
            # _logger.warning(
            # "⚠️ Lens cleanup tmpl=%s: cannot unlink extra variants (%s). Error: %s",
            # tmpl.id, len(extra_variants), e
            # )
            pass

    def _get_or_create_lens_template(self, item, cache):
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
            # _logger.info(
            # "📝 [LENS UPDATE id=%s] uv=%s | coating=%s | cl_hmc=%s | cl_pho=%s | cl_tint=%s",
            # tmpl_id,
            # vals.get('lens_uv_id', 'SKIPPED'),
            # vals.get('lens_coating_ids', 'SKIPPED'),
            # vals.get('lens_cl_hmc_id', 'SKIPPED'),
            # vals.get('lens_cl_pho_id', 'SKIPPED'),
            # vals.get('lens_cl_tint_id', 'SKIPPED'),
            # )
            tmpl.write(vals)
            self._cleanup_lens_template_variants(tmpl)
            # _logger.info(
            # "🔍 Lens [UPDATE] %s | material=%s | index=%s | coatings=%s | design1=%s",
            # tmpl.name,
            # tmpl.lens_material_id.name if tmpl.lens_material_id else None,
            # tmpl.lens_index_id.name if tmpl.lens_index_id else None,
            # ', '.join(tmpl.lens_coating_ids.mapped('name')) or None,
            # tmpl.lens_design1_id.name if tmpl.lens_design1_id else None,
            # )
            return tmpl

        # _logger.info(
        # "📝 [LENS CREATE] uv=%s | coating=%s | cl_hmc=%s | cl_pho=%s | cl_tint=%s",
        # vals.get('lens_uv_id', 'SKIPPED'),
        # vals.get('lens_coating_ids', 'SKIPPED'),
        # vals.get('lens_cl_hmc_id', 'SKIPPED'),
        # vals.get('lens_cl_pho_id', 'SKIPPED'),
        # vals.get('lens_cl_tint_id', 'SKIPPED'),
        # )
        tmpl = self.env['product.template'].with_context(tracking_disable=True).create(vals)
        self._cleanup_lens_template_variants(tmpl)
        cache.setdefault('lens_templates', {})[template_key] = tmpl.id
        if tmpl.default_code:
            cache['products'][tmpl.default_code] = tmpl.id
        # _logger.info(
        # "🔍 Lens [CREATE] %s | material=%s | index=%s | coatings=%s | design1=%s",
        # tmpl.name,
        # tmpl.lens_material_id.name if tmpl.lens_material_id else None,
        # tmpl.lens_index_id.name if tmpl.lens_index_id else None,
        # ', '.join(tmpl.lens_coating_ids.mapped('name')) or None,
        # tmpl.lens_design1_id.name if tmpl.lens_design1_id else None,
        # )
        return tmpl

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
            # _logger.warning(f"⚠️ Không lấy được tồn kho lens: {e}")
            pass
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
            # _logger.warning("⚠️ Không tìm thấy internal stock location để cập nhật tồn kho lens.")
            pass
            return

        # _logger.info(f"📦 Lens stock records: {total}")

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
                # _logger.warning(f"⚠️ Lỗi xử lý record tồn kho lens: {e}")
                pass

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
                # _logger.warning(f"⚠️ Lỗi cập nhật tồn kho lens: {e}")
                pass

        # _logger.info(
        # "✅ Lens stock sync done: updated=%s, skipped=%s, missing_variant=%s, missing_template=%s",
        # updated, skipped, missing_variant, missing_template
        # )

    def _prepare_base_vals(self, item, cache, product_type, coating_ids=None, lens_template_key=None):
        dto = item.get('productdto') or {}
        cid = (dto.get('cid') or '').strip()
        if not cid:
            raise ValueError("Missing CID")

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

        # Category Logic - chỉ 2 cấp: All / <loại>
        grp_dto = dto.get('groupdto') or {}
        grp_type_name = (grp_dto.get('groupTypedto') or {}).get('name', 'Khác')

        # Map product type to category code (matches RS format)
        cat_map = {
            'Mắt': ('Tròng kính', 'lens', '06'),
            'Gọng': ('Gọng kính', 'opt', '27'),
            'Khác': ('Phụ kiện', 'accessory', '20')
        }
        main_cat, _, main_code = cat_map.get(grp_type_name, ('Phụ kiện', 'accessory', '20'))

        # Get/Create Parent Category (chỉ 1 cấp dưới All)
        parent_key = (main_cat, False)
        if parent_key in cache['categories']:
            categ_id = cache['categories'][parent_key]
        else:
            parent = self.env['product.category'].search([('name', '=', main_cat)], limit=1)
            if parent:
                categ_id = parent.id
            else:
                try:
                    with self.env.cr.savepoint():
                        parent = self.env['product.category'].with_context(
                            tracking_disable=True, mail_notrack=True
                        ).create({'name': main_cat, 'code': main_code})
                    categ_id = parent.id
                except Exception:
                    parent = self.env['product.category'].search([('name', '=', main_cat)], limit=1)
                    categ_id = parent.id if parent else self.env.ref('product.product_category_all').id
            cache['categories'][parent_key] = categ_id

        # Nhóm sản phẩm (gán vào field riêng theo loại, không tạo danh mục con)
        cat_name = grp_dto.get('name', '')
        grp_id = False
        if 'product.group' in self.env:
            g_id = grp_dto.get('id')
            g_cid = (grp_dto.get('cid') or '').strip().upper()
            g_name = (grp_dto.get('name') or '').strip()

            if g_id and g_id in cache['groups_by_id']:
                grp_id = g_id
            elif g_cid and g_cid in cache['groups']:
                grp_id = cache['groups'][g_cid]
            elif g_name and g_name.upper() in cache['groups']:
                grp_id = cache['groups'][g_name.upper()]
            elif g_name:
                # Create Group
                g_type_id = False
                if 'product.group.type' in self.env:
                    gt = self.env['product.group.type'].search([('name', '=', grp_type_name)], limit=1)
                    if not gt:
                        try:
                            with self.env.cr.savepoint():
                                gt = self.env['product.group.type'].create({'name': grp_type_name})
                        except Exception:
                            gt = self.env['product.group.type'].search([('name', '=', grp_type_name)], limit=1)
                    g_type_id = gt.id if gt else False
                try:
                    with self.env.cr.savepoint():
                        ng = self.env['product.group'].create(
                            {'name': g_name, 'cid': g_cid or '', 'group_type_id': g_type_id,
                             'product_type': product_type})
                    grp_id = ng.id
                except Exception:
                    ng = self.env['product.group'].search([('name', '=', g_name)], limit=1)
                    grp_id = ng.id if ng else False
                if grp_id:
                    if g_cid: cache['groups'][g_cid] = grp_id
                    cache['groups'][g_name.upper()] = grp_id
                    cache['groups_by_id'][grp_id] = grp_id

        # Currency lookup (cần trước seller_ids để truyền currency_id đúng)
        currency_zone_cid = (dto.get('currencyZoneDTO') or {}).get('cid', '')
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
                    # _logger.info(f"✅ Found currency in cache: {currency_zone_cid.upper()} (id={currency_id})")
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
                                _cur.write({'active': True})
                                # _logger.info(f"✅ Activated inactive currency: {currency_zone_cid.upper()} (id={currency_id})")
                            except Exception as e:
                                # _logger.warning(f"⚠️ Không kích hoạt được currency {currency_zone_cid!r}: {e}")
                                pass
                    else:
                        try:
                            with self.env.cr.savepoint():
                                _cur = self.env['res.currency'].create({
                                    'name': currency_zone_cid.upper(),
                                    'symbol': currency_zone_cid.upper(),
                                    'position': 'after',
                                    'active': True,
                                    'rounding': 0.01,
                                })
                                currency_id = _cur.id
                                # _logger.info(f"✅ Auto-created currency: {currency_zone_cid.upper()} (id={currency_id})")
                        except Exception as e:
                            # _logger.warning(f"⚠️ Không tạo được currency {currency_zone_cid!r}: {e}")
                            # Recover: search lại sau khi lỗi (có thể do race condition)
                            _cur_existing = self.env['res.currency'].with_context(active_test=False).search([
                                ('name', '=', currency_zone_cid.upper())
                            ], limit=1)
                            if _cur_existing:
                                currency_id = _cur_existing.id
                                # _logger.info(f"✅ Recovered currency after error: {currency_zone_cid.upper()} (id={currency_id})")
                    # Cập nhật cache để lần sau không cần search lại
                    if currency_id:
                        cache.setdefault('acc_currency', {})[currency_zone_cid.upper()] = currency_id
                cache['misc'][_cur_key] = currency_id

        # Supplier Logic - Using seller_ids (Odoo standard)
        seller_vals = []
        s_dto = dto.get('supplierdto') or {}
        s_details = s_dto.get('supplierDetailDTOS', [])
        if s_details:
            s_det = s_details[0]
            s_cid, s_name = s_det.get('cid'), s_det.get('name')
            if s_cid and s_name:
                sup_id = False
                if s_cid.upper() in cache['suppliers']:
                    sup_id = cache['suppliers'][s_cid.upper()]
                else:
                    try:
                        with self.env.cr.savepoint():
                            sup = self.env['res.partner'].create({
                                'name': s_name, 'ref': s_cid, 'is_company': True, 'supplier_rank': 1,
                                'phone': s_det.get('phone', ''), 'email': s_det.get('mail', ''),
                                'street': s_det.get('address', '')
                            })
                        sup_id = sup.id
                    except Exception:
                        sup = self.env['res.partner'].search([('ref', '=', s_cid)], limit=1)
                        sup_id = sup.id if sup else False
                    if sup_id:
                        cache['suppliers'][s_cid.upper()] = sup_id

                # Prepare seller_ids values — truyền currency_id đúng theo sản phẩm
                # currency_id là NOT NULL trong DB → dùng company currency làm fallback nếu không tìm được
                if sup_id:
                    _seller_currency_id = currency_id or self.env.company.currency_id.id
                    seller_vals.append((0, 0, {
                        'partner_id': sup_id,
                        'price': self._to_float(dto.get('orPrice'), default=0.0),
                        'min_qty': 1.0,
                        'delay': 1,
                        'currency_id': _seller_currency_id,
                    }))

        # Tax (Purchase tax for suppliers)
        tax_pct = self._to_float(dto.get('tax'), default=0.0)
        tax_id = False
        if tax_pct > 0:
            t_name = f"Thuế mua hàng {tax_pct}%"
            if t_name in cache['taxes']:
                tax_id = cache['taxes'][t_name]
            else:
                try:
                    with self.env.cr.savepoint():
                        nt = self.env['account.tax'].create({
                            'name': t_name,
                            'amount': tax_pct,
                            'amount_type': 'percent',
                            'type_tax_use': 'purchase'
                        })
                    tax_id = nt.id
                except Exception:
                    nt = self.env['account.tax'].search([('name', '=', t_name)], limit=1)
                    tax_id = nt.id if nt else False
                if tax_id:
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
                    try:
                        with self.env.cr.savepoint():
                            ns = self.env['product.status'].create({'name': status_name})
                        status_id = ns.id
                    except Exception:
                        ns = self.env['product.status'].search([('name', '=', status_name)], limit=1)
                        status_id = ns.id if ns else False
                    if status_id:
                        cache['statuses'][status_key] = status_id

        product_kind = 'consu'

        # Basic Vals
        vals = {
            'name': dto.get('fullname') or 'Unknown',
            'default_code': default_code,
            'type': product_kind,
            'categ_id': categ_id,
            'uom_id': cache.setdefault('_uom_unit_id', self.env.ref('uom.product_uom_unit').id),
            'uom_po_id': cache['_uom_unit_id'],
            'list_price': self._to_float(dto.get('rtPrice'), default=0.0),
            'standard_price': self._to_float(dto.get('orPrice'), default=0.0) * self._to_float(
                (dto.get('currencyZoneDTO') or {}).get('value'),
                default=1.0
            ),
            'supplier_taxes_id': [(6, 0, [tax_id])] if tax_id else [(5,)],
            'seller_ids': seller_vals if seller_vals else [],
            'product_type': product_type,
            'brand_id': self._get_or_create(cache, 'brands', 'product.brand', dto.get('tmdto')),
            'country_id': self._get_or_create(cache, 'countries', 'res.country', dto.get('codto')),
            'warranty_id': self._get_or_create(cache, 'warranties', 'product.warranty', dto.get('warrantydto')),
            'lens_group_id': grp_id if product_type == 'lens' else False,
            'opt_group_id': grp_id if product_type == 'opt' else False,
            'acc_group_id': grp_id if product_type == 'accessory' else False,
            # Custom Fields (prefixed with x_)
            'x_eng_name': dto.get('engName', ''),
            'description': dto.get('note', ''),
            'x_uses': dto.get('uses', ''),
            'x_guide': dto.get('guide', ''),
            'x_warning': dto.get('warning', ''),
            'x_preserve': dto.get('preserve', ''),
            'x_cid_ncc': dto.get('cidNcc', ''),
            'x_accessory_total': int(dto.get('accessoryTotal') or 0),
            'status_product_id': status_id,
            'x_currency_zone_code': (dto.get('currencyZoneDTO') or {}).get('cid', ''),
            'x_currency_zone_value': self._to_float((dto.get('currencyZoneDTO') or {}).get('value'), default=0.0),
            'x_ws_price': self._to_float(dto.get('wsPrice') or dto.get('wsPriceMax'), default=0.0),
            'x_ws_price_min': self._to_float(dto.get('wsPriceMin'), default=0.0),
            'x_ws_price_max': self._to_float(dto.get('wsPriceMax'), default=0.0),
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
            # coating_codes chỉ cần cho lens_template_key, đã được tính trước khi gọi hàm này
            if lens_template_key is None:
                _, _codes = self._resolve_lens_coatings(item, cache)
                lens_template_key = self._build_lens_template_key(item, _codes)

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
                # _logger.debug("🔎 _goc_design called with=%s", nm or None)
                if not nm:
                    return False
                key = nm.upper()
                cid = cache.get('designs', {}).get(key)
                if cid:
                    # _logger.debug("✅ _goc_design cache hit name=%s id=%s", nm, cid)
                    pass
                    return cid
                found = self.env['product.design'].search([('name', '=', nm)], limit=1)
                if found:
                    cache.setdefault('designs', {})[key] = found.id
                    # _logger.debug("✅ _goc_design search hit name=%s id=%s", nm, found.id)
                    return found.id
                try:
                    with self.env.cr.savepoint():
                        rec = self.env['product.design'].create({'name': nm})
                    cache.setdefault('designs', {})[key] = rec.id
                    # _logger.debug("✅ _goc_design created name=%s id=%s", nm, rec.id)
                    return rec.id
                except Exception as e:
                    # _logger.warning(f"⚠️ Không tạo được product.design name={nm!r}: {e}")
                    pass
                    return False

            def _goc_material(name_raw):
                """Get or create product.lens.material by name."""
                nm = str(name_raw or '').strip()
                # _logger.debug("🔎 _goc_material called with=%s", nm or None)
                if not nm:
                    return False
                key_lower = nm.lower()
                cid = cache.get('lens_materials', {}).get(key_lower)
                if cid:
                    # _logger.debug("✅ _goc_material cache hit name=%s id=%s", nm, cid)
                    pass
                    return cid
                found = self.env['product.lens.material'].search([('name', '=', nm)], limit=1)
                if found:
                    cache.setdefault('lens_materials', {})[key_lower] = found.id
                    # _logger.debug("✅ _goc_material search hit name=%s id=%s", nm, found.id)
                    return found.id
                try:
                    with self.env.cr.savepoint():
                        rec = self.env['product.lens.material'].create({'name': nm})
                    cache.setdefault('lens_materials', {})[key_lower] = rec.id
                    # _logger.debug("✅ _goc_material created name=%s id=%s", nm, rec.id)
                    return rec.id
                except Exception as e:
                    # _logger.warning(f"⚠️ Không tạo được product.lens.material name={nm!r}: {e}")
                    pass
                    return False

            def _goc_index(dto):
                """Get or create product.lens.index from indexdto."""
                if not dto:
                    # _logger.debug("🔎 _goc_index called with empty dto")
                    pass
                    return False
                cid = (dto.get('cid') or '').strip().upper()
                name = (dto.get('name') or dto.get('value') or cid or '').strip()
                # _logger.debug("🔎 _goc_index called cid=%s name=%s", cid or None, name or None)
                if cid:
                    cached = cache.get('lens_indexes', {}).get(cid)
                    if cached:
                        # _logger.debug("✅ _goc_index cache hit by cid=%s id=%s", cid, cached)
                        pass
                        return cached
                if name:
                    cached = cache.get('lens_indexes', {}).get(name.upper())
                    if cached:
                        # _logger.debug("✅ _goc_index cache hit by name=%s id=%s", name, cached)
                        pass
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
                    # _logger.debug("✅ _goc_index search hit cid=%s name=%s id=%s", cid or None, name or None, found.id)
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
                    # _logger.debug("✅ _goc_index created cid=%s name=%s id=%s", cid or None, name, rec.id)
                    return rec.id
                except Exception as e:
                    # _logger.warning(f"⚠️ Không tạo được product.lens.index cid={cid!r} name={name!r}: {e}")
                    pass
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
                    # _logger.debug("✅ _goc_power created type=%s value=%s id=%s", power_type, formatted, rec.id)
                    return rec.id
                except Exception as e:
                    # _logger.warning("⚠️ Không tạo được product.lens.power type=%s value=%s: %s", power_type, formatted, e)
                    pass
                    return False

            # Resolve Many2one IDs (get-or-create)
            d1_id = _goc_design(design_1)
            d2_id = _goc_design(design_2)
            material_raw = first_non_empty(item.get('material'), item.get('materialdto'))
            mat_id = _goc_material(material_raw)
            idx_id = _goc_index(index_dto)

            # _logger.info(
            # "🔍 Lens mapping candidates | design1=%s | design2=%s | material=%s | index_cid=%s | index_name=%s | coating_ids=%s",
            # design_1 or None,
            # design_2 or None,
            # material_raw or None,
            # (index_dto.get('cid') or None),
            # (index_dto.get('name') or index_dto.get('value') or None),
            # coating_ids,
            # )

            lens_display_vals = {
                'lens_base_curve': safe_float(item.get('base')),
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

            # _logger.info(
            # "📝 [LENS VALS] uv=%s | coating=%s | cl_hmc=%s | cl_pho=%s | cl_tint=%s",
            # lens_display_vals.get('lens_uv_id', 'SKIPPED'),
            # lens_display_vals.get('lens_coating_ids', 'SKIPPED'),
            # lens_display_vals.get('lens_cl_hmc_id', 'SKIPPED'),
            # lens_display_vals.get('lens_cl_pho_id', 'SKIPPED'),
            # lens_display_vals.get('lens_cl_tint_id', 'SKIPPED'),
            # )

            vals.update(lens_display_vals)

        # ─── Opt specs (Hướng B: field trực tiếp trên template) ──────────────────────
        if product_type == 'opt':
            vals.update(self._prepare_opt_vals(item, cache))

        return vals, cache['products'].get(default_code)

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
            # _logger.debug(f"🔍 M2M [{log_label}]: API không trả list hoặc rỗng.")
            pass
            return [(5, 0, 0)]

        ids = []
        for dto in dtos:
            if not isinstance(dto, dict):
                continue
            cid = (dto.get('cid') or '').strip().upper()
            name = (dto.get('name') or '').strip()
            if not cid and not name:
                # _logger.debug(f"⚠️ M2M [{log_label}]: DTO không có cid/name hợp lệ: {dto}")
                pass
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
                    with self.env.cr.savepoint():
                        rec = self.env[model_name].create(vals_create)
                    rid = rec.id
                    if cid:
                        cache.setdefault(cache_key, {})[cid] = rid
                    if name:
                        cache.setdefault(cache_key, {})[name.upper()] = rid
                    # _logger.debug(f"✅ M2M [{log_label}]: Tạo mới {model_name} cid={cid!r} name={name!r}")
                except Exception as e:
                    # _logger.warning(f"⚠️ M2M [{log_label}]: Không tạo được {model_name} cid={cid!r}: {e}")
                    pass

            if rid:
                ids.append(rid)
            else:
                # _logger.debug(f"⚠️ M2M [{log_label}]: Không tìm thấy cid={cid!r} name={name!r} trong cache[{cache_key!r}]")
                pass

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
            'opt_material_temple_tip_id': self._get_or_create_master(cache, 'materials',
                                                                     item.get('materialTempleTipdto')),
            'opt_material_lens_id': self._get_or_create_master(cache, 'materials', item.get('materialLensdto')),
            # ─── Chất liệu Many2many – key thực tế từ API: materialsFrontdto / materialsTempledto
            'opt_materials_front_ids': self._resolve_opt_material_dtos(
                item,
                ['materialsFrontdto', 'materialsFrontDto',  # ✅ key thực tế
                 'materialFrontdtos', 'materialFrontDtos',  # fallback cũ
                 'materialFrontdto', 'materialFrontDto'],
                cache, log_label='materialsFront'
            ),
            'opt_materials_temple_ids': self._resolve_opt_material_dtos(
                item,
                ['materialsTempledto', 'materialsTempleDto',  # ✅ key thực tế
                 'materialTempledtos', 'materialTempleDtos',  # fallback cũ
                 'materialTempledto', 'materialTempleDto'],
                cache, log_label='materialsTemple'
            ),
            # ─── Coating Many2many – key thực tế: coatingsdto ──────────────────────────
            'opt_coating_ids': self._resolve_m2m_ids(
                item.get('coatingsdto')  # ✅ key thực tế
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
            # _logger.info("%s FULL JSON:\n%s", prefix,
            # json.dumps(item, ensure_ascii=False, indent=2, default=str))
            pass
        except Exception as e:
            # _logger.warning("%s Không dump được JSON: %s", prefix, e)
            pass

        # ── 2. Danh sách key cấp 1 ────────────────────────────────────────────
        # _logger.info("%s TOP-LEVEL KEYS (%d): %s", prefix, len(item), list(item.keys()))

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
                # _logger.info("%s KEY=%r → list (%d items):", prefix, k, len(v))
                pass
                for i, elem in enumerate(v):
                    if isinstance(elem, dict):
                        # _logger.info("  [%d] dict keys=%s", i, list(elem.keys()))
                        pass
                    else:
                        # _logger.info("  [%d] %s = %r", i, type(elem).__name__, elem)
                        pass
            elif isinstance(v, dict):
                # _logger.info("%s KEY=%r → dict keys=%s", prefix, k, list(v.keys()))
                pass
            else:
                # _logger.info("%s KEY=%r → %s = %r", prefix, k, type(v).__name__, v)
                pass

        # ── 4. Type map của toàn bộ item ──────────────────────────────────────
        type_map = []
        for k, v in item.items():
            if isinstance(v, list):
                type_map.append(f"{k}: list[{len(v)}]")
            elif isinstance(v, dict):
                type_map.append(f"{k}: dict({len(v)} keys)")
            else:
                type_map.append(f"{k}: {type(v).__name__}={v!r}")
        # _logger.info("%s TYPE MAP:\n  %s", prefix, '\n  '.join(type_map))

    def _process_lens_variant_items(self, items, cache, error_ctx=None):
        total = len(items)
        success = failed = 0
        # _logger.info(f"🔄 Processing {total} lens items (template-based)...")

        to_create_vals = []  # (template_key, vals)
        to_update = []  # (tmpl_id, vals)

        for idx, item in enumerate(items):
            try:
                self._debug_log_item_structure(item, idx)
                coating_ids, coating_codes = self._resolve_lens_coatings(item, cache)
                template_key = self._build_lens_template_key(item, coating_codes)
                tmpl_id = cache.get('lens_templates', {}).get(template_key)
                vals, _ = self._prepare_base_vals(
                    item, cache, 'lens',
                    coating_ids=coating_ids,
                    lens_template_key=template_key
                )
                if tmpl_id:
                    to_update.append((tmpl_id, vals))
                else:
                    to_create_vals.append((template_key, vals))
            except Exception as e:
                failed += 1
                dto = item.get('productdto') or {}
                cid = (dto.get('cid') or '').strip() or f'idx_{idx}'
                self._record_sync_error(error_ctx, 'lens', 'PREPARE', ref=cid, exc=e)
                # _logger.error(f"Lens prepare error idx={idx}: {e}")

        # Batch create
        batch_size = 100
        for i in range(0, len(to_create_vals), batch_size):
            batch = to_create_vals[i:i + batch_size]
            try:
                with self.env.cr.savepoint():
                    recs = self.env['product.template'].with_context(
                        tracking_disable=True
                    ).create([v for _, v in batch])
                    for (template_key, _), rec in zip(batch, recs):
                        cache.setdefault('lens_templates', {})[template_key] = rec.id
                        if rec.default_code:
                            cache['products'][rec.default_code] = rec.id
                        self._cleanup_lens_template_variants(rec)
                    success += len(recs)
            except Exception:
                # Fallback: create từng record
                for template_key, vals in batch:
                    dc = vals.get('default_code')
                    existing_id = cache['products'].get(dc)
                    if not existing_id and dc:
                        existing = self.env['product.template'].search(
                            [('default_code', '=', dc)], limit=1
                        )
                        if existing:
                            existing_id = existing.id
                            cache['products'][dc] = existing_id
                    try:
                        with self.env.cr.savepoint():
                            if existing_id:
                                tmpl = self.env['product.template'].browse(existing_id)
                                tmpl.write(vals)
                            else:
                                tmpl = self.env['product.template'].with_context(
                                    tracking_disable=True
                                ).create(vals)
                                cache.setdefault('lens_templates', {})[template_key] = tmpl.id
                                if tmpl.default_code:
                                    cache['products'][tmpl.default_code] = tmpl.id
                            self._cleanup_lens_template_variants(tmpl)
                            success += 1
                    except Exception as e2:
                        failed += 1
                        self._record_sync_error(error_ctx, 'lens', 'SINGLE_CREATE', ref=dc or 'N/A', exc=e2)
                        # _logger.error(f"Lens single create error default_code={dc}: {e2}")

        # Update từng record (vals thường khác nhau)
        for tmpl_id, vals in to_update:
            try:
                with self.env.cr.savepoint():
                    tmpl = self.env['product.template'].browse(tmpl_id)
                    tmpl.write(vals)
                    self._cleanup_lens_template_variants(tmpl)
                success += 1
            except Exception as e:
                failed += 1
                self._record_sync_error(error_ctx, 'lens', 'UPDATE', ref=f"tmpl_id={tmpl_id}", exc=e)
                # _logger.error(f"Lens update error tmpl_id={tmpl_id}: {e}")

        return success, failed

    def _process_accessory_batch(self, items, cache, error_ctx=None):
        """Xử lý accessories: mỗi record một savepoint độc lập + logging đầy đủ.
        HOÀN TOÀN TÁCH BIỆT khỏi lens/opt. Không sửa bất kỳ helper nào lens/opt dùng.
        """
        import json as _json_acc
        import traceback as _tb_acc

        self._load_env()
        log_raw = os.getenv('LOG_ACCESSORY_RAW_STRUCTURE', 'False').lower() == 'true'
        log_debug = os.getenv('LOG_ACCESSORY_DEBUG', 'False').lower() == 'true'
        raw_limit = int(os.getenv('LOG_RAW_SAMPLE_LIMIT', '3'))

        total = len(items)
        success = 0
        skipped = 0
        errors = 0
        raw_logged = 0
        err_by_step = {'currency': 0, 'map': 0, 'create': 0, 'write': 0, 'other': 0}

        # _logger.info(
        # "[ACC_SYNC] Starting batch: total=%d "
        # "log_raw=%s log_debug=%s raw_limit=%d",
        # total, log_raw, log_debug, raw_limit
        # )
        # [ACC_SYNC][FETCH] — dữ liệu đã được fetch trước, log tổng ở đây
        # _logger.info(
        # "[ACC_SYNC][FETCH] status=pre-fetched duration_ms=N/A items=%d", total
        # )

        for idx, item in enumerate(items):
            dto = item.get('productdto') or {}
            cid = (dto.get('cid') or '').strip()
            sku = cid or f'idx_{idx}'
            ext_id = (dto.get('id') or dto.get('externalId') or cid or f'idx_{idx}')
            name = dto.get('fullname') or dto.get('name') or 'Unknown'

            # _logger.info(
            # "[ACC_SYNC][START] idx=%d ext_id=%s sku=%s name=%s",
            # idx, ext_id, sku, name
            # )

            step = 'init'
            try:
                with self.env.cr.savepoint():

                    # ── RAW_KEYS ────────────────────────────────────────────────
                    if log_debug:
                        # _logger.info(
                        # "[ACC_SYNC][RAW_KEYS] idx=%d keys=%s",
                        # idx, list(item.keys())
                        # )
                        pass

                    # ── RAW_JSON sample (giới hạn raw_limit record + truncate 2KB) ──
                    if log_raw and raw_logged < raw_limit:
                        try:
                            raw_str = _json_acc.dumps(
                                item, ensure_ascii=False, default=str
                            )
                            if len(raw_str) > 2048:
                                raw_str = raw_str[:2048] + '...(truncated)'
                            # _logger.info(
                            # "[ACC_SYNC][RAW_JSON] idx=%d:\n%s", idx, raw_str
                            # )
                            raw_logged += 1
                        except Exception as _je:
                            # _logger.warning(
                            # "[ACC_SYNC] json dump error idx=%d: %s", idx, _je
                            # )
                            pass

                    # ── MAP_IN ──────────────────────────────────────────────────
                    cz_dto = dto.get('currencyZoneDTO') or {}
                    # _logger.info(
                    # "[ACC_SYNC][MAP_IN] sku=%s important_fields={"
                    # "currency=%s, brand=%s, country=%s, warranty=%s, "
                    # "uom=unit, category=%s, price=%s, cost=%s, barcode=%s}",
                    # sku,
                    # cz_dto.get('cid') or 'N/A',
                    # (dto.get('tmdto')      or {}).get('cid') or 'N/A',
                    # (dto.get('codto')      or {}).get('cid') or 'N/A',
                    # (dto.get('warrantydto') or {}).get('cid') or 'N/A',
                    # (dto.get('groupdto')   or {}).get('name') or 'N/A',
                    # dto.get('rtPrice', 0),
                    # dto.get('orPrice', 0),
                    # dto.get('barcode') or 'N/A',
                    # )

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
                        'res.country',
                        name_field='name', code_field='code',
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
                    raw_design = _pick('designdto', 'designDto', 'design')
                    raw_shape = _pick('shapedto', 'shapeDto', 'shape')
                    raw_material = _pick('materialdto', 'materialDto', 'material')
                    raw_color = _pick('colordto', 'colorDto', 'color',
                                      'acc_color', 'accColor')
                    raw_width = _pick('width', 'accWidth', 'acc_width', 'chieu_rong')
                    raw_length = _pick('length', 'accLength', 'acc_length', 'chieu_dai')
                    raw_height = _pick('height', 'accHeight', 'acc_height', 'chieu_cao')
                    raw_head = _pick('head', 'accHead', 'acc_head', 'dau')
                    raw_body = _pick('body', 'accBody', 'acc_body', 'than')

                    if _fdbg:
                        # _logger.info(
                        # "[ACC_FIELD][RAW] sku=%s design=%r shape=%r "
                        # "material=%r color=%r "
                        # "width=%r length=%r height=%r head=%r body=%r",
                        # sku,
                        # raw_design, raw_shape, raw_material, raw_color,
                        # raw_width, raw_length, raw_height, raw_head, raw_body,
                        # )
                        pass

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
                        'design_id': acc_design_id or False,
                        'shape_id': acc_shape_id or False,
                        'material_id': acc_material_id or False,
                        'color_id': acc_color_id or False,
                        'acc_width': _sf(raw_width),
                        'acc_length': _sf(raw_length),
                        'acc_height': _sf(raw_height),
                        'acc_head': _sf(raw_head),
                        'acc_body': _sf(raw_body),
                    }
                    vals.update(acc_field_vals)

                    if _fdbg:
                        # _logger.info(
                        # "[ACC_FIELD][MAPPED] sku=%s "
                        # "design_id=%s shape_id=%s material_id=%s color_id=%s "
                        # "acc_width=%s acc_length=%s acc_height=%s "
                        # "acc_head=%s acc_body=%s",
                        # sku,
                        # acc_design_id, acc_shape_id, acc_material_id, acc_color_id,
                        # _sf(raw_width), _sf(raw_length), _sf(raw_height),
                        # _sf(raw_head), _sf(raw_body),
                        # )
                        pass

                    # ── MAP_OUT ─────────────────────────────────────────────────
                    # _logger.info(
                    # "[ACC_SYNC][MAP_OUT] sku=%s mapped_vals={"
                    # "default_code=%s, name=%s, type=%s, "
                    # "categ_id=%s, brand_id=%s, country_id=%s, warranty_id=%s, "
                    # "list_price=%s, standard_price=%s}",
                    # sku,
                    # vals.get('default_code'),
                    # vals.get('name'),
                    # vals.get('type'),
                    # vals.get('categ_id'),
                    # vals.get('brand_id'),
                    # vals.get('country_id'),
                    # vals.get('warranty_id'),
                    # vals.get('list_price'),
                    # vals.get('standard_price'),
                    # )

                    categ_id = vals.get('categ_id')
                    if categ_id:
                        categ = self.env['product.category'].browse(categ_id)
                        if not categ.exists():
                            fallback = self.env.ref('product.product_category_all')
                            # _logger.warning(
                            # "[ACC_SYNC][WARN] sku=%s categ_id=%s không tồn tại → dùng fallback %s",
                            # sku, categ_id, fallback.id
                            # )
                            vals['categ_id'] = fallback.id

                    # ── create / write ──────────────────────────────────────────
                    if pid:
                        step = 'write'
                        saved_rec = self.env['product.template'].browse(pid).with_context(
                            tracking_disable=True
                        )
                        saved_rec.write(vals)
                        if log_debug:
                            # _logger.info(
                            # "[ACC_SYNC][WRITE_OK] sku=%s tmpl_id=%s", sku, pid
                            # )
                            pass
                    else:
                        step = 'create'
                        saved_rec = self.env['product.template'].with_context(
                            tracking_disable=True
                        ).create(vals)
                        cache['products'][saved_rec.default_code] = saved_rec.id
                        if log_debug:
                            # _logger.info(
                            # "[ACC_SYNC][CREATE_OK] sku=%s new_tmpl_id=%s",
                            # sku, saved_rec.id
                            # )
                            pass

                    # ── Readback log (chỉ khi LOG_ACCESSORY_FIELD_DEBUG=True) ──
                    if _fdbg:
                        try:
                            rb = saved_rec
                            # _logger.info(
                            # "[ACC_FIELD][ODB_READBACK] sku=%s tmpl_id=%s "
                            # "design_id=%s(%s) shape_id=%s(%s) "
                            # "material_id=%s(%s) color_id=%s(%s) "
                            # "acc_width=%s acc_length=%s acc_height=%s "
                            # "acc_head=%s acc_body=%s",
                            # sku, rb.id,
                            # rb.design_id.id if rb.design_id else None,
                            # rb.design_id.name if rb.design_id else None,
                            # rb.shape_id.id if rb.shape_id else None,
                            # rb.shape_id.name if rb.shape_id else None,
                            # rb.material_id.id if rb.material_id else None,
                            # rb.material_id.name if rb.material_id else None,
                            # rb.color_id.id if rb.color_id else None,
                            # rb.color_id.name if rb.color_id else None,
                            # rb.acc_width, rb.acc_length, rb.acc_height,
                            # rb.acc_head, rb.acc_body,
                            # )
                        except Exception as _rb_err:
                            # _logger.warning("[ACC_FIELD][READBACK_ERR] sku=%s err=%s", sku, _rb_err)
                            pass

                    success += 1

            except Exception as exc:
                errors += 1
                skipped += 1
                self._record_sync_error(error_ctx, 'accessory', 'ITEM_ERR', ref=sku, exc=exc)

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
                        # _logger.info(
                        # "[ACC_SYNC][RAW_JSON] ERROR_SAMPLE idx=%d:\n%s",
                        # idx, raw_str
                        # )
                        raw_logged += 1
                    except Exception:
                        pass

                # _logger.exception(
                # "[ACC_SYNC][ERROR] sku=%s step=%s err=%s", sku, step, exc
                # )
                # _logger.warning("[ACC_SYNC][SKIP] sku=%s", sku)

        # ── Tổng kết ────────────────────────────────────────────────────────────
        # _logger.info(
        # "[ACC_SYNC][SUMMARY] total=%d success=%d skipped=%d errors=%d",
        # total, success, skipped, errors
        # )
        # _logger.info(
        # "[ACC_SYNC][ERROR_BY_STEP] currency=%d map=%d create=%d write=%d other=%d",
        # err_by_step.get('currency', 0),
        # err_by_step.get('map',      0),
        # err_by_step.get('create',   0),
        # err_by_step.get('write',    0),
        # err_by_step.get('other',    0),
        # )

        return success, errors

    def _process_batch(self, items, cache, product_type, child_model=None, error_ctx=None):
        """
        Xử lý batch create/update sản phẩm từ API.
        - Lens và Opt: specs đã được map trực tiếp vào template (Hướng B).
        - Accessory và các loại khác: chỉ tạo/update product.template.
        """
        if product_type == 'lens':
            return self._process_lens_variant_items(items, cache, error_ctx=error_ctx)

        # Accessory: xử lý per-record với savepoint riêng + logging đầy đủ
        # KHÔNG thay đổi gì ở đây liên quan lens/opt
        if product_type == 'accessory':
            return self._process_accessory_batch(items, cache, error_ctx=error_ctx)

        total = len(items)
        success = failed = 0
        to_create, to_update = [], []

        has_child = False  # Hướng B: không còn dùng child model cho lens hay opt
        child_vals_map = {}  # tmpl_id → child_vals (cho opt)
        new_child_data = []  # [(idx, child_vals)] cho opt create

        # _logger.info(f"🔄 Processing {total} {product_type} items...")

        # DEBUG: Log cấu trúc item đầu tiên để xác nhận field names từ API
        if items:
            first_item = items[0]
            # _logger.debug(f"🔍 DEBUG [{product_type}] item keys at root: {list(first_item.keys())}")
            dto0 = first_item.get('productdto') or {}
            # _logger.debug(f"🔍 DEBUG [{product_type}] productdto keys: {list(dto0.keys())}")

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
                        # _logger.info(f"🔸 Accessory idx={idx} currency_code={_cur_code} currency_id={_cur_id} default_code={vals.get('default_code')}")
                    if has_child and product_type == 'opt':
                        c_vals = self._prepare_opt_vals(item, cache)
                    if pid:
                        to_update.append((pid, vals))
                        if has_child:
                            child_vals_map[pid] = c_vals
                    else:
                        to_create.append(vals)
                        if has_child:
                            new_child_data.append((idx, c_vals))
            except Exception as e:
                failed += 1
                import traceback
                dto = item.get('productdto') or {}
                _dc = (dto.get('cid') or '').strip() or 'N/A'
                self._record_sync_error(error_ctx, product_type, 'PREPARE', ref=_dc, exc=e)
                # _logger.error(
                # f"Prepare error [{product_type}] idx={idx} default_code={_dc}: {e}\n{traceback.format_exc()}"
                # )

        # ─── Bước 2: Batch Create ─────────────────────────────────────────
        if to_create:
            batch_size = 100
            for i in range(0, len(to_create), batch_size):
                b_vals = to_create[i:i + batch_size]
                b_child = new_child_data[i:i + batch_size] if has_child else []
                b_child_refs = b_child
                try:
                    with self.env.cr.savepoint():
                        recs = self.env['product.template'].with_context(
                            tracking_disable=True
                        ).create(b_vals)

                        for j, rec in enumerate(recs):
                            cache['products'][rec.default_code] = rec.id
                        success += len(recs)
                except Exception:
                    # Batch failed — fallback: create từng record để chỉ skip cái bị trùng
                    for single_vals in b_vals:
                        dc = single_vals.get('default_code')
                        # Nếu default_code đã tồn tại trong DB → update thay vì create
                        existing_id = cache['products'].get(dc)
                        if not existing_id and dc:
                            existing = self.env['product.template'].search(
                                [('default_code', '=', dc)], limit=1
                            )
                            if existing:
                                existing_id = existing.id
                                cache['products'][dc] = existing_id
                        try:
                            with self.env.cr.savepoint():
                                if existing_id:
                                    self.env['product.template'].browse(existing_id).with_context(
                                        tracking_disable=True
                                    ).write(single_vals)
                                    success += 1
                                else:
                                    rec = self.env['product.template'].with_context(
                                        tracking_disable=True
                                    ).create(single_vals)
                                    if rec.default_code:
                                        cache['products'][rec.default_code] = rec.id
                                    success += 1
                        except Exception as e2:
                            failed += 1
                            self._record_sync_error(
                                error_ctx, product_type, 'SINGLE_CREATE',
                                ref=dc or 'N/A', exc=e2
                            )
                            # _logger.error(f"Single Create Error [{product_type}] default_code={dc}: {e2}")

                # Tạo child records riêng lẻ (savepoint độc lập)
                if has_child and b_child_refs:
                    for j, rec in enumerate(recs):
                        if j >= len(b_child_refs):
                            break
                        _, cv = b_child_refs[j]
                        if not cv:
                            # _logger.warning(f"⚠️ Bỏ qua child record rỗng cho product {rec.id}")
                            pass
                            continue
                        cv['product_tmpl_id'] = rec.id
                        try:
                            with self.env.cr.savepoint():
                                self.env[child_model].create(cv)
                        except Exception as e:
                            self._record_sync_error(error_ctx, product_type, 'CHILD_CREATE', ref=rec.id, exc=e)
                            # _logger.error(f"Child Create Error product {rec.id}: {e}")

        # ─── Bước 3: Batch Update ─────────────────────────────────────────
        # Group updates by identical vals để dùng write() trên nhiều record cùng lúc
        # Với opt/accessory vals thường khác nhau nên fallback per-record
        update_batch_size = 50
        update_list = list(to_update)
        for i in range(0, len(update_list), update_batch_size):
            batch = update_list[i:i + update_batch_size]
            for pid, vals in batch:
                try:
                    with self.env.cr.savepoint():
                        self.env['product.template'].browse(pid).with_context(
                            tracking_disable=True
                        ).write(vals)

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
                except Exception as e:
                    failed += 1
                    self._record_sync_error(error_ctx, product_type, 'UPDATE', ref=f"tmpl_id={pid}", exc=e)
                    # _logger.error(f"Update Error [{product_type}] tmpl_id={pid}: {e}")

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
        rec_id = self.id
        db = self.env.cr.dbname

        # Đánh dấu in_progress trên cursor gốc rồi commit ngay
        self.write(
            {'sync_status': 'in_progress', 'sync_log': 'Đang đồng bộ...', 'last_sync_date': fields.Datetime.now()})
        self.env.cr.commit()

        # Toàn bộ sync chạy trên cursor riêng biệt → tránh bị websocket/bus kill
        try:
            from odoo import registry as Registry
            with Registry(db).cursor() as cr:
                env = self.env(cr=cr)
                rec = env[self._name].browse(rec_id)
                msg, full_log, stats = rec._do_sync(limit)
                rec.write({
                    'sync_status': 'success', 'sync_log': full_log,
                    'total_synced': stats['lens'] + stats['opt'] + stats['acc'],
                    'total_failed': stats['failed'],
                    'lens_count': stats['lens'], 'opts_count': stats['opt'], 'other_count': stats['acc'],
                })
                # cr.commit() tự động khi thoát with block thành công
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Đồng bộ hoàn tất', 'message': msg, 'type': 'success'}}
        except Exception as e:
            try:
                with Registry(db).cursor() as cr:
                    self.env(cr=cr)[self._name].browse(rec_id).write(
                        {'sync_status': 'error', 'sync_log': str(e)[:2000]}
                    )
            except Exception:
                pass
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Đồng bộ thất bại', 'message': str(e)[:500], 'type': 'danger'}}

    def _do_sync(self, limit=None):
        """Logic sync thực sự — chạy trên cursor riêng được truyền vào qua self.env."""
        token = self._get_access_token()
        cache = self._preload_all_data()
        cfg = self._get_api_config()
        stats = {}
        error_ctx = self._init_sync_error_ctx()

        # Lens
        s, f = self._sync_streaming(cfg['lens_endpoint'], token, 'lens', cache=cache, error_ctx=error_ctx, limit=limit)
        stats['lens'] = s
        stats['failed'] = f

        try:
            self._sync_lens_stock(token, cfg, cache)
        except Exception:
            pass

        # Opt
        s, f = self._sync_streaming(cfg['opts_endpoint'], token, 'opt', cache=cache, error_ctx=error_ctx, limit=limit)
        stats['opt'] = s
        stats['failed'] += f

        # Accessory
        s, f = self._sync_streaming(cfg['types_endpoint'], token, 'accessory', cache=cache, error_ctx=error_ctx, limit=limit)
        stats['acc'] = s
        stats['failed'] += f

        total = stats['lens'] + stats['opt'] + stats['acc']
        msg = f"Đã đồng bộ {total} (Mắt:{stats['lens']}, Gọng:{stats['opt']}, Khác:{stats['acc']}). Lỗi: {stats['failed']}"

        full_log = msg
        if error_ctx.get('counts'):
            counts_sorted = sorted(error_ctx['counts'].items(), key=lambda kv: (-kv[1], kv[0]))
            counts_str = ", ".join([f"{k}={v}" for k, v in counts_sorted[:20]])
            samples = "\n".join(error_ctx.get('samples') or [])
            full_log = (
                    f"{msg}\n\nTóm tắt lỗi: {counts_str}"
                    + (f"\nVí dụ lỗi (tối đa {error_ctx.get('sample_limit', 0)}):\n{samples}" if samples else "")
            )

        max_chars = error_ctx.get('max_chars', 20000)
        if len(full_log) > max_chars:
            full_log = full_log[:max_chars] + "\n...(truncated)"

        return msg, full_log, stats

    def test_api_connection(self):
        try:
            token = self._get_access_token()
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Kết nối thành công', 'message': 'Đã lấy được token.', 'type': 'success'}}
        except Exception as e:
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Kết nối thất bại', 'message': str(e), 'type': 'danger'}}
