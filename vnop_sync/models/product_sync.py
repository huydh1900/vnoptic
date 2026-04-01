# -*- coding: utf-8 -*-
import logging
import json
from psycopg2 import errors
import time
import os
import time
import random
import re
import base64
from io import BytesIO
import requests
import urllib3
from urllib.parse import urljoin
from collections import defaultdict
from odoo import models, fields, api, _
from odoo.modules.registry import Registry
from odoo.exceptions import UserError

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
            sample_limit = int(os.getenv('SYNC_ERROR_SAMPLE_LIMIT', '500'))
        except (TypeError, ValueError):
            sample_limit = 500

        try:
            max_chars = int(os.getenv('SYNC_ERROR_LOG_MAX_CHARS', '200000'))
        except (TypeError, ValueError):
            max_chars = 200000

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
        msg = (msg or 'Unknown error')[:1000]
        ref_str = (str(ref) if ref is not None else 'N/A')
        error_ctx['samples'].append(f"[{key}] ref={ref_str}\n  {msg}")

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

    def _is_placeholder_value(self, value):
        """Return True when value is empty/demo placeholder like 'khong', 'none', 'n/a'."""
        if value in (None, False):
            return True

        raw = str(value).strip()
        if not raw:
            return True

        normalized = re.sub(r"[\s\-_/\.]+", "", raw.lower())
        return normalized in {'khong', 'none', 'null', 'na', '""', "''"}

    def _clean_placeholder_text(self, value):
        """Normalize to stripped text and drop placeholders as False."""
        if value in (None, False):
            return False
        text = str(value).strip()
        if not text:
            return False
        return False if self._is_placeholder_value(text) else text

    def _get_accessory_category_id(self, cache=None):
        if cache and cache.get('misc', {}).get('_accessory_categ_id'):
            return cache['misc']['_accessory_categ_id']

        categ = self.env['product.category'].search([('code', '=', 'PK')], limit=1)
        if not categ:
            categ = self.env.ref('vnop_sync.product_category_accessory', raise_if_not_found=False)
        if not categ:
            categ = self.env.ref('product.product_category_all', raise_if_not_found=False)

        categ_id = categ.id if categ else False
        if cache is not None and categ_id:
            cache.setdefault('misc', {})['_accessory_categ_id'] = categ_id
        return categ_id

    def _extract_rs_image_url(self, item):
        """Extract RS product image URL/path from known payload aliases."""
        dto = (
            item.get('productdto')
            or item.get('productDto')
            or item.get('productDTO')
            or {}
        )

        image_url = False
        for source in (dto, item):
            if not isinstance(source, dict):
                continue
            for key in ('imageUrl', 'imageURL', 'image', 'Image'):
                value = source.get(key)
                if value not in (None, '', False):
                    image_url = value
                    break
            if image_url:
                break

        cleaned = self._clean_placeholder_text(image_url)
        return str(cleaned).strip() if cleaned else False

    def _is_rs_default_image_url(self, image_url):
        """Return True when RS image path points to known default placeholder image."""
        if not image_url:
            return True

        value = str(image_url).strip()
        if not value:
            return True

        normalized = value.replace('\\', '/').lower()
        default_endpoint = (os.getenv('RS_DEFAULT_IMAGE_ENDPOINT') or '/api/files/default.png').strip().lower()
        default_endpoint = default_endpoint.replace('\\', '/')
        if default_endpoint and normalized.endswith(default_endpoint):
            return True

        return normalized.endswith('/default.png') or normalized.endswith('/default.jpg') or '/default-image' in normalized

    def _build_rs_image_full_url(self, image_url, cfg):
        """Normalize RS image URL to absolute URL using configured base_url when needed."""
        if not image_url:
            return False
        raw = str(image_url).strip()
        if not raw:
            return False

        if raw.lower().startswith('http://') or raw.lower().startswith('https://'):
            return raw

        base_url = (cfg or {}).get('base_url') or ''
        if not base_url:
            return False
        return urljoin(base_url.rstrip('/') + '/', raw.lstrip('/'))

    def _get_image_sync_mode(self, limit=None):
        """Image sync mode: off | missing | changed | always."""
        default_mode = (os.getenv('PRODUCT_IMAGE_SYNC_MODE') or 'missing').strip().lower()
        limited_mode = (os.getenv('PRODUCT_IMAGE_SYNC_MODE_LIMITED') or '').strip().lower()
        mode = limited_mode if (limit and limited_mode) else default_mode
        if mode not in {'off', 'missing', 'changed', 'always'}:
            mode = 'missing'
        return mode

    def _optimize_image_bytes(self, content, content_type='', product_ref=''):
        """Resize/compress image payload before storing into image_1920."""
        if not content:
            return content

        compress = (os.getenv('PRODUCT_IMAGE_COMPRESS', 'true').strip().lower() == 'true')
        if not compress:
            return content

        try:
            max_dim = int(os.getenv('PRODUCT_IMAGE_MAX_DIM', '1280'))
        except (TypeError, ValueError):
            max_dim = 1280
        max_dim = max(256, max_dim)

        try:
            jpeg_quality = int(os.getenv('PRODUCT_IMAGE_JPEG_QUALITY', '82'))
        except (TypeError, ValueError):
            jpeg_quality = 82
        jpeg_quality = min(95, max(50, jpeg_quality))

        try:
            from PIL import Image
        except Exception:
            return content

        try:
            with Image.open(BytesIO(content)) as img:
                img.load()
                width, height = img.size
                if width > max_dim or height > max_dim:
                    resampling = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', Image.LANCZOS)
                    img.thumbnail((max_dim, max_dim), resampling)

                save_as_png = 'png' in (content_type or '').lower() and ('A' in img.getbands() or img.mode in ('RGBA', 'LA'))
                output = BytesIO()
                if save_as_png:
                    img.save(output, format='PNG', optimize=True)
                else:
                    if img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')
                    img.save(output, format='JPEG', quality=jpeg_quality, optimize=True, progressive=True)
                optimized = output.getvalue()
                if optimized and len(optimized) < len(content):
                    return optimized
        except Exception as e:
            _logger.debug("Skip image optimize product=%s error=%s", product_ref or 'N/A', e)

        return content

    def _fetch_rs_image_base64(self, image_url, image_sync_ctx=None, product_ref='', allow_default_fallback=True):
        """Download RS image and return base64 string; return False on recoverable failure."""
        if not image_url:
            return False

        ctx = image_sync_ctx or {}
        cfg = ctx.get('cfg') or self._get_api_config()
        token = ctx.get('token')
        session = ctx.get('session') or self._make_session()

        try:
            timeout = int(os.getenv('PRODUCT_IMAGE_TIMEOUT', '20'))
        except (TypeError, ValueError):
            timeout = 20

        image_full_url = self._build_rs_image_full_url(image_url, cfg)
        if not image_full_url:
            _logger.warning(
                "⚠️ Skip sync image: cannot build full URL for product=%s image_url=%r",
                product_ref or 'N/A',
                image_url,
            )
            return False

        headers = {'Accept': 'image/*,*/*'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        def _download_image_as_b64(target_url):
            resp = session.get(
                target_url,
                headers=headers,
                verify=cfg.get('ssl_verify', False),
                timeout=timeout,
            )
            resp.raise_for_status()

            content = resp.content or b''
            if not content:
                _logger.warning("⚠️ Skip sync image: empty content product=%s url=%s", product_ref or 'N/A', target_url)
                return False

            content_type = (resp.headers.get('Content-Type') or '').lower()
            if content_type and not content_type.startswith('image/'):
                _logger.warning(
                    "⚠️ Skip sync image: invalid content-type product=%s url=%s content_type=%s",
                    product_ref or 'N/A',
                    target_url,
                    content_type,
                )
                return False

            content = self._optimize_image_bytes(content, content_type=content_type, product_ref=product_ref)
            try:
                return base64.b64encode(content).decode('ascii')
            except Exception as e:
                _logger.warning("⚠️ Skip sync image encode error: product=%s url=%s error=%s", product_ref or 'N/A', target_url, e)
                return False

        url_cache = ctx.setdefault('_url_cache', {})
        image_stats = ctx.setdefault('stats', defaultdict(int))
        image_stats['fetch_attempts'] += 1
        try:
            url_cache_limit = int(os.getenv('PRODUCT_IMAGE_URL_CACHE_LIMIT', '1000'))
        except (TypeError, ValueError):
            url_cache_limit = 1000
        url_cache_limit = max(0, url_cache_limit)

        if image_full_url in url_cache:
            image_stats['cache_hits'] += 1
            return url_cache[image_full_url]

        result = False
        try:
            result = _download_image_as_b64(image_full_url)
        except requests.exceptions.Timeout as e:
            _logger.warning("⚠️ Skip sync image timeout: product=%s url=%s error=%s", product_ref or 'N/A', image_full_url, e)
        except Exception as e:
            _logger.warning("⚠️ Skip sync image download error: product=%s url=%s error=%s", product_ref or 'N/A', image_full_url, e)

        if result:
            image_stats['downloaded'] += 1
            if url_cache_limit and len(url_cache) < url_cache_limit:
                url_cache[image_full_url] = result
            return result

        if allow_default_fallback and not self._is_rs_default_image_url(image_url):
            default_endpoint = (os.getenv('RS_DEFAULT_IMAGE_ENDPOINT') or '/api/files/default.png').strip()
            default_url = self._build_rs_image_full_url(default_endpoint, cfg)
            if default_url and default_url != image_full_url:
                if default_url in url_cache:
                    return url_cache[default_url]
                try:
                    fallback_b64 = _download_image_as_b64(default_url)
                    if fallback_b64:
                        image_stats['fallback_downloaded'] += 1
                        if url_cache_limit and len(url_cache) < url_cache_limit:
                            url_cache[default_url] = fallback_b64
                        _logger.info(
                            "ℹ️ Product image fallback to default image: product=%s failed_url=%s default_url=%s",
                            product_ref or 'N/A',
                            image_full_url,
                            default_url,
                        )
                        return fallback_b64
                except Exception as e:
                    _logger.warning(
                        "⚠️ Skip sync image fallback error: product=%s default_url=%s error=%s",
                        product_ref or 'N/A',
                        default_url,
                        e,
                    )

        return False

    def _apply_product_image_to_vals(self, item, vals, image_sync_ctx=None, existing_product_id=None):
        """Set vals['image_1920'] only when RS image download succeeds."""
        ctx = image_sync_ctx or {}
        mode = (ctx.get('mode') or 'missing').strip().lower()
        image_stats = ctx.setdefault('stats', defaultdict(int))
        if mode == 'off':
            image_stats['mode_off_skipped'] += 1
            return

        image_url = self._extract_rs_image_url(item)
        if not image_url:
            image_stats['no_url_skipped'] += 1
            return

        cfg = ctx.get('cfg') or self._get_api_config()
        image_full_url = self._build_rs_image_full_url(image_url, cfg)
        if not image_full_url:
            image_stats['invalid_url_skipped'] += 1
            return

        existing_has_image = False
        existing_image_url = False
        if existing_product_id:
            has_image_set = ctx.get('_has_image_set')
            if has_image_set is not None:
                existing_has_image = existing_product_id in has_image_set
            else:
                existing_tmpl = self.env['product.template'].browse(existing_product_id).exists()
                existing_has_image = bool(existing_tmpl and existing_tmpl.image_1920)
            existing_image_url = (ctx.get('_existing_image_url_map') or {}).get(existing_product_id)

        is_default_image = self._is_rs_default_image_url(image_url)
        if is_default_image and existing_has_image:
            # Keep existing image if product already has one; only fill blank images with default image.
            image_stats['default_kept'] += 1
            return

        if existing_has_image:
            if mode == 'missing':
                image_stats['existing_kept'] += 1
                return
            if mode == 'changed' and existing_image_url and existing_image_url == image_full_url:
                image_stats['unchanged_skipped'] += 1
                return

        dto = (
            item.get('productdto')
            or item.get('productDto')
            or item.get('productDTO')
            or {}
        )
        product_ref = (dto.get('cid') or dto.get('id') or dto.get('externalId') or vals.get('default_code') or '').strip() or 'N/A'
        image_b64 = self._fetch_rs_image_base64(
            image_full_url,
            image_sync_ctx=image_sync_ctx,
            product_ref=product_ref,
            allow_default_fallback=not existing_has_image,
        )
        if image_b64:
            vals['image_1920'] = image_b64
            if ctx.get('track_source_url'):
                vals['x_rs_image_url'] = image_full_url
                vals['x_rs_image_synced_at'] = fields.Datetime.now()
            image_stats['written'] += 1
            if existing_product_id:
                has_image_set = ctx.get('_has_image_set')
                if isinstance(has_image_set, set):
                    has_image_set.add(existing_product_id)
                if ctx.get('_existing_image_url_map') is not None:
                    ctx['_existing_image_url_map'][existing_product_id] = image_full_url

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
            size = int(os.getenv('SYNC_BATCH_SIZE', '1000'))
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

    def _iter_batches(self, endpoint, token, batch_size=1000, limit=None):
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

    def _sync_streaming(self, endpoint, token, product_type, child_model=None, cache=None, error_ctx=None, limit=None, image_sync_ctx=None):
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
                            items, cache, product_type, child_model, error_ctx=error_ctx, image_sync_ctx=image_sync_ctx
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
        cache['categories_by_code'] = {}
        if 'code' in self.env['product.category']._fields:
            for c in self.env['product.category'].search_read([], ['id', 'code']):
                code = (c.get('code') or '').strip().upper()
                if code:
                    cache['categories_by_code'][code] = c['id']

        # Suppliers
        for s in self.env['res.partner'].search_read([('ref', '!=', False)], ['id', 'ref']):
            cache['suppliers'][s['ref'].upper()] = s['id']

        # Company cho seller_ids
        vnoptic_company = self.env['res.company'].search([('name', 'ilike', 'Công ty Kính mắt Việt Nam')], limit=1)
        cache['_seller_company_id'] = vnoptic_company.id if vnoptic_company else self.env.company.id

        # Taxes (Purchase taxes only)
        for t in self.env['account.tax'].search_read([('type_tax_use', '=', 'purchase')], ['id', 'name']):
            cache['taxes'][t['name']] = t['id']

        # Statuses (selection mapping: name → value)
        cache['statuses'] = {'MỚI': 'new', 'HIỆN HÀNH': 'current', 'NEW': 'new', 'CURRENT': 'current'}

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
        cache['lens_powers'] = {}
        if 'product.lens.power' in self.env:
            for r in self.env['product.lens.power'].search_read([], ['id', 'value']):
                cache['lens_powers'][float(r['value'])] = r['id']
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
                    if val:
                        raw = str(val).strip()
                        if raw:
                            cache[key][raw.upper()] = r['id']
                            # Extra normalization for product.group to make name matching robust
                            if model == 'product.group' and key == 'groups':
                                def _norm_group_key(s):
                                    s = str(s or '').strip()
                                    s = s.replace('–', '-').replace('—', '-')
                                    s = re.sub(r'\s+', ' ', s)
                                    s = re.sub(r'\s*-\s*', ' - ', s)
                                    s = re.sub(r'\s+', ' ', s).strip()
                                    return s.upper()

                                cache[key][_norm_group_key(raw)] = r['id']
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
            raw_name = name or cid
            # Viết hoa chữ cái đầu mỗi từ cho tên bảo hành
            if model_name == 'product.warranty':
                raw_name = raw_name[:1].upper() + raw_name[1:] if raw_name else raw_name
            vals = {'name': raw_name, 'code': cid}
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
        coating_str = '-'.join(sorted(str(c).strip() for c in coating_codes if str(c).strip()))
        return f"{cid}|{index_code}|{material_code}|{coating_str}|{diameter}|{brand_code}"

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

    @staticmethod
    def _format_power_value(raw_val):
        if raw_val is None or raw_val == '':
            return False
        try:
            f = float(raw_val)
        except (TypeError, ValueError):
            return False
        sign = '+' if f >= 0 else '-'
        return f"{sign}{abs(f):.2f}"

    @staticmethod
    def _find_variant_by_values(template, value_ids):
        value_set = set(value_ids)
        for variant in template.product_variant_ids:
            if set(variant.product_template_attribute_value_ids.mapped('product_attribute_value_id').ids) == value_set:
                return variant
        return False

    def _get_lens_variant(self, template, sph, cyl, add_val=None):
        sph_val = self._format_power_value(sph)
        cyl_val = self._format_power_value(cyl)
        if not sph_val or not cyl_val:
            return False

        add_fmt = self._format_power_value(add_val) if add_val not in (None, '', False) else False

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

        return self._find_variant_by_values(template, value_ids)

    def _build_lens_template_key_from_stock(self, rec):
        coating_raw = rec.get('coating') or rec.get('coatings') or rec.get('coatingCodes') or []
        if isinstance(coating_raw, str):
            coating_codes = [c.strip() for c in coating_raw.split(',') if c.strip()]
        else:
            coating_codes = [str(c).strip() for c in coating_raw if str(c).strip()]

        coating_str = '-'.join(sorted(str(c).strip() for c in coating_codes if str(c).strip()))
        return f"{rec.get('cid') or rec.get('CID') or ''}|{rec.get('index') or rec.get('Index') or ''}|{rec.get('material') or rec.get('Material') or ''}|{coating_str}|{rec.get('diameter') or rec.get('Diameter') or ''}|{rec.get('brand') or rec.get('Brand') or ''}"

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

    def _prepare_base_vals(self, item, cache, product_type, coating_ids=None, lens_template_key=None, image_sync_ctx=None):
        # Một số endpoint có thể trả key khác nhau (productdto/productDto/...) hoặc flatten trực tiếp.
        dto = (
            item.get('productdto')
            or item.get('productDto')
            or item.get('productDTO')
            or {}
        )

        def _pick_str(src, keys):
            if not isinstance(src, dict):
                return ''
            for k in keys:
                v = src.get(k)
                if v in (None, False):
                    continue
                s = str(v).strip()
                if s:
                    return s
            return ''

        def _looks_like_code(s):
            # Avoid treating English name (contains spaces) as a code/default_code.
            return bool(s) and not any(ch.isspace() for ch in str(s))

        def _pick_code(src, keys):
            if not isinstance(src, dict):
                return ''
            for k in keys:
                v = src.get(k)
                if v in (None, False):
                    continue
                s = str(v).strip()
                if s and _looks_like_code(s):
                    return s
            return ''

        # CID là khoá chính trong hệ thống RS.
        # Đồng nhất cho mọi loại sản phẩm: chỉ lấy các trường dạng "code" (không có khoảng trắng).
        cid = (
            _pick_code(dto, ['cid', 'default_code', 'defaultCode', 'code', 'sku'])
            or _pick_code(item, ['cid', 'default_code', 'defaultCode', 'code', 'sku'])
        )
        if not cid:
            raise ValueError("Missing CID")

        # default_code là "Mã viết tắt" trên Odoo: sync thống nhất cho mọi loại sản phẩm.
        default_code = cid


        product_name = dto.get('fullname') or 'Unknown'
        forced_len_type = False
        grp_type_name = ((dto.get('groupdto') or {}).get('groupTypedto') or {}).get('name', 'Khác')

        # ── Resolve group/brand/categ từ default_code: [GG][BBB][III][XXXXX] ──
        grp_id = False
        grp_rec = None
        categ_id = False
        _parsed_brand_id = False

        if default_code and len(default_code) >= 5:
            try:
                _grp_seq = int(default_code[:2])
                _brd_seq = int(default_code[2:5])

                # Rule: mã bắt đầu bằng "01" → danh mục TK, nhóm sequence=19, len_type=DT
                if default_code[:2] == '01':
                    _tk_cat = self.env['product.category'].search([('code', '=', 'TK')], limit=1) if 'code' in self.env['product.category']._fields else False
                    if _tk_cat:
                        categ_id = _tk_cat.id
                    _grp_match = self.env['product.group'].search([('sequence', '=', 19)], limit=1)
                    forced_len_type = 'DT'
                # Rule: mã bắt đầu bằng "04" → danh mục GK, nhóm sequence=27
                elif default_code[:2] == '04':
                    _gk_cat = self.env['product.category'].search([('code', '=', 'GK')], limit=1) if 'code' in self.env['product.category']._fields else False
                    if _gk_cat:
                        categ_id = _gk_cat.id
                    _grp_match = self.env['product.group'].search([('sequence', '=', 27)], limit=1)
                # Rule: mã bắt đầu bằng "15" → danh mục TK, nhóm sequence=19, Bifocal → HT
                elif default_code[:2] == '15':
                    _tk_cat = self.env['product.category'].search([('code', '=', 'TK')], limit=1) if 'code' in self.env['product.category']._fields else False
                    if _tk_cat:
                        categ_id = _tk_cat.id
                    _grp_match = self.env['product.group'].search([('sequence', '=', 19)], limit=1)
                    if 'bifocal' in (product_name or '').lower():
                        forced_len_type = 'HT'
                else:
                    _grp_match = self.env['product.group'].search([('sequence', '=', _grp_seq)], limit=1)
                if _grp_match:
                    grp_rec = _grp_match
                    grp_id = _grp_match.id
                    if not categ_id and getattr(_grp_match, 'category_id', False):
                        categ_id = _grp_match.category_id.id

                _brd_match = self.env['product.brand'].search([('sequence', '=', _brd_seq)], limit=1)
                if _brd_match:
                    _parsed_brand_id = _brd_match.id
            except Exception:
                pass

        if product_type == 'accessory':
            accessory_categ_id = self._get_accessory_category_id(cache)
            if accessory_categ_id:
                categ_id = accessory_categ_id

        if not categ_id:
            categ_id = self.env.ref('product.product_category_all').id

        # Fill loại tròng từ product_type của nhóm
        _lens_types = {'DT', 'HT', 'DAT', 'PT'}
        if grp_rec and getattr(grp_rec, 'product_type', False) and grp_rec.product_type in _lens_types:
            forced_len_type = grp_rec.product_type

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
                        'company_id': cache.get('_seller_company_id', self.env.company.id),
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
        product_status = False
        status_name = (dto.get('statusProductdto') or {}).get('name', '')
        if status_name:
            product_status = cache['statuses'].get(status_name.upper(), False)

        product_kind = 'consu'

        # Basic Vals
        vals = {
            'name': product_name,
            'default_code': default_code,
            'type': product_kind,
            'categ_id': categ_id,
            'uom_id': cache.setdefault('_uom_unit_id', self.env.ref('vnop_sync.uom_chiec', raise_if_not_found=False) and self.env.ref('vnop_sync.uom_chiec').id or self.env.ref('uom.product_uom_unit').id),
            'uom_po_id': cache['_uom_unit_id'],
            'list_price': self._to_float(dto.get('rtPrice'), default=0.0),
            'standard_price': self._to_float(dto.get('orPrice'), default=0.0) * self._to_float(
                (dto.get('currencyZoneDTO') or {}).get('value'),
                default=1.0
            ),
            'supplier_taxes_id': [(6, 0, [tax_id])] if tax_id else [(5,)],
            'seller_ids': seller_vals if seller_vals else [],
            'brand_id': _parsed_brand_id or False,
            'country_id': self._get_or_create(cache, 'countries', 'res.country', dto.get('codto')),
            'warranty_id': self._get_or_create(cache, 'warranties', 'product.warranty', dto.get('warrantydto')),
            'warranty_supplier_id': self._get_or_create(cache, 'warranties', 'product.warranty', dto.get('warrantySupplierdto')),
            'warranty_retail_id': self._get_or_create(cache, 'warranties', 'product.warranty', dto.get('warrantyRetailDTO')),
            # Nhóm sản phẩm dùng chung (computed inverse sẽ map về lens/opt/acc_* nếu cần)
            'group_id': grp_id or False,
            # Custom Fields (prefixed with x_)
            'x_eng_name': dto.get('engName', ''),
            'description': dto.get('note', ''),
            'x_uses': dto.get('uses', ''),
            'x_guide': dto.get('guide', ''),
            'x_warning': dto.get('warning', ''),
            'x_preserve': dto.get('preserve', ''),
            'x_accessory_total': int(dto.get('accessoryTotal') or 0),
            'product_status': product_status,
            'x_currency_zone_code': (dto.get('currencyZoneDTO') or {}).get('cid', ''),
            'x_currency_zone_value': self._to_float((dto.get('currencyZoneDTO') or {}).get('value'), default=0.0),
            'x_ws_price': self._to_float(dto.get('wsPrice') or dto.get('wsPriceMax'), default=0.0),
            'x_ws_price_min': self._to_float(dto.get('wsPriceMin'), default=0.0),
            'x_ws_price_max': self._to_float(dto.get('wsPriceMax'), default=0.0),
            'manufacturer_months': int((dto.get('warrantydto') or {}).get('value') or 0),
            'company_months': int((dto.get('warrantySupplierdto') or {}).get('value') or 0),
            'bao_hanh_ban_le': int((dto.get('warrantyRetailDTO') or {}).get('value') or 0),
            'x_group_type_name': grp_type_name,
        }

        # Sync QR URL từ Java (https://erp.vnoptictech.com.vn/product/{id})
        java_id = dto.get('id')
        if java_id:
            vals['x_java_qr_url'] = f'https://erp.vnoptictech.com.vn/product/{java_id}'

        if forced_len_type:
            vals['len_type'] = forced_len_type

        # Set company cho toàn bộ sản phẩm sync (nếu product.template có field company_id)
        if 'company_id' in self.env['product.template']._fields:
            vals['company_id'] = self.env.company.id

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

            def _goc_power(raw_val, power_type=None):
                """Get or create product.lens.power by float value."""
                if raw_val is None or raw_val == '':
                    return False
                try:
                    fval = float(raw_val)
                except (TypeError, ValueError):
                    return False
                formatted = f"{fval:+.2f}"
                cached = cache.get('lens_powers_m2o', {}).get(fval)
                if cached:
                    return cached
                found = self.env['product.lens.power'].search([('value', '=', fval)], limit=1)
                if found:
                    cache.setdefault('lens_powers_m2o', {})[fval] = found.id
                    return found.id
                try:
                    with self.env.cr.savepoint():
                        rec = self.env['product.lens.power'].create({'value': fval})
                    cache.setdefault('lens_powers_m2o', {})[fval] = rec.id
                    return rec.id
                except Exception:
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
                'x_prism': extract_label(item.get('prism')) or False,
                'x_prism_base': extract_label(item.get('prismBase') or item.get('prism_base')) or False,
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

        # Image sync: chỉ set image_1920 khi tải ảnh RS thành công.
        if image_sync_ctx:
            try:
                self._apply_product_image_to_vals(
                    item,
                    vals,
                    image_sync_ctx=image_sync_ctx,
                    existing_product_id=cache['products'].get(default_code),
                )
            except Exception as e:
                _logger.warning(
                    "⚠️ Skip product image mapping due to unexpected error: product_type=%s default_code=%s error=%s",
                    product_type,
                    vals.get('default_code'),
                    e,
                )

        pid = cache['products'].get(default_code)

        return vals, pid

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
        gender_val = item.get('gender')
        vals = {
            'opt_season': item.get('season', ''),
            'opt_model': item.get('model', ''),
            'opt_serial': item.get('serial', ''),
            'opt_oem_ncc': item.get('oemNcc', ''),
            'opt_sku': item.get('sku', ''),
            'opt_color': item.get('color', ''),
            # gender từ RS: 0=Nam, 1=Nữ, 2=Unisex → 0 là giá trị hợp lệ (không được coi là False)
            'opt_gender': str(gender_val) if gender_val is not None else False,
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
        }

        # ─── RS adapter: chỉ set khi payload có key tương ứng (tránh override về 0) ───
        if 'lensLength' in item or 'daiMat' in item:
            vals['dai_mat'] = float(item.get('lensLength') or item.get('daiMat') or 0)
        if 'ngangMat' in item or 'nangMat' in item:
            # giữ fallback 'nangMat' (typo cũ) + hỗ trợ 'ngangMat' (đúng chính tả)
            vals['ngang_mat'] = float(item.get('ngangMat') or item.get('nangMat') or 0)

        # bao_hanh_ban_le đã map chuẩn ở _prepare_base_vals từ productdto.warrantyRetailDTO.value
        # Chỉ override nếu endpoint opt trả months trực tiếp.
        dto = item.get('productdto') or {}
        if 'retailWarrantyMonths' in dto or 'baoHanhBanLe' in item:
            vals['bao_hanh_ban_le'] = int(dto.get('retailWarrantyMonths') or item.get('baoHanhBanLe') or 0)

        return vals

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

    def _process_lens_variant_items(self, items, cache, error_ctx=None, image_sync_ctx=None):
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
                    lens_template_key=template_key,
                    image_sync_ctx=image_sync_ctx,
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

    def _process_accessory_batch(self, items, cache, error_ctx=None, image_sync_ctx=None):
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

                    # ── currency: optional (fallback về company currency) ───────
                    step = 'ref_currency'
                    cur_code = (cz_dto.get('cid') or '').strip()
                    _cur_id, _cur_err = self._acc_get_or_create_ref(
                        'currency',
                        cur_code or (cz_dto if cz_dto else None),
                        cache, 'acc_currency', 'res.currency',
                        name_field='name', code_field='name',
                        required=False, sku=sku
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
                    vals, pid = self._prepare_base_vals(item, cache, 'accessory', image_sync_ctx=image_sync_ctx)

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

                    categ_id = vals.get('categ_id')
                    if categ_id:
                        categ = self.env['product.category'].browse(categ_id)
                        if not categ.exists():
                            fallback_id = self._get_accessory_category_id(cache)
                            fallback = self.env['product.category'].browse(fallback_id) if fallback_id else self.env.ref('product.product_category_all')
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

        return success, errors

    def _process_batch(self, items, cache, product_type, child_model=None, error_ctx=None, image_sync_ctx=None):
        """
        Xử lý batch create/update sản phẩm từ API.
        - Lens và Opt: specs đã được map trực tiếp vào template (Hướng B).
        - Accessory và các loại khác: chỉ tạo/update product.template.
        """
        if product_type == 'lens':
            return self._process_lens_variant_items(items, cache, error_ctx=error_ctx, image_sync_ctx=image_sync_ctx)

        # Accessory: xử lý per-record với savepoint riêng + logging đầy đủ
        # KHÔNG thay đổi gì ở đây liên quan lens/opt
        if product_type == 'accessory':
            return self._process_accessory_batch(items, cache, error_ctx=error_ctx, image_sync_ctx=image_sync_ctx)

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
                    vals, pid = self._prepare_base_vals(item, cache, product_type, image_sync_ctx=image_sync_ctx)
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

    def sync_products_limited(self, limit=1000):
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
                        {'sync_status': 'error', 'sync_log': str(e)[:1000]}
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
        product_tmpl = self.env['product.template']
        existing_ids = list(cache.get('products', {}).values())
        image_mode = self._get_image_sync_mode(limit=limit)
        track_source_url = 'x_rs_image_url' in product_tmpl._fields
        existing_image_url_map = {}
        try:
            has_image_set = set(
                product_tmpl.search([
                    ('id', 'in', existing_ids), ('image_1920', '!=', False)
                ]).ids
            ) if existing_ids else set()
        except Exception:
            has_image_set = set()
        if track_source_url and existing_ids:
            try:
                for row in product_tmpl.search_read(
                    [('id', 'in', existing_ids), ('x_rs_image_url', '!=', False)],
                    ['id', 'x_rs_image_url'],
                ):
                    existing_image_url_map[row['id']] = (row.get('x_rs_image_url') or '').strip()
            except Exception:
                existing_image_url_map = {}
        image_sync_ctx = {
            'token': token,
            'cfg': cfg,
            'session': self._make_session(),
            'mode': image_mode,
            'track_source_url': track_source_url,
            '_has_image_set': has_image_set,
            '_existing_image_url_map': existing_image_url_map,
        }
        stats = {}
        error_ctx = self._init_sync_error_ctx()

        # Lens
        s, f = self._sync_streaming(
            cfg['lens_endpoint'], token, 'lens', cache=cache, error_ctx=error_ctx, limit=limit,
            image_sync_ctx=image_sync_ctx,
        )
        stats['lens'] = s
        stats['failed'] = f

        try:
            self._sync_lens_stock(token, cfg, cache)
        except Exception:
            pass

        # Opt
        s, f = self._sync_streaming(
            cfg['opts_endpoint'], token, 'opt', cache=cache, error_ctx=error_ctx, limit=limit,
            image_sync_ctx=image_sync_ctx,
        )
        stats['opt'] = s
        stats['failed'] += f

        # Accessory
        s, f = self._sync_streaming(
            cfg['types_endpoint'], token, 'accessory', cache=cache, error_ctx=error_ctx, limit=limit,
            image_sync_ctx=image_sync_ctx,
        )
        stats['acc'] = s
        stats['failed'] += f

        total = stats['lens'] + stats['opt'] + stats['acc']
        msg = f"Đã đồng bộ {total} (Mắt:{stats['lens']}, Gọng:{stats['opt']}, Khác:{stats['acc']}). Lỗi: {stats['failed']}"

        lines = [msg]
        image_stats = image_sync_ctx.get('stats') or {}
        if image_stats:
            lines.append(
                "\n── Ảnh sản phẩm ──\n"
                f"  mode={image_mode} | downloaded={image_stats.get('downloaded', 0)} | "
                f"fallback={image_stats.get('fallback_downloaded', 0)} | write={image_stats.get('written', 0)} | "
                f"cache_hit={image_stats.get('cache_hits', 0)} | unchanged_skip={image_stats.get('unchanged_skipped', 0)} | "
                f"existing_skip={image_stats.get('existing_kept', 0)} | no_url_skip={image_stats.get('no_url_skipped', 0)}"
            )
        if error_ctx.get('counts'):
            counts_sorted = sorted(error_ctx['counts'].items(), key=lambda kv: (-kv[1], kv[0]))
            lines.append("\n── Tóm tắt lỗi theo loại ──")
            for k, v in counts_sorted:
                lines.append(f"  {k}: {v} lỗi")
        if error_ctx.get('samples'):
            lines.append(f"\n── Chi tiết lỗi ({len(error_ctx['samples'])} mẫu) ──")
            lines.extend(error_ctx['samples'])

        full_log = "\n".join(lines)
        max_chars = error_ctx.get('max_chars', 200000)
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
