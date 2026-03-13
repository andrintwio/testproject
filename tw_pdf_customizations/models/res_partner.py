from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"
    
    tw_EORI_nr = fields.Char(string="EORI", size=15)
    