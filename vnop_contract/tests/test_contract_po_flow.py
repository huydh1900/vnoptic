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
