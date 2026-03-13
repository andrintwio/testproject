from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    tw_producer_raw_mat = fields.Char(string="Producer-raw mat")
    tw_contract_manufacture = fields.Char(string="Contract manufacture")
    tw_fda_ffr_1 = fields.Char(string="FDA Food Facility Registration Number (FFR)")
    tw_fda_ffr_2 = fields.Char(string="FDA Food Facility Registration Number (FFR)")
    