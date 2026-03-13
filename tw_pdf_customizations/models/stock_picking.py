from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    tw_gross_weight = fields.Float(string="Gross weight")
    tw_origin_picking_id = fields.Many2one(
        "stock.picking",
        string="Origin Picking",
        compute="_compute_tw_origin_picking_id",
    )

    @api.depends(
        "move_ids",
        "move_ids.move_orig_ids",
        "move_ids.move_orig_ids.picking_id",
    )
    def _compute_tw_origin_picking_id(self):
        for picking in self:
            for move in picking.move_ids:
                for move_orig in move.move_orig_ids:
                    if move_orig:
                        picking.tw_origin_picking_id = move_orig.picking_id
                        return
            picking.tw_origin_picking_id = False
    