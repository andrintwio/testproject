from odoo import models, fields, api
from github import Github
import ast
import hashlib
import time
import json
import base64
import logging
import datetime
import markdown
from dateutil.relativedelta import relativedelta
import re
from github import Auth
import uuid
from docutils.core import publish_parts

# Initialize the logger
_logger = logging.getLogger(__name__)

class TWModuleCatalog(models.Model):
    _name = 'tw.module.catalog'
    _description = 'TW Module Catalog'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'tw_name'
    
    tw_technical_name = fields.Char(string='Technical Name', required=True, readonly=True)
    tw_name = fields.Char(string='Name', required=True)
    tw_repo_name = fields.Char(string='Repository Name', required=True, index=True, readonly=True)
    tw_version = fields.Char(string='Version', required=True, readonly=True)
    tw_summary = fields.Text(string='Summary', readonly=True)
    tw_depends = fields.Char(string='Dependencies', readonly=True) 
    tw_author = fields.Char(string='Author', readonly=True)
    tw_repo_link = fields.Char(string='Repository Link', readonly=True)
    tw_category = fields.Char(string='Category', readonly=True) 
    tw_description = fields.Text(string='Description', readonly=True)
    tw_readme = fields.Html(string='Readme', readonly=True)
    tw_index_html_raw = fields.Text(string='Raw HTML Content', readonly=True)
    tw_description_html = fields.Html(string='Description View', sanitize=False, strip_style=False, strip_classes=False, readonly=True)
    tw_hash_1 = fields.Char("Hash 1 (Func)", index=True, readonly=True)
    tw_hash_2 = fields.Char("Hash 2 (Struct)", index=True, readonly=True)
    tw_hash_3 = fields.Char("Hash 3 (Intent)", index=True, readonly=True)
    tw_hash_4 = fields.Char("Hash 4 (Origin)", index=True, readonly=True)
    tw_hash_5 = fields.Char("Hash 5 (DNA)", index=True, readonly=True)
    tw_cluster_hash = fields.Char("Cluster ID", index=True, readonly=True, store=True)
    tw_module_sha = fields.Char(string="Module SHA", readonly=True)
    tw_sibling_ids = fields.Many2many('tw.module.catalog', string='Other Installations', compute="_compute_siblings", help="Other repositories where this same module was found.")
    tw_user_used_ids = fields.Many2many('res.users', 'tw_module_usage_rel', 'module_id', 'user_id', string='Users Who Used This', readonly=True)
    tw_usage_count = fields.Integer(string='Usage Count', compute='_compute_usage_count', store=True, readonly=True)
    tw_i_have_used_this = fields.Boolean(compute='_compute_i_have_used_this', readonly=True)
    tw_dependency_tag_ids = fields.Many2many('tw.module.dependency.tag', string='Tags')
    tw_cluster_label = fields.Char(
        string='Cluster Group', 
        compute='_compute_cluster_label', 
        store=True
    )

    tw_has_siblings = fields.Boolean(
        string='Has Siblings',
        compute='_compute_has_siblings',
        store=True
    )

    @api.depends('tw_cluster_hash')
    def _compute_has_siblings(self):
        # Get all hashes that appear more than once in the database
        self.env.cr.execute('''
            SELECT tw_cluster_hash 
            FROM tw_module_catalog 
            WHERE tw_cluster_hash IS NOT NULL
            GROUP BY tw_cluster_hash 
            HAVING COUNT(*) > 1
        ''')
        hashes_with_siblings = [row[0] for row in self.env.cr.fetchall()]
        
        for rec in self:
            rec.tw_has_siblings = rec.tw_cluster_hash in hashes_with_siblings

    @api.depends('tw_cluster_hash', 'tw_name')
    def _compute_cluster_label(self):
        # Group all records being computed by their hash to minimize queries
        hashes = self.mapped('tw_cluster_hash')
        
        # Map each hash to the name of its oldest member
        master_map = {}
        if hashes:
            self.env.cr.execute('''
                SELECT DISTINCT ON (tw_cluster_hash) tw_cluster_hash, tw_name 
                FROM tw_module_catalog 
                WHERE tw_cluster_hash IN %s 
                ORDER BY tw_cluster_hash, create_date ASC
            ''', (tuple(hashes),))
            master_map = dict(self.env.cr.fetchall())

        # Assign the master name to every record in the cluster
        for rec in self:
            rec.tw_cluster_label = master_map.get(rec.tw_cluster_hash) or rec.tw_name

    @api.depends('tw_cluster_hash')
    def _compute_siblings(self):
        """Finds other modules that belong to the same cluster hash (similar modules)."""
        for rec in self:
            if rec.tw_cluster_hash:
                # Find all records with same cluster hash, excluding self
                siblings = self.search([
                    ('tw_cluster_hash', '=', rec.tw_cluster_hash),
                    ('id', '!=', rec.id)
                ])
                rec.tw_sibling_ids = siblings
            else:
                rec.tw_sibling_ids = self.env['tw.module.catalog']

    @api.depends('tw_user_used_ids')
    def _compute_usage_count(self):
        """Computes the total number of users who have marked this module as used."""
        for rec in self:
            rec.tw_usage_count = len(rec.tw_user_used_ids)

    @api.depends('tw_user_used_ids')
    def _compute_i_have_used_this(self):
        """Checks if the current user is in the list of users who have used this module."""
        for rec in self:
            rec.tw_i_have_used_this = self.env.user in rec.tw_user_used_ids

    def action_toggle_usage(self):
        """Adds or removes the current user from the module's usage list."""
        self.ensure_one()
        if self.env.user in self.tw_user_used_ids:
            self.tw_user_used_ids = [(3, self.env.user.id)] # Remove (Unlink)
        else:
            self.tw_user_used_ids = [(4, self.env.user.id)] # Add (Link)
    
