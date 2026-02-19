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

_logger = logging.getLogger(__name__)

class TWModuleCatalog(models.Model):
    _name = 'tw.module.catalog'
    _description = 'TW Module Catalog'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'tw_name'
    
    tw_technical_name = fields.Char(string='Technical Name', required=True, readonly=True, index=True)
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

    def action_process_queue_cron(self):
        BATCH_LIMIT = 40
        _logger.info("WORKER_CRON Started. Batch Limit: %s", BATCH_LIMIT)
        g = self._get_github_client()
        if not g:
            return
        
        tasks = self.env['tw.module.sync.queue'].sudo().search([('state', '=', 'pending')], limit=BATCH_LIMIT)

        # Prefetch existing modules 
        tech_names = tasks.mapped('tw_technical_name')
        repo_names = tasks.mapped('tw_repo_name')
        existing_recs = self.env['tw.module.catalog'].sudo().search([
            ('tw_technical_name', 'in', tech_names),
            ('tw_repo_name', 'in', repo_names)
        ])
        existing_map = {(r.tw_repo_name, r.tw_technical_name): r for r in existing_recs}
            
        for task in tasks:
            try:
                repo = g.get_repo(f"twio-tech/{task.tw_repo_name}")
                shas = {
                    'manifest_sha': task.tw_manifest_sha,
                    'readme_sha': task.tw_readme_sha,
                    'readme_path': task.tw_readme_path,
                    'index_sha': task.tw_index_sha
                }
                
                content = self._fetch_module_content(repo, task.tw_module_path, shas, {})
                
                if content:
                    # Use pre-fetched record
                    existing = existing_map.get((task.tw_repo_name, task.tw_technical_name), self.env['tw.module.catalog'])

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
                if not tools.config['test_enable']:
                    self.env.cr.commit()
                
            except Exception as e:
                if not tools.config['test_enable']:
                    self.env.cr.rollback()
                task.write({'state': 'error', 'error_log': str(e)})
                _logger.error("Processing failed for %s: %s", task.tw_technical_name, str(e))
                

        remaining_count = self.env['tw.module.sync.queue'].search_count([('state', '=', 'pending')])
        cron = self.env.ref('tw_module_catalog.ir_cron_process_sync_queue', raise_if_not_found=False)
        if cron:
            if remaining_count > 0:
                cron.sudo()._trigger()
        return True

    def _get_github_client(self):
        """Returns an authenticated Github client."""
        token = self.env['ir.config_parameter'].sudo().get_param('tw_module_catalog.github_token')
        if not token:
            _logger.error("GitHub Token not found in System Parameters!")
            return False
        auth = Auth.Token(token)
        return Github(auth=auth)
        
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

                # Determine if markdown or rst
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
            return False  
        
    def _process_found_module(self, repo, path, manifest_raw, index_raw=False, readme_html=False, module_sha=None, tech_name=None, existing_module=None):
        """
        Processes a single Odoo module found in a repository.
        Parses the manifest, generates hashes, identifies clusters, adds tags, 
        and handles record create/update.
        """
        try:
            # Parse manifest
            data = self._parse_manifest(manifest_raw)
            if not data:
                _logger.warning("Skipping module %s in %s: Empty or invalid manifest.", tech_name, repo.name)
                return

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

            # Create dependency tags
            depends_list = data.get('depends', [])
            tag_ids = self.env['tw.module.dependency.tag'].get_or_create_tags(depends_list)

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
