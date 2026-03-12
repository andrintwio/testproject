from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tw_odoo_sh_monitoring_session_id = fields.Char(string="Odoo.sh Session ID",config_parameter="tw_odoo_sh_monitoring.session_id",groups='base.group_system')
    tw_odoo_sh_monitoring_default_project = fields.Integer(string="Default Project ID",config_parameter="tw_odoo_sh_monitoring.default_project",groups='base.group_system')
    tw_odoo_sh_monitoring_github_username = fields.Char(string="GitHub Username",config_parameter="tw_odoo_sh_monitoring.github_username",groups='base.group_system')
    tw_odoo_sh_monitoring_github_password = fields.Char(string="GitHub Password",config_parameter="tw_odoo_sh_monitoring.github_password",groups='base.group_system')
    tw_odoo_sh_monitoring_responsible_user_id = fields.Many2one('res.users', string="Technical Responsible", compute='_compute_tw_responsible_user_id', inverse='_inverse_tw_responsible_user_id', groups='base.group_system', help="User who will be notified by e-mail when GitHub device verification is required.")

    def _compute_tw_responsible_user_id(self):
        ICP = self.env['ir.config_parameter'].sudo()
        user_id = int(ICP.get_param('tw_odoo_sh_monitoring.responsible_user_id', default=0) or 0)
        user = self.env['res.users'].browse(user_id).exists()
        for record in self:
            record.tw_odoo_sh_monitoring_responsible_user_id = user

    def _inverse_tw_responsible_user_id(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for record in self:
            user_id = record.tw_odoo_sh_monitoring_responsible_user_id.id or 0
            ICP.set_param('tw_odoo_sh_monitoring.responsible_user_id', user_id)
