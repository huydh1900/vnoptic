import os
import requests
import logging
from datetime import datetime, timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ServerConnector(models.Model):
    _name = 'server.connector'
    _description = 'Spring Boot API Connector'
    _rec_name = 'api_url'

    api_url = fields.Char(
        string='API Base URL',
        default=lambda self: os.getenv('SPRINGBOOT_API_URL', 'http://localhost:8080'),
        required=True
    )
    service_username = fields.Char(
        string='Service Username',
        default=lambda self: os.getenv('SPRINGBOOT_SERVICE_USERNAME', 'odoo_service'),
        required=True
    )
    service_password = fields.Char(
        string='Service Password',
        default=lambda self: os.getenv('SPRINGBOOT_SERVICE_PASSWORD'),
        required=True
    )

    # Token cache (transient - không lưu DB)
    access_token = fields.Char(string='Access Token', store=False)
    token_expires_at = fields.Datetime(string='Token Expires At', store=False)

    # Status
    last_sync_date = fields.Datetime(string='Last Sync Date', readonly=True)
    last_sync_status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error')
    ], string='Last Sync Status', readonly=True)
    last_sync_message = fields.Text(string='Last Sync Message', readonly=True)

    @api.model
    def get_default_connector(self):
        connector = self.search([], limit=1)
        if not connector:
            connector = self.create({
                'api_url': os.getenv('SPRINGBOOT_API_URL', 'http://localhost:8080'),
                'service_username': os.getenv('SPRINGBOOT_SERVICE_USERNAME', 'odoo_service'),
                'service_password': os.getenv('SPRINGBOOT_SERVICE_PASSWORD'),
            })
        return connector

    def _get_valid_token(self):
        self.ensure_one()

        # Check token cache
        now = fields.Datetime.now()
        if self.access_token and self.token_expires_at and self.token_expires_at > now:
            _logger.info("✅ Using cached token")
            return self.access_token

        # Token hết hạn → refresh
        return self._refresh_token()

    def _refresh_token(self):
        """Lấy token mới từ Spring Boot service account"""
        self.ensure_one()

        try:
            url = f"{self.api_url}/api/auth/service-token"
            payload = {
                "username": self.service_username,
                "password": self.service_password
            }

            _logger.info(f"🔄 Requesting token from {url}")

            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()

            data = response.json()
            token = data.get('token')
            expires_in = data.get('expiresIn', 3600)

            if not token:
                raise UserError("No token received from API")

            # Cache token
            self.access_token = token
            self.token_expires_at = fields.Datetime.now() + timedelta(seconds=expires_in)

            _logger.info(f"✅ Token refreshed successfully, expires in {expires_in}s")
            return token

        except requests.exceptions.RequestException as e:
            error_msg = f"Cannot get token from Spring Boot: {str(e)}"
            _logger.error(f"❌ {error_msg}")
            raise UserError(error_msg)

    def _call_api(self, endpoint, method='GET', data=None):
        """Generic method để call API với authentication"""
        self.ensure_one()

        token = self._get_valid_token()
        url = f"{self.api_url}{endpoint}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            _logger.info(f"📡 Calling API: {method} {url}")

            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            error_msg = f"API Error: {str(e)}"
            _logger.error(f"❌ {error_msg}")
            raise UserError(error_msg)

    def test_connection(self):
        self.ensure_one()

        try:
            token = self._get_valid_token()

            # Update status
            self.write({
                'last_sync_date': fields.Datetime.now(),
                'last_sync_status': 'success',
                'last_sync_message': 'Connection successful!'
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': 'Connected to Spring Boot API successfully!',
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            self.write({
                'last_sync_date': fields.Datetime.now(),
                'last_sync_status': 'error',
                'last_sync_message': str(e)
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
