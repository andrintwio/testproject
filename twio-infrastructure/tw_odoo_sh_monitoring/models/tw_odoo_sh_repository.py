from odoo import fields, models, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class TwOdooShRepository(models.Model):
    _name = 'tw_odoo_sh.repository'
    _description = 'Odoo.sh Repository'
    _inherit = 'tw_odoo_sh.monitoring.mixin'
    _order = 'name'

    name = fields.Char(string='Repository Name', required=True, index=True)
    tw_repository_id = fields.Integer(string='Odoo.sh Repository ID', required=True, index=True)
    tw_owner = fields.Char(string='Owner')
    tw_odoo_branch = fields.Char(string='Odoo Branch')
    tw_project_name = fields.Char(string='Project Name')
    tw_branch_ids = fields.One2many('tw_odoo_sh.branch', 'tw_repository_id', string='Branches')
    tw_branch_count = fields.Integer(string='Branch Count', compute='_compute_tw_branch_count', store=True)
    tw_user_ids = fields.One2many('tw_odoo_sh.repository.user', 'tw_repository_id', string='Users')
    tw_last_sync = fields.Datetime(string='Last Sync', readonly=True)
    tw_sync_status = fields.Char(string='Sync Status', readonly=True)
    tw_last_update_status = fields.Char(string='Build Status', compute='_compute_tw_last_update_status', store=True)

    @api.depends('tw_branch_ids')
    def _compute_tw_branch_count(self):
        for repo in self:
            repo.tw_branch_count = len(repo.tw_branch_ids)

    @api.depends('tw_branch_ids.tw_last_update_status', 'tw_branch_ids.tw_stage', 'tw_sync_status')
    def _compute_tw_last_update_status(self):
        for repo in self:
            # If repository no longer exists in Odoo.sh, show ❓
            if repo.tw_sync_status and 'no longer exists' in repo.tw_sync_status.lower():
                repo.tw_last_update_status = '❓'
            elif not repo.tw_branch_ids:
                repo.tw_last_update_status = '⚪'  # Gray for no build
            else:
                # Get the status from the production branch
                production_branch = repo.tw_branch_ids.filtered(lambda b: b.tw_stage == 'production')
                if production_branch:
                    # Use the status emoji of the production branch
                    repo.tw_last_update_status = production_branch[0].tw_last_update_status
                else:
                    # If no production branch, get the worst status from all branches (failed > warning > success > no_build)
                    statuses = repo.tw_branch_ids.mapped('tw_last_update_status')
                    if '🔴' in statuses:  # Red (failed)
                        repo.tw_last_update_status = '🔴'
                    elif '🟡' in statuses:  # Yellow (warning)
                        repo.tw_last_update_status = '🟡'
                    elif '🟢' in statuses:  # Green (success)
                        repo.tw_last_update_status = '🟢'
                    else:
                        repo.tw_last_update_status = '⚪'  # Gray (no build)

    @api.model
    def action_synchronize_all_odoo_sh_repositories(self):
        """
        Synchronize all Odoo.sh repositories by fetching repositories and creating tw_odoo_sh_repository and tw_odoo_sh_branch records.
        Also removes branches and users that no longer exist in Odoo.sh.
        """
        _logger.info("=" * 80)
        _logger.info("Starting Odoo.sh databases synchronization")
        
        # Get configuration parameters
        session_id = self.env['ir.config_parameter'].sudo().get_param('tw_odoo_sh_monitoring.session_id')
        project_id = int(self.env['ir.config_parameter'].sudo().get_param('tw_odoo_sh_monitoring.default_project') or 0)
        
        if not session_id:
            raise UserError("Odoo.sh Session ID is not configured. Please set it in Settings > Databases > Odoo.sh Monitoring.")
        
        if not project_id:
            raise UserError("Odoo.sh Project ID is not configured. Please set it in Settings > Databases > Odoo.sh Monitoring.")
        
        try:
            # Step 1: Save existing data before synchronization
            _logger.info("Step 1: Saving existing branches and users data before synchronization...")
            existing_repositories = self.env['tw_odoo_sh.repository'].sudo().search([])
            
            # Store existing branches and users by repository
            existing_data = {}
            for repo in existing_repositories:
                existing_branches = repo.tw_branch_ids.mapped('tw_branch_id')
                existing_users = repo.tw_user_ids.mapped('tw_github_user')
                existing_data[repo.tw_repository_id] = {
                    'repository': repo,
                    'tw_branch_ids': set(existing_branches),
                    'user_github_names': set(existing_users),
                }
            _logger.info(f"Saved data for {len(existing_data)} existing repositories")
            
            _logger.info(f"Step 2: Fetching repositories from Odoo.sh for project {project_id}...")
            repositories = self._get_repositories(project_id)
            _logger.info(f"Found {len(repositories)} repositories")
            
            synced_repos = 0
            synced_branches = 0
            deleted_branches = 0
            deleted_users = 0
            errors = []
            
            # Track which repositories exist in Odoo.sh
            synced_repository_ids = set()
            
            for repo_data in repositories:
                repo_id = repo_data.get('id')
                repo_name = repo_data.get('name', 'Unknown')
                synced_repository_ids.add(repo_id)
                _logger.info(f"Processing repository {synced_repos + 1}/{len(repositories)}: {repo_name} (ID: {repo_id})")
                
                try:
                    # Get branches for this repository
                    _logger.info(f"  Fetching branches for repository {repo_id}...")
                    branches = self._get_branches_info(repo_id)
                    _logger.info(f"  Found {len(branches)} branches")
                    
                    # Find or create repository (using sudo to bypass access rights)
                    repository = self.env['tw_odoo_sh.repository'].sudo().search([
                        ('tw_repository_id', '=', repo_id)
                    ], limit=1)
                    
                    repo_vals = {
                        'name': repo_name,
                        'tw_repository_id': repo_id,
                        'tw_owner': repo_data.get('owner', ''),
                        'tw_odoo_branch': repo_data.get('odoo_branch', ''),
                        'tw_project_name': repo_data.get('project_name', ''),
                        'tw_last_sync': fields.Datetime.now(),
                    }
                    
                    if not repository:
                        # Create new repository
                        repository = self.env['tw_odoo_sh.repository'].sudo().create(repo_vals)
                        _logger.info(f"Created new repository: {repository.name}")
                    else:
                        # Update existing repository
                        repository.sudo().write(repo_vals)
                        _logger.info(f"Updated repository: {repository.name}")
                    
                    # Track which branches exist in Odoo.sh for this repository
                    synced_branch_ids = set()
                    
                    # Process each branch
                    for idx, branch_data in enumerate(branches):
                        branch_id = branch_data.get('id')
                        branch_name = branch_data.get('name', 'Unknown')
                        synced_branch_ids.add(branch_id)
                        _logger.info(f"    Processing branch {idx + 1}/{len(branches)}: {branch_name} (ID: {branch_id})")
                        
                        # Get history info (contains trackings with push/rebuild info)
                        history = self._get_branch_history(branch_id)
                        tracking_count = history.get('num_trackings', 0)
                        trackings = history.get('trackings', [])
                        
                        # Get last tracking info (most recent push or rebuild)
                        last_build_commit_msg = ''
                        last_build_commit_author = ''
                        last_build_start_datetime = ''
                        last_tracking_type = ''
                        last_pusher_name = ''
                        
                        if trackings:
                            # Get the first tracking (most recent)
                            last_tracking = trackings[0]
                            last_tracking_type = last_tracking.get('tracking_type', '')
                            last_pusher_name = last_tracking.get('pusher_name', '')
                            last_build_start_datetime = last_tracking.get('create_date', '')
                            # Get commit message from commits[0].message
                            commits = last_tracking.get('commits', [])
                            if commits and len(commits) > 0:
                                last_build_commit_msg = commits[0].get('message', '')
                            last_build_commit_author = last_pusher_name  # Use pusher_name as author
                        
                        # Get last_build_id from branch_data
                        last_build_id_data = branch_data.get('last_build_id', [])
                        last_build_id = last_build_id_data[0] if isinstance(last_build_id_data, list) and last_build_id_data else 0
                        
                        # Find or create branch (using sudo to bypass access rights)
                        branch = self.env['tw_odoo_sh.branch'].sudo().search([
                            ('tw_branch_id', '=', branch_id),
                            ('tw_repository_id', '=', repository.id)
                        ], limit=1)
                        
                        branch_vals = {
                            'name': branch_name,
                            'tw_branch_id': branch_id,
                            'tw_repository_id': repository.id,
                            'tw_stage': branch_data.get('stage', ''),
                            'tw_last_build_id': last_build_id,
                            'tw_last_build_status': branch_data.get('last_build_status', ''),
                            'tw_last_build_result': branch_data.get('last_build_result', ''),
                            'tw_last_build_commit_msg': last_build_commit_msg,
                            'tw_last_build_commit_author': last_build_commit_author,
                            'tw_last_build_date': last_build_start_datetime,
                            'tw_last_tracking_type': last_tracking_type,
                            'tw_last_pusher_name': last_pusher_name,
                            'tw_tracking_count': tracking_count,
                            'tw_last_update': fields.Datetime.now(),
                        }
                        
                        if not branch:
                            # Create new branch
                            branch = self.env['tw_odoo_sh.branch'].sudo().create(branch_vals)
                            _logger.info(f"Created new branch: {branch.name}")
                        else:
                            # Update existing branch
                            branch.sudo().write(branch_vals)
                            _logger.info(f"Updated branch: {branch.name}")
                        
                        synced_branches += 1
                    
                    # Delete branches that no longer exist in Odoo.sh
                    if repo_id in existing_data:
                        existing_branch_ids = existing_data[repo_id]['tw_branch_ids']
                        branches_to_delete = existing_branch_ids - synced_branch_ids
                        if branches_to_delete:
                            _logger.info(f"  Deleting {len(branches_to_delete)} branches that no longer exist in Odoo.sh...")
                            branches_to_remove = self.env['tw_odoo_sh.branch'].sudo().search([
                                ('tw_repository_id', '=', repository.id),
                                ('tw_branch_id', 'in', list(branches_to_delete))
                            ])
                            branch_names = branches_to_remove.mapped('name')
                            branches_to_remove.unlink()
                            deleted_branches += len(branches_to_remove)
                            _logger.info(f"  Deleted branches: {', '.join(branch_names)}")
                    
                    # Synchronize repository users
                    _logger.info(f"  Fetching users for repository {repo_id}...")
                    try:
                        settings_data = self._fetch_repository_settings(repo_id)
                        users_data = settings_data.get('users', [])
                        _logger.info(f"  Found {len(users_data)} users")
                        
                        # Track which users exist in Odoo.sh for this repository
                        synced_user_github_names = set()
                        
                        synced_users = 0
                        for user_data in users_data:
                            github_username = user_data.get('username', '')
                            access_level = user_data.get('access_level', 'developer')
                            hosting_identifier = user_data.get('hosting_identifier', '')
                            
                            if github_username:
                                synced_user_github_names.add(github_username)
                            
                            # Map access_level to permission
                            permission_map = {
                                'admin': 'admin',
                                'tester': 'tester',
                                'developer': 'developer',
                            }
                            permission = permission_map.get(access_level, 'developer')
                            
                            # Search for user by GitHub username
                            user = None
                            if github_username:
                                user = self.env['res.users'].sudo().search([
                                    ('tw_github_user', '=', github_username)
                                ], limit=1)
                            
                            # Find or create repository user
                            repo_user = self.env['tw_odoo_sh.repository.user'].sudo().search([
                                ('tw_repository_id', '=', repository.id),
                                ('tw_github_user', '=', github_username)
                            ], limit=1)
                            
                            user_vals = {
                                'tw_repository_id': repository.id,
                                'tw_user_id': user.id if user else False,
                                'tw_github_user': github_username,
                                'tw_hosting_identifier': str(hosting_identifier) if hosting_identifier else '',
                                'tw_permission': permission,
                            }
                            
                            if not repo_user:
                                # Create new repository user
                                repo_user = self.env['tw_odoo_sh.repository.user'].sudo().create(user_vals)
                                _logger.info(f"    Created new user: {github_username} ({permission})")
                            else:
                                # Update existing repository user
                                repo_user.sudo().write(user_vals)
                                _logger.info(f"    Updated user: {github_username} ({permission})")
                            
                            synced_users += 1
                        
                        # Delete users that no longer exist in Odoo.sh
                        if repo_id in existing_data:
                            existing_user_github_names = existing_data[repo_id]['user_github_names']
                            users_to_delete = existing_user_github_names - synced_user_github_names
                            if users_to_delete:
                                _logger.info(f"  Deleting {len(users_to_delete)} users that no longer exist in Odoo.sh...")
                                users_to_remove = self.env['tw_odoo_sh.repository.user'].sudo().search([
                                    ('tw_repository_id', '=', repository.id),
                                    ('tw_github_user', 'in', list(users_to_delete))
                                ])
                                user_names = users_to_remove.mapped('tw_github_user')
                                users_to_remove.unlink()
                                deleted_users += len(users_to_remove)
                                _logger.info(f"  Deleted users: {', '.join(user_names)}")
                        
                        _logger.info(f"  Synchronized {synced_users} users")
                    except Exception as e:
                        _logger.warning(f"  Error synchronizing users for repository {repo_name}: {str(e)}")
                    
                    # Update repository sync status
                    repository.sudo().write({
                        'tw_sync_status': f'Success: {len(branches)} branches synchronized',
                        'tw_last_sync': fields.Datetime.now(),
                    })
                    
                    synced_repos += 1
                    
                except Exception as e:
                    error_msg = f"Error processing repository {repo_name}: {str(e)}"
                    errors.append(error_msg)
                    _logger.error(error_msg)
                    import traceback
                    _logger.error(traceback.format_exc())
            
            # Step 3: Mark repositories that no longer exist in Odoo.sh with ❓
            _logger.info("Step 3: Checking for repositories that no longer exist in Odoo.sh...")
            all_existing_repo_ids = set(existing_data.keys())
            repos_no_longer_exist = all_existing_repo_ids - synced_repository_ids
            marked_repos = 0
            if repos_no_longer_exist:
                _logger.info(f"Found {len(repos_no_longer_exist)} repositories that no longer exist in Odoo.sh...")
                for repo_id in repos_no_longer_exist:
                    repo = existing_data[repo_id]['repository']
                    _logger.info(f"  Marking repository as not found: {repo.name} (ID: {repo_id})")
                    repo.sudo().write({
                        'tw_last_update_status': '❓',
                        'tw_sync_status': 'Repository no longer exists in Odoo.sh',
                        'tw_last_sync': fields.Datetime.now(),
                    })
                    marked_repos += 1
            
            _logger.info(f"Sync completed: {synced_repos} repos, {synced_branches} branches synchronized, {deleted_branches} branches deleted, {deleted_users} users deleted, {marked_repos} repos marked as not found")
            _logger.info("=" * 80)
            
            message = f'{synced_repos} repositories synchronized successfully ({synced_branches} branches)'
            if deleted_branches > 0:
                message += f'\n{deleted_branches} branches deleted (no longer exist in Odoo.sh)'
            if deleted_users > 0:
                message += f'\n{deleted_users} users deleted (no longer exist in Odoo.sh)'
            if marked_repos > 0:
                message += f'\n{marked_repos} repositories marked as not found in Odoo.sh (❓)'
            if errors:
                message += f'\nErrors: {len(errors)}'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Synchronization Completed',
                    'message': message,
                    'type': 'success' if not errors else 'warning',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            import traceback
            error_msg = f"Error during synchronization: {str(e)}"
            _logger.error("=" * 80)
            _logger.error(f"ERROR: {error_msg}")
            _logger.error("Traceback:")
            _logger.error(traceback.format_exc())
            _logger.error("=" * 80)
            raise UserError(error_msg)

    _repository_unique = models.Constraint(
        "unique(tw_repository_id)",
        "A repository with the same ID already exists!",
    )

