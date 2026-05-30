from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()
        if res is True:
            for picking in self:
                picking._generate_warranty_registrations_from_moves()
        return res

    def _generate_warranty_registrations_from_moves(self):
        """Sinh phiếu bảo hành sau khi xác nhận phiếu giao hàng bán.

        - Chỉ chạy với picking giao hàng bán (có sale_id, picking_type outgoing).
        - Số tem = tổng quantity đã chốt trên stock.move của từng sale.order.line
          (chỉ tính sản phẩm có gói bảo hành).
        - Idempotent qua đếm registration đã tồn tại trên sale.order.line.
        """
        self.ensure_one()
        if not self.sale_id:
            return
        if self.picking_type_id and self.picking_type_id.code != 'outgoing':
            return
        order = self.sale_id
        Reg = self.env['warranty.registration']

        # Gom quantity theo sale.order.line trên tất cả picking đã done của đơn
        # để cộng dồn khi giao nhiều lần.
        qty_by_line = {}
        done_pickings = order.picking_ids.filtered(lambda p: p.state == 'done')
        for move in done_pickings.move_ids:
            sol = move.sale_line_id
            if not sol or sol.display_type:
                continue
            qty_by_line[sol.id] = qty_by_line.get(sol.id, 0.0) + (move.quantity or 0.0)

        # Ngày xuất kho = min(date_done) của các picking outgoing done.
        # date_done là datetime UTC — phải convert sang timezone của user
        # trước khi .date() để tránh lệch 1 ngày (vd: validate 06:30 GMT+7
        # = 23:30 UTC hôm trước → .date() sẽ ra hôm trước).
        date_done_list = [p.date_done for p in done_pickings if p.date_done]
        if date_done_list:
            min_dt_utc = min(date_done_list)
            date_delivered = fields.Datetime.context_timestamp(self, min_dt_utc).date()
        else:
            date_delivered = False

        to_create = []
        for sol_id, total_qty in qty_by_line.items():
            sol = self.env['sale.order.line'].browse(sol_id)
            warranty = order._get_warranty_for_line(sol)
            if not warranty:
                continue
            qty = int(total_qty)
            if qty <= 0:
                continue
            existing = Reg.search_count([('sale_order_line_id', '=', sol.id)])
            need = max(qty - existing, 0)
            if not need:
                continue
            to_create.extend([{
                'sale_order_id': order.id,
                'sale_order_line_id': sol.id,
                'product_id': sol.product_id.id,
                'warranty_id': warranty.id,
                'date_delivered': date_delivered,
            } for _ in range(need)])

        if to_create:
            Reg.create(to_create)
