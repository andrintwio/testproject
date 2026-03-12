from odoo import models, fields, tools
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
    _inherit = ['mail.thread', 'mail.activity.mixin']

    
    name = fields.Char(string="Repository Name", required=True)
    tw_last_sync = fields.Datetime("Last Sync Date")
    tw_has_modules = fields.Boolean("Contains Modules")
    tw_module_count = fields.Integer(string="Module Count")
    tw_last_main_sha = fields.Char(string="Repository SHA")
    tw_branch = fields.Char(string="Branch", help="If not set we use GitHub default branch")

    def action_discovery_cron(self):
        """
        Main entry point for the discovery process.
        Scans 'twio-tech' for syncable repositories, identifies Odoo modules,
        and adds them to the processing queue.
        """
        start_time = time.time()
        MAX_SECONDS = 600
        g = self._get_github_client()
        syncable_gh_repos = self._get_syncable_gh_repos(g, 'twio-tech')
        Queue = self.env['tw.module.sync.queue'].sudo()
        Catalog = self.env['tw.module.catalog'].sudo()
        
        # Define threshold for "recently synced" check (12 hours)
        sync_threshold = fields.Datetime.now() - relativedelta(hours=12)
        
        for repo_gh_obj in syncable_gh_repos:
            _logger.info("Starting GitHub Module Catalog Sync for Repo %s...", repo_gh_obj.name)
            
            # Stop if we've exceeded the execution time limit
            if time.time() - start_time > MAX_SECONDS:
                _logger.warning("Discovery Cron reached time limit. Stopping burst.")
                break

            # Find or create the tracking record for this repository
            record = self.search([('name', '=', repo_gh_obj.name)], limit=1)
            if not record:
                record = self.create({'name': repo_gh_obj.name})

            try:
                # Skip if no changes detected based on SHA or recent sync
                is_up_to_date, branch = record._is_up_to_date(repo_gh_obj, sync_threshold)
                if is_up_to_date:
                    # branch is None if we skipped based on time threshold (no API call made)
                    branch_name = branch.name if branch else (record.tw_branch or repo_gh_obj.default_branch)
                    _logger.info("Repo %s: No changes on %s. Skipping.", repo_gh_obj.name, branch_name)
                    continue

                # Fetch Tree Metadata (recursive list of all files in default branch)
                manifest_data = record._get_repo_manifest_data(repo_gh_obj, branch)

                if not manifest_data:
                    continue
                
                # Identify Odoo modules by finding '__manifest__.py' files
                found_tech_names = set()
                for manifest_path in manifest_data.get('paths', []):
                    # Extract tech_name and path within repo
                    module_path = manifest_path.rsplit('/__manifest__.py', 1)[0] if '/' in manifest_path else ""
                    tech_name = module_path.split('/')[-1] if module_path else repo_gh_obj.name
                    found_tech_names.add(tech_name)
                    
                    # Compute SHAs for the module's manifest, README, and index.html
                    all_shas = self._get_module_shas(module_path, manifest_data['tree_map'])

                    # Add to queue if not already in catalog or queue
                    Queue.add_to_queue(
                        repo_name=repo_gh_obj.name,
                        tech_name=tech_name,
                        module_path=module_path,
                        all_shas=all_shas
                    )

                # Cleanup: Remove modules that are in our catalog but no longer in the GitHub tree
                stale_modules = Catalog.search([
                    ('tw_repo_name', '=', repo_gh_obj.name),
                    ('tw_technical_name', 'not in', list(found_tech_names))
                ])
                if stale_modules:
                    _logger.info("Repo %s: Removing %s stale modules from catalog.", repo_gh_obj.name, len(stale_modules))
                    stale_modules.unlink()

                # Update repo state
                record.write({
                    'tw_last_main_sha': branch.commit.sha, 
                    'tw_last_sync': fields.Datetime.now(),
                    'tw_module_count': manifest_data.get('count', 0),
                    'tw_has_modules': bool(manifest_data.get('count', 0)),
                })

                # Commit changes periodically to avoid long-running transactions if not testing
                if not tools.config['test_enable']:
                    self.env.cr.commit()

            except Exception as e:
                if not tools.config['test_enable']:
                    self.env.cr.rollback()
                _logger.error("Discovery failed for %s: %s", repo_gh_obj.name, str(e))
                continue
       
        # Trigger the worker cron to process the queue items immediately
        worker_cron = self.env.ref('tw_module_catalog.ir_cron_process_sync_queue', raise_if_not_found=False)
        if worker_cron:
            try:
                worker_cron._trigger()
            except UserError:
                _logger.info("Worker cron is already running, skipping trigger.")
            except Exception as e:
                _logger.error("Failed to directly trigger worker cron: %s", e)

        return True


    def _get_github_client(self):
        """
        Authenticates with GitHub using a token stored in system parameters.
        Returns: github.Github object or False if token is missing.
        """
        token = self.env['ir.config_parameter'].sudo().get_param('tw_module_catalog.github_token')
        if not token:
            _logger.error("GitHub Token not found in System Parameters!")
            return False
        auth = Auth.Token(token)
        return Github(auth=auth)

    def _get_syncable_gh_repos(self, github_client, org_name):
        """
        Retrieves a list of repositories from the organization that should be synced.
        Filters out forks, blacklisted repos, and Odoo system repositories.
        """
        exclusions = self.env['tw.github.repo.blacklist'].sudo().search([('active', '=', True)])
        exclude_list = exclusions.mapped('name')
        system_defaults = ['odoo', 'enterprise', 'design-themes']
        
        try:
            org = github_client.get_organization(org_name)
            # Fetch all repos, sorted by most recently pushed
            syncable_gh_repos = [
                r for r in org.get_repos(sort='pushed', direction='desc')
                if not r.fork 
                and r.name not in exclude_list 
                and r.name not in system_defaults
            ]
            _logger.info("Found %s repositories to scan.", len(syncable_gh_repos))
            return syncable_gh_repos
        except Exception as e:
            _logger.error("Failed to connect to GitHub Organization: %s", str(e))
            return []

    def _get_repo_manifest_data(self, repo_gh_obj, branch_obj):
        """
        Retrieves manifest paths and file SHAs for a repository using the Git Tree API.
        Uses recursive tree fetching to minimize API calls (1 call per repository).
        """        
        _logger.info("Scanning Repo %s for Modules.", repo_gh_obj.name)
        try:
            if not branch_obj:
                branch_obj = self.get_production_branch(repo_gh_obj)
            # Fetch the entire file tree recursively (maximum performance)
            tree = repo_gh_obj.get_git_tree(branch_obj.commit.sha, recursive=True)
            
            # Create a lookup map: file path -> file SHA
            tree_map = {item.path: item.sha for item in tree.tree}
            
            # Filter for Odoo manifest files
            manifest_paths = [p for p in tree_map.keys() if p.endswith('/__manifest__.py') or p == '__manifest__.py']
            
            return {
                'paths': manifest_paths, 
                'tree_map': tree_map, 
                'count': len(manifest_paths)
            }
        except Exception as e:
            _logger.error("Failed to get manifests from repo %s: %s", repo_gh_obj.name, str(e))
            return False
                
    def _get_module_shas(self, module_path, tree_map):
        """
        Computes SHAs for core module files to detect content changes.
        Returns a dict of SHAs and the README path found (md or rst).
        """
        readme_sha = False
        readme_path = False
        
        prefix = f"{module_path}/" if module_path else ""
        manifest_path = f"{prefix}__manifest__.py"
        md_path = f"{prefix}README.md"
        rst_path = f"{prefix}README.rst"
        index_path = f"{prefix}static/description/index.html"

        # Prioritize README.md over README.rst
        if tree_map.get(md_path):
            readme_path = md_path
            readme_sha = tree_map[md_path]
        elif tree_map.get(rst_path):
            readme_path = rst_path
            readme_sha = tree_map[rst_path]

        manifest_sha = tree_map.get(manifest_path)
        index_sha = tree_map.get(index_path, False)
        
        # Combine SHAs into a single string for easy change detection
        module_sha = f"{manifest_sha}|{readme_sha}|{index_sha}"

        return {
            'module_sha': module_sha, 
            'manifest_sha': manifest_sha, 
            'readme_sha': readme_sha, 
            'index_sha': index_sha, 
            'readme_path': readme_path
        }

    def _is_up_to_date(self, repo_gh_obj, sync_threshold):
        """
        Determines if a repository should be skipped during the discovery scan.
        Skips if last sync was recent or if the trunk SHA hasn't changed.
        """
        # Skip if synced within the last threshold period (e.g., 12 hours)
        if self.tw_last_sync and isinstance(self.tw_last_sync, datetime.datetime):
            if self.tw_last_sync > sync_threshold:
                return True, None

        # Skip if the latest commit SHA matches our records
        branch = self.get_production_branch(repo_gh_obj)
        if self.tw_last_main_sha == branch.commit.sha:
            return True, branch

        return False, branch

    def get_production_branch(self, repo_gh_obj):
            """
            Customized branch selection:
            1. Manual override in tw_branch
            2. Odoo.sh Production branch (if module tw_odoo_sh is installed)
            3. GitHub Default Branch
            """
            # Manual Override
            if self.tw_branch:
                try:
                    return repo_gh_obj.get_branch(self.tw_branch)
                except Exception:
                    _logger.warning("Manual branch %s not found for %s", self.tw_branch, repo_gh_obj.name)

            # Look up the Production branch from tw_odoo_sh_monitoring
            sh_repo = self.env['tw_odoo_sh.repository'].sudo().search([
                ('name', '=', repo_gh_obj.name)
            ], limit=1)

            if sh_repo:
                # Find the branch record marked as 'production'
                prod_branch_record = sh_repo.tw_branch_ids.filtered(lambda b: b.tw_stage == 'production')
                if prod_branch_record:
                    prod_branch_name = prod_branch_record[0].name
                    try:
                        # Sync the name back to our record for visibility
                        if self.tw_branch != prod_branch_name:
                            self.write({'tw_branch': prod_branch_name})
                        return repo_gh_obj.get_branch(prod_branch_name)
                    except Exception:
                        _logger.error("Odoo.sh Production branch %s not found on GitHub for %s", prod_branch_name, repo_gh_obj.name)

            # 3. Fallback to GitHub Default
            return repo_gh_obj.get_branch(repo_gh_obj.default_branch)