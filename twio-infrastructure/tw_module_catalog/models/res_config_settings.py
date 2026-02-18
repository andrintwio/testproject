from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tw_module_catalog_github_token = fields.Char(string="Github Token",config_parameter="tw_module_catalog.github_token",groups='base.group_system')
    tw_module_catalog_night_sync = fields.Boolean(string="Night Sync Only", config_parameter="tw_module_catalog.night_sync", groups='base.group_system', default=True)

