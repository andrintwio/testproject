from odoo import fields, models, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    tw_repository_user_count = fields.Integer(string='Repository Access Count', compute='_compute_tw_repository_user_count', store=False)

    @api.depends('user_id')
    def _compute_tw_repository_user_count(self):
        """Compute the number of repository users linked to this employee's user"""
        for employee in self:
            if employee.user_id:
                employee.tw_repository_user_count = self.env['tw_odoo_sh.repository.user'].search_count([
                    ('tw_user_id', '=', employee.user_id.id)
                ])
            else:
                employee.tw_repository_user_count = 0

    def action_view_repository_users(self):
        """Open the repository users view filtered by this employee's user"""
        self.ensure_one()
        if not self.user_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'This employee has no associated user',
                    'type': 'warning',
                }
            }
        
        action = {
            'name': f'Repository Access - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'tw_odoo_sh.repository.user',
            'view_mode': 'list,form',
            'domain': [('tw_user_id', '=', self.user_id.id)],
            'context': {'default_tw_user_id': self.user_id.id},
            'target': 'current',
        }
        return action


