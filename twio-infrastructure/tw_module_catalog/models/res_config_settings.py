from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tw_module_catalog_github_token = fields.Char(string="Github Token", config_parameter="tw_module_catalog.github_token", groups='base.group_system')
    tw_module_catalog_github_org = fields.Char(string="Github Organization/User", config_parameter="tw_module_catalog.github_org", groups='base.group_system', default='twio-tech')