#==================== Start API Sync ====================
    # def action_sync_github_catalog(self):
    #     """
    #     Orchestrates the synchronization process with GitHub in adaptive bursts.
    #     """
    #     start_time = time.time()
        
    #     # 1. Simplified Window Check (No Rescheduling to avoid RPC_ERROR)
    #     night_sync_only = self.env['ir.config_parameter'].sudo().get_param('tw_module_catalog.night_sync', 'True').lower() == 'true'
    #     if night_sync_only:
    #         now_utc = datetime.datetime.now(datetime.timezone.utc)
    #         if not (0 <= now_utc.hour < 5):
    #             return False

    #     _logger.info("Starting GitHub Module Catalog Sync Burst...")
    #     RepoLog = self.env['tw.github.repo']
    #     g = self._get_github_client()
    #     if not g:
    #         _logger.warning("Sync aborted: Missing GitHub Token.")
    #         return False

    #     org_name = 'twio-tech'
    #     all_repos = self._get_syncable_repos(g, org_name)
        
    #     # State tracking for chaining
    #     sync_threshold = fields.Datetime.now() - relativedelta(hours=12)
    #     processed_in_this_burst = 0
    #     burst_limit = 8
    #     has_more = False

    #     for repo in all_repos:
    #         try:
    #             # 2. Cooperative Multitasking: Graceful exit before Odoo timeout
    #             if time.time() - start_time > 600: # 10 minutes
    #                 _logger.info("Sync time limit reached. Chaining next run.")
    #                 has_more = True
    #                 break

    #             if processed_in_this_burst >= burst_limit:
    #                 _logger.info("Burst repository limit reached. Chaining next run.")
    #                 has_more = True
    #                 break

    #             # Get existing repo log
    #             repo_log = RepoLog.sudo().search([('name', '=', repo.name)], limit=1)
                
    #             # Check threshold
    #             if repo_log and repo_log.tw_last_sync and repo_log.tw_last_sync > sync_threshold:
    #                 continue

    #             _logger.info("Scanning Repo for Modules: %s", repo.name)
                
    #             # Process the Repo
    #             manifest_data = self._get_repo_manifest_data(repo_log, repo, sync_threshold)
                
    #             if manifest_data['status'] == 'error' or manifest_data['status'] == 'recently synced':
    #                 continue

    #             if manifest_data['count'] == 0:
    #                 _logger.info("Repo %s has no modules. Skipping.", repo.name)
    #                 log_vals = {'tw_last_sync': fields.Datetime.now(), 'tw_has_modules': False, 'tw_module_count': 0}
    #                 if repo_log:
    #                     repo_log.sudo().write(log_vals)
    #                 else:
    #                     RepoLog.sudo().create({'name': repo.name, **log_vals})
    #                 processed_in_this_burst += 1
    #                 self.env.cr.commit()
    #                 continue

    #             _logger.info("---Found %s manifests in repo %s---", manifest_data['count'], repo.name)

    #             # Process each module
    #             for manifest_path in manifest_data['paths']:
    #                 if manifest_path == '__manifest__.py':
    #                     module_path = ''
    #                 else:
    #                     module_path = manifest_path.rsplit('/__manifest__.py', 1)[0]

    #                 if '/' in module_path:
    #                     tech_name = module_path.split('/')[-1]
    #                 elif module_path:
    #                     tech_name = module_path
    #                 else:
    #                     tech_name = repo.name

    #                 # Get Module SHA and record
    #                 all_shas = self._get_module_shas(module_path, manifest_data['tree_map'])
    #                 module = self.env['tw.module.catalog'].search([
    #                     ('tw_repo_name', '=', repo.name), 
    #                     ('tw_technical_name', '=', tech_name)
    #                 ], limit=1)

    #                 if module and module.tw_module_sha == all_shas['module_sha']:
    #                     continue

    #                 module_content_raw = self._fetch_module_content(repo, module_path, all_shas, manifest_data['tree_map'])
    #                 if not module_content_raw:
    #                     continue

    #                 self._process_found_module(
    #                     repo=repo, path=module_path, manifest_raw=module_content_raw['manifest_raw'], 
    #                     index_raw=module_content_raw['index_raw'], readme_html=module_content_raw['readme_html'],
    #                     module_sha=all_shas['module_sha'], tech_name=tech_name, existing_module=module
    #                 )

    #             # Finalize repo sync
    #             log_vals = {'tw_last_sync': fields.Datetime.now(), 'tw_has_modules': True, 'tw_module_count': manifest_data['count']}
    #             if repo_log:
    #                 repo_log.sudo().write(log_vals)
    #             else:
    #                 RepoLog.sudo().create({'name': repo.name, **log_vals})

    #             _logger.info("Sync Complete for %s.", repo.name)
    #             processed_in_this_burst += 1
    #             self.env.cr.commit()

    #         except Exception as e:
    #             self.env.cr.rollback()
    #             _logger.error("Failed to sync repository %s: %s", repo.name, str(e))
    #             continue

    #     # 3. Adaptive Chaining: Trigger next run if needed
    #     if has_more:
    #         cron = self.env.ref('tw_module_catalog.tw_module_catalog_sync_github_cron', raise_if_not_found=False)
    #         if cron:
    #             _logger.info("Manually triggering follow-up sync burst via _trigger().")
    #             cron._trigger()
        
    #     return True

    def action_process_queue_cron(self):
        BATCH_LIMIT = 40
        _logger.info("WORKER_CRON Started. Batch Limit: %s", BATCH_LIMIT)
        g = self._get_github_client()
        # Process 40 modules at a time (Safe for 3-minute timeout)
        tasks = self.env['tw.module.sync.queue'].search([('state', '=', 'pending')], limit=BATCH_LIMIT)
        _logger.info("WORKER_CRON found %d pending tasks.", len(tasks))
            
        for task in tasks:
            try:
                _logger.info("Starting GitHub Module Catalog Sync for Module %s in repo %s...", task.tw_technical_name, task.tw_repo_name)
                repo = g.get_repo(f"twio-tech/{task.tw_repo_name}")
                
                # Reuse your existing efficient blob fetcher
                shas = {
                    'manifest_sha': task.tw_manifest_sha,
                    'readme_sha': task.tw_readme_sha,
                    'readme_path': task.tw_readme_path,
                    'index_sha': task.tw_index_sha
                }
                
                content = self._fetch_module_content(repo, task.tw_module_path, shas, {})
                
                if content:
                    existing = self.env['tw.module.catalog'].search([
                        ('tw_repo_name', '=', task.tw_repo_name),
                        ('tw_technical_name', '=', task.tw_technical_name)
                    ], limit=1)

                    self._process_found_module(
                        repo=repo, path=task.tw_module_path, 
                        manifest_raw=content['manifest_raw'],
                        index_raw=content['index_raw'], 
                        readme_html=content['readme_html'],
                        module_sha=task.tw_module_sha, 
                        tech_name=task.tw_technical_name, 
                        existing_module=existing
                    )
                    task.state = 'done'
                
                self.env.cr.commit() # Save after every single module
                
            except Exception as e:
                self.env.cr.rollback()
                task.write({'state': 'error', 'error_log': str(e)})
                self.env.cr.commit()
        
        # RETRIGGER CONDITION:
        # If we found exactly 40, there are likely more. Stay at 1 minute.
        # If we found < 40, we just finished the pile. Sleep now.
        remaining_count = self.env['tw.module.sync.queue'].search_count([('state', '=', 'pending')])
        cron = self.env.ref('tw_module_catalog.ir_cron_process_sync_queue', raise_if_not_found=False)
        if cron:
            if remaining_count > 0:
                cron.sudo()._trigger()
        return True

    # def _update_worker_cron_interval(self, interval, unit):
    #         """ Helper to modify the cron schedule dynamically """

    #         cron = self.env.ref('tw_module_catalog.ir_cron_process_sync_queue', raise_if_not_found=False)
    #         if cron and (cron.interval_number != interval or cron.interval_type != unit):
    #             cron.sudo().write({
    #                 'interval_number': interval,
    #                 'interval_type': unit
    #             })


    def _get_github_client(self):
        """Returns an authenticated Github client."""
        token = self.env['ir.config_parameter'].sudo().get_param('tw_module_catalog.github_token')
        if not token:
            _logger.error("GitHub Token not found in System Parameters!")
            return False
        auth = Auth.Token(token)
        return Github(auth=auth)

    # def _get_syncable_repos(self, github_client, org_name):
    #     """Returns filtered repos from the organization."""
    #     exclusions = self.env['tw.github.repo.blacklist'].sudo().search([('active', '=', True)]) # Get list of excluded repos
    #     exclude_list = exclusions.mapped('name')
    #     system_defaults = ['odoo', 'enterprise', 'design-themes']
        
    #     try:
    #         org = github_client.get_organization(org_name)
    #         all_repos = [
    #             r for r in org.get_repos(sort='pushed', direction='desc') # Sort by pushed date, descending
    #             if not r.fork 
    #             and r.name not in exclude_list 
    #             and r.name not in system_defaults
    #         ]
    #         _logger.info("Found %s repositories to scan.", len(all_repos))
    #         return all_repos
    #     except Exception as e:
    #         _logger.error("Failed to connect to GitHub Organization: %s", str(e))
    #         return []

    # def _get_repo_manifest_data(self, repo_log, repo, sync_threshold):

    #     """Orchestrates the sync for a single repo."""

    #     if repo_log and repo_log.tw_last_sync and repo_log.tw_last_sync > sync_threshold:
    #         return {'status': 'recently synced'}
        
    #     _logger.info("Scanning Repo for Modules: %s", repo.name) #Non essential

    #     try:
    #         # Use Git Tree API (Recursive) - Much faster than search_code and no rate limiting issues
    #         # 1 API call per repo vs 1 call per 100 files + sleeps
    #             tree = repo.get_git_tree(repo.default_branch, recursive=True)
                
    #             # Build Map: Path -> SHA
    #             # We need this to fetch the BLOBS directly via SHA (super fast) instead of Path
    #             tree_map = {item.path: item.sha for item in tree.tree}
                
    #             # Identify Manifests
    #             manifest_paths = [p for p in tree_map.keys() if p.endswith('/__manifest__.py') or p == '__manifest__.py']
    #             return {'status': 'success', 'paths': manifest_paths, 'tree_map': tree_map, 'count': len(manifest_paths)}
    #     except Exception as e:
    #         _logger.error("Failed to get manifests from repo %s: %s", repo.name, str(e))
    #         return {'status': 'error', 'paths': [], 'tree_map': {}, 'count': 0}
                
    # def _get_module_shas(self, module_path, tree_map):
    #     # Initialize defaults
    #     readme_sha = False
    #     readme_path = False
        
    #     prefix = f"{module_path}/" if module_path else ""
    #     manifest_path = f"{prefix}__manifest__.py"
    #     md_path = f"{prefix}README.md"
    #     rst_path = f"{prefix}README.rst"
    #     index_path = f"{prefix}static/description/index.html"

    #     # Check for Readme
    #     if tree_map.get(md_path):
    #         readme_path = md_path
    #         readme_sha = tree_map[md_path]
    #     elif tree_map.get(rst_path):
    #         readme_path = rst_path
    #         readme_sha = tree_map[rst_path]

    #     manifest_sha = tree_map.get(manifest_path)
    #     index_sha = tree_map.get(index_path, False)
        
    #     # Create the composite SHA for change detection
    #     module_sha = f"{manifest_sha}|{readme_sha}|{index_sha}"

    #     return {
    #         'module_sha': module_sha, 
    #         'manifest_sha': manifest_sha, 
    #         'readme_sha': readme_sha, 
    #         'index_sha': index_sha, 
    #         'readme_path': readme_path
    #     }

        
    def _fetch_module_content(self, repo, module_path, all_shas, tree_map):
        """Fetches raw content for manifest/readme/index."""

        results = {'manifest_raw': False, 'readme_html': False, 'index_raw': False}
        try:
            # Fetch manifest.py
            if all_shas['manifest_sha']:
                blob = repo.get_git_blob(all_shas['manifest_sha'])
                results['manifest_raw'] = base64.b64decode(blob.content).decode('utf-8')
        
            # Fetch README (Try MD then RST)
            if all_shas['readme_sha']:
                blob = repo.get_git_blob(all_shas['readme_sha'])
                raw = base64.b64decode(blob.content).decode('utf-8')

                # Determine if the readme is markdown or rst
                if all_shas.get('readme_path', '').endswith('.md'):
                    results['readme_html'] = markdown.markdown(raw, extensions=['extra'])
                else:
                    results['readme_html'] = publish_parts(raw, writer_name='html')['html_body']    
            # Fetch index.html
            if all_shas['index_sha']:
                blob = repo.get_git_blob(all_shas['index_sha'])
                results['index_raw'] = base64.b64decode(blob.content).decode('utf-8')
            return results

        except Exception as e:
            _logger.error("Error fetching content for %s: %s", module_path, e)
            return False # Signal a total failure   
        
    def _process_found_module(self, repo, path, manifest_raw, index_raw=False, readme_html=False, module_sha=None, tech_name=None, existing_module=None):
        """
        Processes a single Odoo module found in a repository.
        Parses the manifest, generates hashes, identifies clusters, 
        and handles record create/update.
        """
        try:
            # Parse manifest
            data = self._parse_manifest(manifest_raw)
            if not data:
                _logger.warning("Skipping module %s in %s: Empty or invalid manifest.", tech_name, repo.name)
                return

            # Create dependency tags
            depends_list = data.get('depends', [])
            tag_ids = self._get_or_create_dependency_tags(depends_list)

            # Generate hashes
            hashes = self.generate_pillar_hashes(data)

            # Handle Clustering
            existing_cluster_hash = self._find_similar_peer(
                hashes['tw_hash_1'], 
                hashes['tw_hash_2'], 
                hashes['tw_hash_3'], 
                hashes['tw_hash_4'], 
                hashes['tw_hash_5']
            )
            
            if existing_cluster_hash:
                cluster_hash = existing_cluster_hash
            else:
                cluster_hash = str(uuid.uuid4())

            # Prepare values
            vals = {
                'tw_technical_name': tech_name,
                'tw_name': (data.get('name') or path or tech_name).strip(),
                'tw_repo_name': repo.name,
                'tw_summary': (data.get('summary') or '').strip(),
                'tw_description': (data.get('description') or '').strip(),
                'tw_category': (data.get('category') or '').strip(),
                'tw_depends': ", ".join(depends_list),
                'tw_dependency_tag_ids': [(6, 0, tag_ids)],
                'tw_version': (data.get('version') or '0.0').strip(),
                'tw_readme': readme_html,
                'tw_index_html_raw': index_raw,
                'tw_description_html': index_raw,
                'tw_repo_link': f"{repo.html_url}/tree/{repo.default_branch}/{path}",
                'tw_author': (data.get('author') or 'Unknown').strip(),
                'tw_hash_1': hashes['tw_hash_1'],
                'tw_hash_2': hashes['tw_hash_2'],
                'tw_hash_3': hashes['tw_hash_3'],
                'tw_hash_4': hashes['tw_hash_4'],
                'tw_hash_5': hashes['tw_hash_5'],
                'tw_cluster_hash': cluster_hash,
                'tw_module_sha': module_sha,
            }

            # Database Write/Create
            if existing_module:
                existing_module.sudo().write(vals)
            else:
                self.sudo().create(vals)
                
        except Exception as e:
            # Log the error but don't re-raise it, allowing the main loop to continue
            _logger.error("Error processing module %s in repo %s: %s", tech_name, repo.name, str(e))

    
