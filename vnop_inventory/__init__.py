# -*- coding: utf-8 -*-
# Import folder models để load các class logic
from odoo import api, SUPERUSER_ID
from . import models


def post_init_hook(cr, registry):
	"""Seed lens index data if missing (for statistic filters)."""
	env = api.Environment(cr, SUPERUSER_ID, {})
	Index = env['product.lens.index']
	if Index.search_count([]) > 0:
		return

	seed = [
		{'name': '1.56', 'cid': '1.56', 'description': 'Chiết suất 1.56', 'activated': True},
		{'name': '1.60', 'cid': '1.60', 'description': 'Chiết suất 1.60', 'activated': True},
		{'name': '1.67', 'cid': '1.67', 'description': 'Chiết suất 1.67', 'activated': True},
		{'name': '1.74', 'cid': '1.74', 'description': 'Chiết suất 1.74', 'activated': True},
		{'name': '1.59', 'cid': '1.59', 'description': 'Polycarbonate', 'activated': True},
	]
	Index.create(seed)

