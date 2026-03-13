from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"
    
    tw_DUNS_nr_importer = fields.Char(string="DUNS-Nr Importer")
    