# ===================== Helper Functions ===================== 

    def _parse_manifest(self, content):
        """Attempts to safely literal_eval the Odoo manifest dictionary from a string."""
        try:
            dict_start = content.find('{')
            dict_end = content.rfind('}') + 1
            if dict_start != -1 and dict_end != -1:
                return ast.literal_eval(content[dict_start:dict_end])
        except Exception as e:
            _logger.warning("Manifest parsing failed: %s", str(e))
            return {}
        return {}

    def _clean_val(self, val):
        """Normalizes Odoo manifest values to ensure consistent hashing. Converts falsy values into empty strings and
            ensures ['a', 'b'] and ['b', 'a'] produce the same hash """
        if not val: 
            return ""
        if isinstance(val, list):
            return sorted([str(i).strip() for i in val])
        return str(val).strip()

    def generate_pillar_hashes(self, data):
        pillars = [
            ('tw_hash_1', {'n': 'name', 'd': 'depends'}),
            ('tw_hash_2', {'n': 'name', 'f': 'data'}),
            ('tw_hash_3', {'s': 'summary'}),
            ('tw_hash_4', {'n': 'name', 'a': 'author'}),
            ('tw_hash_5', {'d': 'depends', 'f': 'data'})
        ]
        
        results = {}
        for field_name, schema in pillars:
            payload = {k: self._clean_val(data.get(v)) for k, v in schema.items()}
            json_str = json.dumps(payload, sort_keys=True)
            results[field_name] = hashlib.md5(json_str.encode()).hexdigest()
            
        return results

    def _find_similar_peer(self, h1, h2, h3, h4, h5):
        """
        Uses a raw SQL query to find a cluster hash that matches at least 3 out of 5 pillar hashes.
        Enables fuzzy/similarity matching across different repositories.
        """
        query = """
            SELECT tw_cluster_hash FROM tw_module_catalog 
            WHERE (
                tw_hash_1 = %s OR tw_hash_2 = %s OR 
                tw_hash_3 = %s OR tw_hash_4 = %s OR tw_hash_5 = %s
            )
            GROUP BY tw_cluster_hash
            HAVING (
                MAX(CASE WHEN tw_hash_1 = %s THEN 1 ELSE 0 END) +
                MAX(CASE WHEN tw_hash_2 = %s THEN 1 ELSE 0 END) +
                MAX(CASE WHEN tw_hash_3 = %s THEN 1 ELSE 0 END) +
                MAX(CASE WHEN tw_hash_4 = %s THEN 1 ELSE 0 END) +
                MAX(CASE WHEN tw_hash_5 = %s THEN 1 ELSE 0 END)
            ) >= 3
            LIMIT 1
        """
        self.env.cr.execute(query, [h1, h2, h3, h4, h5, h1, h2, h3, h4, h5])
        res = self.env.cr.fetchone()

        if res:
            return res[0]
        else:
            return False

    def _get_or_create_dependency_tags(self, depends_list):
        TagModel = self.env['tw.module.dependency.tag'].sudo()
        tag_ids = []
        
        for name in depends_list:
            name = str(name).strip()
            if not name:
                continue
                
            # Check if exists, or create on the fly
            tag = TagModel.search([('name', '=', name)], limit=1)
            if not tag:
                tag = TagModel.create({
                    'name': name,
                    'color': (len(name) % 11) + 1 # Randomish color based on name length
                })
            tag_ids.append(tag.id)
            
        return tag_ids