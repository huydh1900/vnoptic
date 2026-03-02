# -*- coding: utf-8 -*-
import logging
import json
import os
import time
import random
import re
import requests
import urllib3
from collections import defaultdict
from odoo import models, fields, api, _
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
            ('brands', 'product.brand', 'name'), # Fallback to name
            ('countries', 'product.country', 'code'),
            ('warranties', 'product.warranty', 'code'),
            ('groups', 'product.group', 'cid'),
            ('groups', 'product.group', 'name'),
            ('designs', 'product.design', 'name'),
            ('materials', 'product.material', 'name'),
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
            rec = self.env['product.uv'].create(create_vals)
            if cid:
                cache.setdefault('uvs', {})[cid] = rec.id
            cache.setdefault('uvs', {})[name.upper()] = rec.id
            _logger.info("✅ Auto-created product.uv cid=%s name=%s id=%s", cid or None, name, rec.id)
            return rec.id
        except Exception as e:
            _logger.warning("⚠️ Không tạo được product.uv cid=%s name=%s: %s", cid or None, name, e)
            return False

    def _resolve_lens_coatings(self, item, cache):
        coating_ids = []
        coating_codes = []
        raw_coatings = (
            item.get('coatingdtos')
            or item.get('coatingDtos')
            or item.get('coatingDTOs')
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
            tmpl.write(vals)
            self._cleanup_lens_template_variants(tmpl)
            _logger.info(
                "🔍 Lens [UPDATE] %s | material=%s | index=%s | coatings=%s | design1=%s",
                tmpl.name,
                tmpl.lens_material_id.name if tmpl.lens_material_id else None,
                tmpl.lens_index_id.name if tmpl.lens_index_id else None,
                ', '.join(tmpl.lens_coating_ids.mapped('name')) or None,
                tmpl.lens_design1_id.name if tmpl.lens_design1_id else None,
            )
            return tmpl

        tmpl = self.env['product.template'].with_context(tracking_disable=True).create(vals)
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
                    sup = self.env['res.partner'].create({
                        'name': s_name, 'ref': s_cid, 'is_company': True, 'supplier_rank': 1,
                        'phone': s_det.get('phone', ''), 'email': s_det.get('mail', ''), 'street': s_det.get('address', '')
                    })
                    sup_id = sup.id
                    cache['suppliers'][s_cid.upper()] = sup_id
                
                # Prepare seller_ids values (will be added to product)
                if sup_id:
                    seller_vals.append((0, 0, {
                        'partner_id': sup_id,
                        'price': float(dto.get('orPrice') or 0),  # Supplier price
                        'min_qty': 1.0,
                        'delay': 1,
                    }))

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

        # Currency lookup for don_vi_nguyen_te
        currency_zone_cid = (dto.get('currencyZoneDTO') or {}).get('cid', '')
        don_vi_nguyen_te_id = False
        if currency_zone_cid:
            currency = self.env['res.currency'].search(
                [('name', '=', currency_zone_cid.upper())], limit=1
            )
            don_vi_nguyen_te_id = currency.id if currency else False

        is_storable = product_type in ['opt', 'lens']
        product_kind = 'consu'

        # Basic Vals
        vals = {
            'name': dto.get('fullname') or 'Unknown',
            'default_code': default_code,
            'type': product_kind,
            'is_storable': is_storable,  # Gọng/Lens = storable
            'categ_id': categ_id,
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'uom_po_id': self.env.ref('uom.product_uom_unit').id,
            'list_price': float(dto.get('rtPrice') or 0),
            'standard_price': float(dto.get('orPrice') or 0) * float((dto.get('currencyZoneDTO') or {}).get('value') or 1),  # Giá vốn: orPrice * tỷ giá (= x_or_price)
            'supplier_taxes_id': [(6, 0, [tax_id])] if tax_id else False,
            'seller_ids': seller_vals if seller_vals else False,
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
            'x_ws_price': float(dto.get('wsPrice') or 0),
            'x_ws_price_min': float(dto.get('wsPriceMin') or 0),
            'x_ws_price_max': float(dto.get('wsPriceMax') or 0),
            # x_or_price = giá nhập kho quy VND: orPrice (ngoại tệ) * tỷ giá
            'x_or_price': float(dto.get('orPrice') or 0) * float((dto.get('currencyZoneDTO') or {}).get('value') or 1),
            'don_vi_nguyen_te': don_vi_nguyen_te_id,
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
                # HMC / Photochromic / Tinted (char — chỉ set khi RS có dữ liệu, tránh ghi NULL)
                'x_hmc': extract_label(hmc_val) or None,
                'x_photochromic': extract_label(pho_val) or None,
                'x_tinted': extract_label(tint_val) or None,
                'x_mir_coating': extract_label(item.get('mirCoating')) or None,
                'x_diameter': safe_int(item.get('diameter')),
            }

            # Lọc các giá trị không hợp lệ ra khỏi vals
            # Quy tắc: None, False, '' → không ghi vào DB (giữ nguyên giá trị cũ)
            for key, value in list(lens_display_vals.items()):
                if value is None or value is False or value == '':
                    lens_display_vals.pop(key)

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
            'opt_frame_id': self._get_id(cache, 'frames', self._get_val(item, 'framedto')),
            'opt_frame_type_id': self._get_id(cache, 'frame_types', self._get_val(item, 'frameTypedto')),
            'opt_shape_id': self._get_id(cache, 'shapes', self._get_val(item, 'shapedto')),
            'opt_ve_id': self._get_id(cache, 'ves', self._get_val(item, 'vedto')),
            'opt_temple_id': self._get_id(cache, 'temples', self._get_val(item, 'templedto')),
            'opt_material_ve_id': self._get_id(cache, 'materials', self._get_val(item, 'materialVedto')),
            'opt_material_temple_tip_id': self._get_id(cache, 'materials', self._get_val(item, 'materialTempleTipdto')),
            'opt_material_lens_id': self._get_id(cache, 'materials', self._get_val(item, 'materialLensdto')),
            # ─── Mỹ thuật màu sắc (cơ bản) ────────────────────────────────────────────
            'opt_color_front_id': self._get_id_with_fallback(cache, 'colors', item.get('colorFrontdto')),
            'opt_color_temple_id': self._get_id_with_fallback(cache, 'colors', item.get('colorTempledto')),
            # ─── Chất liệu Many2many ─────────────────────────────────────────────────────
            'opt_materials_front_ids': self._resolve_m2m_ids(
                item.get('materialFrontdtos'), 'materials', cache,
                model_name='product.material', log_label='materialFrontdtos'
            ),
            'opt_materials_temple_ids': self._resolve_m2m_ids(
                item.get('materialTempledtos'), 'materials', cache,
                model_name='product.material', log_label='materialTempledtos'
            ),
            # ─── Coating Many2many ──────────────────────────────────────────────────────
            'opt_coating_ids': self._resolve_m2m_ids(
                item.get('coatingdtos'), 'coatings', cache,
                # Không tự create coating – là master data phải có sẵn
                model_name=None, log_label='coatingdtos'
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

    def _process_lens_variant_items(self, items, cache):
        total = len(items)
        success = failed = 0

        _logger.info(f"🔄 Processing {total} lens items (template-based)...")

        for idx, item in enumerate(items):
            try:
                tmpl = self._get_or_create_lens_template(item, cache)
                if not tmpl:
                    failed += 1
                    continue
                success += 1
            except Exception as e:
                failed += 1
                import traceback
                _logger.error(
                    f"Lens variant error idx={idx}: {e}\n{traceback.format_exc()}"
                )

        return success, failed

    def _process_batch(self, items, cache, product_type, child_model=None):
        """
        Xử lý batch create/update sản phẩm từ API.
        - Lens và Opt: specs đã được map trực tiếp vào template (Hướng B).
        - Accessory và các loại khác: chỉ tạo/update product.template.
        """
        if product_type == 'lens':
            return self._process_lens_variant_items(items, cache)

        total = len(items)
        success = failed = 0
        to_create, to_update = [], []

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

        # ─── Bước 1: Chuẩn bị dữ liệu ────────────────────────────────────
        for idx, item in enumerate(items):
            try:
                vals, pid = self._prepare_base_vals(item, cache, product_type)
                c_vals = {}
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
                _logger.error(f"Prepare error [{product_type}] idx={idx}: {e}\n{traceback.format_exc()}")

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
                except Exception as e:
                    failed += len(b_vals)
                    import traceback
                    _logger.error(f"Batch Create Error [{product_type}]: {e}\n{traceback.format_exc()}")
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
        for pid, vals in to_update:
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
                _logger.error(f"Update Error [{product_type}] tmpl_id={pid}: {e}")

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
        try:
            self.write({'sync_status': 'in_progress', 'sync_log': 'Đang đồng bộ...', 'last_sync_date': fields.Datetime.now()})
            self.env.cr.commit()
            
            token = self._get_access_token()
            cache = self._preload_all_data()
            cfg = self._get_api_config()
            stats = {}
            
            # Lens – specs đã map trực tiếp vào template (Hướng B)
            # Mỗi bản ghi lens từ API → 1 product.template (default variant duy nhất)
            items = self._fetch_all_items(cfg['lens_endpoint'], token, 'Lens', limit)
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
            s, f = self._process_batch(items, cache, 'opt')  # Không dùng child_model
            stats['opt'] = s
            stats['failed'] += f
            self.env.cr.commit()

            # Access
            items = self._fetch_all_items(cfg['types_endpoint'], token, 'Types', limit)
            s, f = self._process_batch(items, cache, 'accessory')
            stats['acc'] = s
            stats['failed'] += f
            self.env.cr.commit()
            
            total = stats['lens'] + stats['opt'] + stats['acc']
            msg = f"Đã đồng bộ {total} (Mắt:{stats['lens']}, Gọng:{stats['opt']}, Khác:{stats['acc']}). Lỗi: {stats['failed']}"
            self.write({'sync_status': 'success' if stats['failed'] == 0 else 'success', 'sync_log': msg, 
                       'total_synced': total, 'total_failed': stats['failed'], 
                       'lens_count': stats['lens'], 'opts_count': stats['opt'], 'other_count': stats['acc']})
            
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Đồng bộ hoàn tất', 'message': msg, 'type': 'success'}}

        except Exception as e:
            self.env.cr.rollback()
            self.write({'sync_status': 'error', 'sync_log': str(e)})
            self.env.cr.commit()
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Đồng bộ thất bại', 'message': str(e), 'type': 'danger'}}

    def test_api_connection(self):
        try:
            token = self._get_access_token()
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Kết nối thành công', 'message': 'Đã lấy được token.', 'type': 'success'}}
        except Exception as e:
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Kết nối thất bại', 'message': str(e), 'type': 'danger'}}
