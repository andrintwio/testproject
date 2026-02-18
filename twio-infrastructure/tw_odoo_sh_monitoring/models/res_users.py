from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    tw_github_user = fields.Char(string='GitHub User', help='GitHub username for this user')

