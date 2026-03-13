from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    tw_dimension = fields.Char(string="Dimension")
    tw_gross_weight = fields.Float(string="Gross weight")
    tw_net_weight = fields.Float(string="Net weight", compute="_compute_tw_net_weight")

    @api.depends('line_ids.sale_line_ids.order_id.shipping_weight')
    def _compute_tw_net_weight(self):
        for record in self:
            net_weight = 0
            if record.line_ids.sale_line_ids.order_id:
                order_ids = record.line_ids.sale_line_ids.order_id
                for order in order_ids:
                    net_weight += order.shipping_weight
            record.tw_net_weight = net_weight

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            if move.line_ids.sale_line_ids.order_id:
                # Gross weight
                gross_weight = 0
                order_ids = move.line_ids.sale_line_ids.order_id
                for order in order_ids:
                    gross_weight += order.tw_gross_weight
                move.tw_gross_weight = gross_weight
                # Dimension
                order_id = order_ids[-1] if len(order_ids) > 1 else order_ids
                move.tw_dimension = order_id.tw_dimension   
        return moves
            