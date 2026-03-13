from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    tw_gross_weight = fields.Float(string="Gross weight")
    tw_dimension = fields.Char(string="Dimension")
    
    def action_confirm(self):
        res = super().action_confirm()
        for so in self:
            for picking in so.picking_ids:
                picking.tw_gross_weight = so.tw_gross_weight
        return res
        