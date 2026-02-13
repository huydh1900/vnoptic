from odoo.tests.common import SavepointCase


class TestContractPurchaseFlow(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id
        cls.partner = cls.env["res.partner"].create({
            "name": "Vendor Contract Test",
            "supplier_rank": 1,
        })
        cls.product = cls.env.ref("product.product_product_8")

    @classmethod
    def _create_po(cls, name):
        return cls.env["purchase.order"].create({
            "name": name,
            "partner_id": cls.partner.id,
            "company_id": cls.company.id,
            "currency_id": cls.currency.id,
            "date_order": "2026-01-01 00:00:00",
            "order_line": [
                (0, 0, {
                    "name": cls.product.display_name,
                    "product_id": cls.product.id,
                    "product_qty": 5,
                    "product_uom": cls.product.uom_po_id.id,
                    "price_unit": 10,
                    "date_planned": "2026-01-02 00:00:00",
                })
            ],
        })

    @classmethod
    def _create_contract(cls, name):
        return cls.env["contract"].create({
            "name": name,
            "partner_id": cls.partner.id,
            "company_id": cls.company.id,
            "shipment_date": "2026-01-03",
        })

    def test_contract_po_many2many_inverse(self):
        contract = self._create_contract("Contract A")
        po1 = self._create_po("PO-A-01")
        po2 = self._create_po("PO-A-02")

        contract.write({"purchase_order_ids": [(6, 0, [po1.id, po2.id])]})

        self.assertIn(contract, po1.contract_ids)
        self.assertIn(contract, po2.contract_ids)

    def test_removing_contract_keeps_other_contract_on_receipt(self):
        contract_a = self._create_contract("Contract A")
        contract_b = self._create_contract("Contract B")
        po = self._create_po("PO-B-01")

        contract_a.write({"purchase_order_ids": [(4, po.id)]})
        contract_b.write({"purchase_order_ids": [(4, po.id)]})

        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("company_id", "=", self.company.id),
        ], limit=1)
        picking = self.env["stock.picking"].create({
            "partner_id": self.partner.id,
            "picking_type_id": incoming_type.id,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "purchase_id": po.id,
            "contract_id": contract_a.id,
        })

        contract_a.write({"purchase_order_ids": [(3, po.id)]})

        self.assertEqual(picking.contract_id, contract_b)


    def test_create_batch_sets_delivery_state_confirmed_arrival(self):
        contract = self._create_contract("Contract Batch")
        po = self._create_po("PO-BATCH")
        contract.write({"purchase_order_ids": [(4, po.id)], "state": "approved"})

        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("company_id", "=", self.company.id),
        ], limit=1)
        picking = self.env["stock.picking"].create({
            "partner_id": self.partner.id,
            "picking_type_id": incoming_type.id,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "purchase_id": po.id,
            "contract_id": contract.id,
            "state": "confirmed",
        })
        self.env["stock.move"].create({
            "name": self.product.display_name,
            "product_id": self.product.id,
            "product_uom": self.product.uom_po_id.id,
            "product_uom_qty": 5,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "picking_id": picking.id,
            "purchase_line_id": po.order_line[:1].id,
            "contract_id": contract.id,
        })

        action = contract.action_create_batch_receipt()

        self.assertEqual(contract.delivery_state, "confirmed_arrival")
        self.assertEqual(action.get("res_model"), "stock.picking.batch")

    def test_sync_receipt_progress_updates_line_and_delivery_state(self):
        contract = self._create_contract("Contract Sync")
        po = self._create_po("PO-SYNC")
        po_line = po.order_line[:1]
        contract.write({"purchase_order_ids": [(4, po.id)], "state": "approved"})
        self.env["contract.line"].create({
            "contract_id": contract.id,
            "product_id": self.product.id,
            "uom_id": po_line.product_uom.id,
            "currency_id": po.currency_id.id,
            "product_qty": 5,
            "qty_contract": 5,
            "qty_received": 0,
            "qty_remaining": 5,
            "price_unit": 10,
            "amount_total": 50,
            "purchase_id": po.id,
            "purchase_line_id": po_line.id,
        })

        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("company_id", "=", self.company.id),
        ], limit=1)
        picking = self.env["stock.picking"].create({
            "partner_id": self.partner.id,
            "picking_type_id": incoming_type.id,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "purchase_id": po.id,
            "contract_id": contract.id,
            "state": "done",
        })

        self.env["stock.move"].create({
            "name": self.product.display_name,
            "product_id": self.product.id,
            "product_uom": self.product.uom_po_id.id,
            "product_uom_qty": 3,
            "quantity": 3,
            "state": "done",
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "picking_id": picking.id,
            "purchase_line_id": po_line.id,
            "contract_id": contract.id,
        })
        contract._sync_receipt_progress()
        line = contract.line_ids[:1]
        self.assertEqual(line.qty_received, 3)
        self.assertEqual(line.qty_remaining, 2)
        self.assertEqual(contract.delivery_state, "partial")

        self.env["stock.move"].create({
            "name": self.product.display_name,
            "product_id": self.product.id,
            "product_uom": self.product.uom_po_id.id,
            "product_uom_qty": 2,
            "quantity": 2,
            "state": "done",
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "picking_id": picking.id,
            "purchase_line_id": po_line.id,
            "contract_id": contract.id,
        })
        contract._sync_receipt_progress()
        self.assertEqual(line.qty_received, 5)
        self.assertEqual(line.qty_remaining, 0)
        self.assertEqual(contract.delivery_state, "done")
