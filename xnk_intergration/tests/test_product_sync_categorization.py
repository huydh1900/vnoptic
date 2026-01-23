# -*- coding: utf-8 -*-
from odoo.tests import tagged, TransactionCase
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestProductSyncCategorization(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ProductSync = self.env['product.sync']
        self.ProductTemplate = self.env['product.template']

    def test_product_type_mapping_lens(self):
        """Test sản phẩm 'Mắt' được map thành product_type='lens'"""
        # Mock data cho sản phẩm Lens
        product_data = {
            'cid': 'TEST-LENS-001',
            'fullname': 'Test Lens Product',
            'groupdto': {
                'name': 'Single Vision',
                'groupTypedto': {
                    'name': 'Mắt'
                }
            },
            'rtPrice': 1000000,
            'wsPrice': 800000,
            'ctPrice': 500000,
            'orPrice': 500000,
            'unit': 'Unit',
            'tax': 10
        }

        # Tạo sync record
        sync = self.ProductSync.create({
            'name': 'Test Sync',
        })

        # Process product
        success, failed, stats = sync._process_and_categorize_products([product_data])

        # Kiểm tra
        self.assertEqual(success, 1, "Should sync 1 product")
        self.assertEqual(stats['lens'], 1, "Should have 1 lens product")

        # Tìm product đã tạo
        product = self.ProductTemplate.search([('default_code', '=', 'TEST-LENS-001')])
        self.assertTrue(product, "Product should be created")
        self.assertEqual(product.product_type, 'lens', "Product type should be 'lens'")

    def test_product_type_mapping_opt(self):
        """Test sản phẩm 'Gọng' được map thành product_type='opt'"""
        product_data = {
            'cid': 'TEST-OPT-001',
            'fullname': 'Test Optical Frame',
            'groupdto': {
                'name': 'Full Frame',
                'groupTypedto': {
                    'name': 'Gọng'
                }
            },
            'rtPrice': 2000000,
            'wsPrice': 1500000,
            'ctPrice': 1000000,
            'orPrice': 1000000,
            'unit': 'Unit',
            'tax': 10
        }

        sync = self.ProductSync.create({
            'name': 'Test Sync',

        })

        success, failed, stats = sync._process_and_categorize_products([product_data])

        self.assertEqual(success, 1)
        self.assertEqual(stats['opts'], 1)

        product = self.ProductTemplate.search([('default_code', '=', 'TEST-OPT-001')])
        self.assertTrue(product)
        self.assertEqual(product.product_type, 'opt', "Product type should be 'opt'")

    def test_product_type_mapping_accessory(self):
        """Test sản phẩm 'Khác' được map thành product_type='accessory'"""
        product_data = {
            'cid': 'TEST-ACC-001',
            'fullname': 'Test Accessory',
            'groupdto': {
                'name': 'Cleaning Kit',
                'groupTypedto': {
                    'name': 'Khác'
                }
            },
            'rtPrice': 50000,
            'wsPrice': 40000,
            'ctPrice': 30000,
            'orPrice': 30000,
            'unit': 'Unit',
            'tax': 10
        }

        sync = self.ProductSync.create({
            'name': 'Test Sync',

        })

        success, failed, stats = sync._process_and_categorize_products([product_data])

        self.assertEqual(success, 1)
        self.assertEqual(stats['other'], 1)

        product = self.ProductTemplate.search([('default_code', '=', 'TEST-ACC-001')])
        self.assertTrue(product)
        self.assertEqual(product.product_type, 'accessory', "Product type should be 'accessory'")

    def test_product_type_mapping_mixed_products(self):
        products_data = [
            {
                'cid': 'TEST-LENS-002',
                'fullname': 'Lens 2',
                'groupdto': {'name': 'Progressive', 'groupTypedto': {'name': 'Mắt'}},
                'rtPrice': 1500000, 'wsPrice': 1200000, 'ctPrice': 800000, 'orPrice': 800000,
                'unit': 'Unit', 'tax': 10
            },
            {
                'cid': 'TEST-OPT-002',
                'fullname': 'Frame 2',
                'groupdto': {'name': 'Rimless', 'groupTypedto': {'name': 'Gọng'}},
                'rtPrice': 2500000, 'wsPrice': 2000000, 'ctPrice': 1500000, 'orPrice': 1500000,
                'unit': 'Unit', 'tax': 10
            },
            {
                'cid': 'TEST-ACC-002',
                'fullname': 'Accessory 2',
                'groupdto': {'name': 'Case', 'groupTypedto': {'name': 'Khác'}},
                'rtPrice': 100000, 'wsPrice': 80000, 'ctPrice': 50000, 'orPrice': 50000,
                'unit': 'Unit', 'tax': 10
            }
        ]

        sync = self.ProductSync.create({
            'name': 'Test Sync',

        })

        success, failed, stats = sync._process_and_categorize_products(products_data)

        self.assertEqual(success, 3)
        self.assertEqual(stats['lens'], 1)
        self.assertEqual(stats['opts'], 1)
        self.assertEqual(stats['other'], 1)

        # Kiểm tra từng product
        lens = self.ProductTemplate.search([('default_code', '=', 'TEST-LENS-002')])
        opt = self.ProductTemplate.search([('default_code', '=', 'TEST-OPT-002')])
        acc = self.ProductTemplate.search([('default_code', '=', 'TEST-ACC-002')])

        self.assertEqual(lens.product_type, 'lens')
        self.assertEqual(opt.product_type, 'opt')
        self.assertEqual(acc.product_type, 'accessory')
