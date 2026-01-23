# # controllers/odoo_api_controller.py
# import json
# import logging
#
# from odoo import http
# from odoo.http import request
#
# _logger = logging.getLogger(__name__)
#
#
# class OdooProductApiController(http.Controller):
#
#     @http.route('/api/vnoptic/product/create',
#                 type='json',
#                 auth='none',
#                 methods=['POST'],
#                 csrf=False,
#                 cors='*')
#     def create_product(self, **kwargs):
#         """Tạo sản phẩm - Phân biệt lens, opt, other"""
#         try:
#             data = json.loads(request.httprequest.data.decode('utf-8'))
#             product_type = data.get('product_type', 'lens')  # ← Kiểm tra product_type
#
#             # Tạo product template
#             product_vals = {
#                 'name': data.get('name'),
#                 'cid': data.get('cid'),
#                 'product_type': product_type,
#                 'rt_price': data.get('rt_price'),
#                 'ws_price': data.get('ws_price'),
#                 'ct_price': data.get('ct_price'),
#                 'or_price': data.get('or_price'),
#                 'ws_price_max': data.get('ws_price_max'),
#                 'ws_price_min': data.get('ws_price_min'),
#                 'supplier_id': data.get('supplier_id'),
#                 'group_id': data.get('group_id'),
#                 'status_product_id': data.get('status_product_id'),
#             }
#
#             product = request.env['product.template'].sudo().create(product_vals)
#
#             # Chỉ tạo lens_ids nếu product_type là 'lens'
#             if product_type == 'lens' and data.get('lens_data'):
#                 lens_vals = {
#                     'product_tmpl_id': product.id,
#                     'prism': data['lens_data'].get('prism'),
#                     'base': data['lens_data'].get('base'),
#                     'axis': data['lens_data'].get('axis'),
#                     'sph': data['lens_data'].get('sph'),
#                     'cyl': data['lens_data'].get('cyl'),
#                     'lens_add': data['lens_data'].get('lens_add'),
#                     'diameter': data['lens_data'].get('diameter'),
#                     'corridor': data['lens_data'].get('corridor'),
#                     'design1_id': data['lens_data'].get('design1_id'),
#                     'design2_id': data['lens_data'].get('design2_id'),
#                     'uv_id': data['lens_data'].get('uv_id'),
#                     'index_id': data['lens_data'].get('index_id'),
#                     'material_id': data['lens_data'].get('material_id'),
#                 }
#
#                 # Xử lý coatings
#                 coating_ids = data['lens_data'].get('coating_ids', [])
#                 if coating_ids:
#                     lens_vals['coating_ids'] = [(6, 0, coating_ids)]
#
#                 request.env['product.lens'].sudo().create(lens_vals)
#
#             # Chỉ tạo opt_ids nếu product_type là 'opt'
#             elif product_type == 'opt' and data.get('opt_data'):
#                 opt_vals = {
#                     'product_tmpl_id': product.id,
#                     'season': data['opt_data'].get('season'),
#                     'model': data['opt_data'].get('model'),
#                     'serial': data['opt_data'].get('serial'),
#                     'oem_ncc': data['opt_data'].get('oem_ncc'),
#                     'sku': data['opt_data'].get('sku'),
#                     'gender': data['opt_data'].get('gender'),
#                     'temple_width': data['opt_data'].get('temple_width'),
#                     'lens_width': data['opt_data'].get('lens_width'),
#                     'lens_span': data['opt_data'].get('lens_span'),
#                     'lens_height': data['opt_data'].get('lens_height'),
#                     'bridge_width': data['opt_data'].get('bridge_width'),
#                     'frame_id': data['opt_data'].get('frame_id'),
#                     'frame_type_id': data['opt_data'].get('frame_type_id'),
#                     'shape_id': data['opt_data'].get('shape_id'),
#                 }
#
#                 # Xử lý many2many fields
#                 if data['opt_data'].get('coating_ids'):
#                     opt_vals['coating_ids'] = [(6, 0, data['opt_data']['coating_ids'])]
#                 if data['opt_data'].get('materials_front_ids'):
#                     opt_vals['materials_front_ids'] = [(6, 0, data['opt_data']['materials_front_ids'])]
#                 if data['opt_data'].get('materials_temple_ids'):
#                     opt_vals['materials_temple_ids'] = [(6, 0, data['opt_data']['materials_temple_ids'])]
#
#                 request.env['product.opt'].sudo().create(opt_vals)
#
#             # Nếu là 'other' hoặc 'accessory' - không tạo lens_ids hay opt_ids
#             # Chỉ lưu thông tin product template
#
#             return {
#                 'success': True,
#                 'product_id': product.id,
#                 'cid': product.cid,
#                 'product_type': product.product_type
#             }
#
#         except Exception as e:
#             _logger.error(f"Error creating product: {str(e)}")
#             return {
#                 'success': False,
#                 'error': str(e)
#             }
