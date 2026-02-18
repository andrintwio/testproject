from odoo import fields, models, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class TwOdooShRepositoryUser(models.Model):
    _name = 'tw_odoo_sh.repository.user'
    _description = 'Odoo.sh Repository User'
    _inherit = 'tw_odoo_sh.monitoring.mixin'
    _order = 'tw_user_id'

    tw_repository_id = fields.Many2one('tw_odoo_sh.repository', string='Repository', required=True, ondelete='cascade', index=True)
    tw_user_id = fields.Many2one('res.users', string='User', required=False, ondelete='cascade', index=True)
    tw_user_name = fields.Char(compute='_compute_tw_user_name', string='User Name', readonly=True, store=True)
    tw_github_user = fields.Char(string='GitHub User', readonly=False, help='GitHub username from Odoo.sh', required=True)
    tw_hosting_identifier = fields.Char(string='Hosting Identifier', readonly=True, help='Odoo.sh hosting identifier for API calls')
    tw_permission = fields.Selection([
        ('admin', 'Admin'),
        ('tester', 'Tester'),
        ('developer', 'Developer')
    ], string='Permission', required=True, default='developer')

    @api.depends('tw_user_id')
    def _compute_tw_user_name(self):
        for user in self:
            user.tw_user_name = user.tw_user_id.name if user.tw_user_id else ''

    @api.onchange('tw_user_id')
    def _onchange_tw_user_id(self):
        """Auto-fill GitHub user when user is selected"""
        if self.tw_user_id and hasattr(self.tw_user_id, 'tw_github_user') and self.tw_user_id.tw_github_user:
            self.tw_github_user = self.tw_user_id.tw_github_user

    @api.model_create_multi
    def create(self, vals_list):
        """Create repository user and add to Odoo.sh if not synced"""
        # Process each vals dict
        for vals in vals_list:
            # Auto-fill GitHub user from user if not provided
            tw_github_user = vals.get('tw_github_user', '').strip() if vals.get('tw_github_user') else ''
            if not tw_github_user:
                if 'tw_user_id' in vals and vals.get('tw_user_id'):
                    user = self.env['res.users'].browse(vals['tw_user_id'])
                    if user and hasattr(user, 'tw_github_user') and user.tw_github_user:
                        vals['tw_github_user'] = user.tw_github_user.strip()
            
            # Ensure tw_github_user is set
            final_tw_github_user = vals.get('tw_github_user', '').strip() if vals.get('tw_github_user') else ''
            if not final_tw_github_user:
                raise ValidationError("GitHub User is required. Please select a user with a GitHub user or enter the GitHub username manually.")
        
        records = super().create(vals_list)
        
        # Process each created record
        for record in records:
            
            # If hosting_identifier is not set, it means it's a new user being added manually
            # We need to add it to Odoo.sh
            if not record.tw_hosting_identifier and record.tw_repository_id and record.tw_github_user:
                project_name = record.tw_repository_id.tw_project_name or record.tw_repository_id.name
                if project_name:
                    try:
                        # Call API to add collaborator (using mixin method)
                        result = record._add_collaborator_public(project_name, record.tw_github_user)
                            
                        # Update record with hosting_identifier and permission from response
                        if result:
                            record.sudo().write({
                                'tw_hosting_identifier': str(result.get('hosting_identifier', '')),
                                'tw_permission': result.get('access_level', 'developer'),
                            })
                        _logger.info(f"Added user {record.tw_github_user} to repository {project_name} in Odoo.sh")
                    except Exception as e:
                        _logger.error(f"Error adding user to Odoo.sh: {str(e)}")
                        # Don't raise error, allow creation but log it
        
        return records[0] if len(records) == 1 else records

    def unlink(self):
        """Remove collaborator from Odoo.sh when deleting"""
        # Store data before deletion
        repos_to_update = {}
        for record in self:
            if record.tw_hosting_identifier and record.tw_repository_id:
                repo_id = record.tw_repository_id.id
                if repo_id not in repos_to_update:
                    repos_to_update[repo_id] = {
                        'repository': record.tw_repository_id,
                        'users': []
                    }
                repos_to_update[repo_id]['users'].append({
                    'hosting_identifier': record.tw_hosting_identifier,
                    'github_user': record.tw_github_user,
                })
        
        # Delete records
        result = super().unlink()
        
        # Call API to remove from Odoo.sh
        for repo_data in repos_to_update.values():
            repository = repo_data['repository']
            project_name = repository.tw_project_name or repository.name
            
            if project_name:
                for user_data in repo_data['users']:
                    try:
                        # Call API to remove collaborator (using mixin method)
                        repository._remove_collaborator_public(project_name, user_data['hosting_identifier'])
                        _logger.info(f"Removed user {user_data['github_user']} from repository {project_name} in Odoo.sh")
                    except Exception as e:
                        _logger.error(f"Error removing user from Odoo.sh: {str(e)}")
                        # Don't raise error, deletion already happened
    
        return result

    def write(self, vals):
        """Prevent changing tw_user_id for existing records and update permissions in Odoo.sh"""
        if 'tw_user_id' in vals and self.ids:
            # Check if tw_user_id is being changed
            for record in self:
                if record.tw_user_id and record.tw_user_id.id != vals.get('tw_user_id'):
                    raise ValidationError("You cannot change the user of an existing repository user. Please delete the current user and add a new one if you need to change the user.")
        
        # Update permissions in Odoo.sh if permission is being changed
        if 'tw_permission' in vals and self.ids:
            for record in self:
                if record.tw_permission != vals.get('tw_permission') and record.tw_hosting_identifier and record.tw_repository_id:
                    project_name = record.tw_repository_id.tw_project_name or record.tw_repository_id.name
                    if not project_name:
                        raise ValidationError("Repository project name is not available.")
                    
                    try:
                        # Call API to update user access (using mixin method)
                        record.tw_repository_id._change_user_access_public(project_name, record.tw_hosting_identifier, vals.get('tw_permission'))
                        _logger.info(f"Updated permission for user {record.tw_github_user} to {vals.get('tw_permission')} in Odoo.sh")
                    except Exception as e:
                        _logger.error(f"Error updating permission in Odoo.sh for user {record.tw_github_user}: {str(e)}")
                        raise ValidationError(f"Error updating permission in Odoo.sh: {str(e)}")
        
        return super().write(vals)

    _repository_github_user_unique = models.Constraint(
        "unique(tw_repository_id, tw_github_user)",
        "This GitHub user is already assigned to this repository!",
    )
