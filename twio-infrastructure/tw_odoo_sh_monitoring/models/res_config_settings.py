from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tw_odoo_sh_monitoring_session_id = fields.Char(string="Odoo.sh Session ID",config_parameter="tw_odoo_sh_monitoring.session_id",groups='base.group_system')
    tw_odoo_sh_monitoring_default_project = fields.Integer(string="Default Project ID",config_parameter="tw_odoo_sh_monitoring.default_project",groups='base.group_system')

