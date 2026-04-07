from odoo import http
from odoo.http import content_disposition, request


class ProductExportTemplateController(http.Controller):

    @http.route('/vnop_sync/product_template_template_download', type='http', auth='user')
    def product_template_template_download(self, product_type='mat', file_format='xlsx', **kwargs):
        payload = request.env['product.export.template.wizard']._get_template_payload(
            product_type=product_type,
            file_format=file_format,
        )
        headers = [
            ('Content-Type', payload['mimetype']),
            ('Content-Disposition', content_disposition(payload['filename'])),
        ]
        return request.make_response(payload['content'], headers=headers)
