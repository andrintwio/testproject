from odoo import models, fields
import logging
from dateutil.relativedelta import relativedelta
import time
from github import Auth
from github import Github
import datetime



_logger = logging.getLogger(__name__)

class TWGithubRepo(models.Model):
    _name = 'tw.github.repo'
    _description = 'Github Repo Sync Log'
    
    name = fields.Char(string="Repository Name", required=True)
    tw_last_sync = fields.Datetime("Last Sync Date")
    tw_has_modules = fields.Boolean("Contains Modules")
    tw_module_count = fields.Integer(string="Module Count")
    tw_last_main_sha = fields.Char(string="Repository SHA")

    def action_discovery_cron(self):
        start_time = time.time()
        MAX_SECONDS = 900

        g = self._get_github_client()
        # Explicitly fetching names and objects
        all_repos = self._get_syncable_repos(g, 'twio-tech')
        
        Queue = self.env['tw.module.sync.queue'].sudo()
        Catalog = self.env['tw.module.catalog'].sudo()
        sync_threshold = fields.Datetime.now() - relativedelta(hours=12)
        _logger.info("CRON_START: sync_threshold=%s (type=%s)", sync_threshold, type(sync_threshold))

        for repo in all_repos:
            _logger.info("Starting GitHub Module Catalog Sync for Repo %s...", repo.name)
            # WORKLOAD CHECK: Is it time to stop?
            if time.time() - start_time > MAX_SECONDS:
                _logger.warning("Discovery Cron reached time limit. Stopping burst.")
                break

            # 1. Standard search for your log record
            record = self.search([('name', '=', repo.name)], limit=1)
            if not record:
                record = self.create({'name': repo.name})

            try:
                # 2. Precise Change Detection
                branch = repo.get_branch(repo.default_branch)
                # ROBUST CHECK: prevent TypeError between datetime and bool
                is_recent = False
                if record.tw_last_sync and isinstance(record.tw_last_sync, datetime.datetime) and isinstance(sync_threshold, datetime.datetime):
                    is_recent = record.tw_last_sync > sync_threshold
                
                if record.tw_last_main_sha == branch.commit.sha or is_recent:
                    _logger.info("Repo %s: No changes on %s. Skipping.", repo.name, repo.default_branch)
                    continue

                # 3. Fetch Tree Metadata
                manifest_data = self._get_repo_manifest_data(record, repo, sync_threshold)
                
                for manifest_path in manifest_data.get('paths', []):
                    # (Logic for tech_name and module_path remains same)
                    module_path = manifest_path.rsplit('/__manifest__.py', 1)[0] if '/' in manifest_path else ""
                    tech_name = module_path.split('/')[-1] if module_path else repo.name
                    
                    all_shas = self._get_module_shas(module_path, manifest_data['tree_map'])
                    
                    # CHECK A: Is it already in the Catalog with this SHA?
                    already_in_catalog = Catalog.search_count([
                        ('tw_repo_name', '=', repo.name),
                        ('tw_technical_name', '=', tech_name),
                        ('tw_module_sha', '=', all_shas['module_sha'])
                    ])

                    if not already_in_catalog:
                        # CHECK B: Is it already sitting in the queue pending?
                        already_queued = Queue.search_count([
                            ('tw_repo_name', '=', repo.name),
                            ('tw_technical_name', '=', tech_name),
                            ('tw_module_sha', '=', all_shas['module_sha']),
                            ('state', '=', 'pending')
                        ])

                        if not already_queued:
                            Queue.create({
                                'tw_repo_name': repo.name,
                                'tw_technical_name': tech_name,
                                'tw_module_path': module_path,
                                'tw_manifest_sha': all_shas['manifest_sha'],
                                'tw_readme_sha': all_shas['readme_sha'],
                                'tw_readme_path': all_shas['readme_path'], # For .md or .rst
                                'tw_index_sha': all_shas['index_sha'],
                                'tw_module_sha': all_shas['module_sha'],
                            })

                # 4. Finalize Repo State
                record.write({
                    'tw_last_main_sha': branch.commit.sha, 
                    'tw_last_sync': fields.Datetime.now()
                })

                # 5. Database & Memory Cleanup
                self.env.cr.commit()
                self.env.invalidate_all()

            except Exception as e:
                self.env.cr.rollback()
                _logger.error("Discovery failed for %s: %s", repo.name, str(e))
                continue
        # Inside action_discovery_cron, after the loop finishes:
        _logger.info("ACTION_DISCOVERY_CRON_FINISHED - Pre-trigger logs reached.")
        _logger.warning("DISCOVERY_LOOP_FINISHED - Attempting to trigger worker_cron")
        worker_cron = self.env.ref('tw_module_catalog.ir_cron_process_sync_queue', raise_if_not_found=False)
        if worker_cron:
            _logger.warning("worker_cron TRIGGERED (ID: %s) via method_direct_trigger()", worker_cron.id)
            try:
                # Force synchronous execution to ensure it runs immediately
                worker_cron._trigger()
            except UserError:
                _logger.info("Worker cron is already running, skipping trigger.")
            except Exception as e:
                _logger.error("Failed to directly trigger worker cron: %s", e)
        else:
            _logger.error("Worker cron 'tw_module_catalog.ir_cron_process_sync_queue' NOT FOUND!")
        
        return True


    def _get_github_client(self):
        """Returns an authenticated Github client."""
        token = self.env['ir.config_parameter'].sudo().get_param('tw_module_catalog.github_token')
        if not token:
            _logger.error("GitHub Token not found in System Parameters!")
            return False
        auth = Auth.Token(token)
        return Github(auth=auth)

    def _get_syncable_repos(self, github_client, org_name):
        """Returns filtered repos from the organization."""
        exclusions = self.env['tw.github.repo.blacklist'].sudo().search([('active', '=', True)]) # Get list of excluded repos
        exclude_list = exclusions.mapped('name')
        system_defaults = ['odoo', 'enterprise', 'design-themes']
        
        try:
            org = github_client.get_organization(org_name)
            all_repos = [
                r for r in org.get_repos(sort='pushed', direction='desc') # Sort by pushed date, descending
                if not r.fork 
                and r.name not in exclude_list 
                and r.name not in system_defaults
            ]
            _logger.info("Found %s repositories to scan.", len(all_repos))
            return all_repos
        except Exception as e:
            _logger.error("Failed to connect to GitHub Organization: %s", str(e))
            return []

    def _get_repo_manifest_data(self, record, repo, sync_threshold):

        """Orchestrates the sync for a single repo."""

        # Defensive check: ensure both values are comparable (both datetimes)
        if record and record.tw_last_sync and isinstance(record.tw_last_sync, datetime.datetime) and isinstance(sync_threshold, datetime.datetime):
            if record.tw_last_sync > sync_threshold:
                return {'status': 'recently synced'}
        
        _logger.info("Scanning Repo for Modules: %s", repo.name) #Non essential

        try:
            # Use Git Tree API (Recursive) - Much faster than search_code and no rate limiting issues
            # 1 API call per repo vs 1 call per 100 files + sleeps
                tree = repo.get_git_tree(repo.default_branch, recursive=True)
                
                # Build Map: Path -> SHA
                # We need this to fetch the BLOBS directly via SHA (super fast) instead of Path
                tree_map = {item.path: item.sha for item in tree.tree}
                
                # Identify Manifests
                manifest_paths = [p for p in tree_map.keys() if p.endswith('/__manifest__.py') or p == '__manifest__.py']
                return {'status': 'success', 'paths': manifest_paths, 'tree_map': tree_map, 'count': len(manifest_paths)}
        except Exception as e:
            _logger.error("Failed to get manifests from repo %s: %s", repo.name, str(e))
            return {'status': 'error', 'paths': [], 'tree_map': {}, 'count': 0}
                
    def _get_module_shas(self, module_path, tree_map):
        # Initialize defaults
        readme_sha = False
        readme_path = False
        
        prefix = f"{module_path}/" if module_path else ""
        manifest_path = f"{prefix}__manifest__.py"
        md_path = f"{prefix}README.md"
        rst_path = f"{prefix}README.rst"
        index_path = f"{prefix}static/description/index.html"

        # Check for Readme
        if tree_map.get(md_path):
            readme_path = md_path
            readme_sha = tree_map[md_path]
        elif tree_map.get(rst_path):
            readme_path = rst_path
            readme_sha = tree_map[rst_path]

        manifest_sha = tree_map.get(manifest_path)
        index_sha = tree_map.get(index_path, False)
        
        # Create the composite SHA for change detection
        module_sha = f"{manifest_sha}|{readme_sha}|{index_sha}"

        return {
            'module_sha': module_sha, 
            'manifest_sha': manifest_sha, 
            'readme_sha': readme_sha, 
            'index_sha': index_sha, 
            'readme_path': readme_path
        }