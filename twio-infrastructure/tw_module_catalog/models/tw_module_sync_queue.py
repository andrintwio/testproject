from odoo import models, fields, api

class TWModuleSyncQueue(models.Model):
    _name = 'tw.module.sync.queue'
    _description = 'GitHub Sync Queue'

    tw_repo_name = fields.Char(index=True)
    tw_technical_name = fields.Char(index=True)
    tw_module_path = fields.Char()
    
    # SHAs captured from the Git Tree scan
    tw_manifest_sha = fields.Char()
    tw_readme_sha = fields.Char()
    tw_readme_path = fields.Char()
    tw_index_sha = fields.Char()
    tw_module_sha = fields.Char()

    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('error', 'Error')
    ], default='pending', index=True)
    error_log = fields.Text()

    @api.model
    def add_to_queue(self, repo_name, tech_name, module_path, all_shas):
        """Checks if module is in catalog or existing queue. If not add to queue."""
        
        in_catalog = self.env['tw.module.catalog'].search_count([
            ('tw_repo_name', '=', repo_name),
            ('tw_technical_name', '=', tech_name),
            ('tw_module_sha', '=', all_shas['module_sha'])
        ])
        if in_catalog:
            return False

        in_queue = self.search_count([
            ('tw_repo_name', '=', repo_name),
            ('tw_technical_name', '=', tech_name),
            ('tw_module_sha', '=', all_shas['module_sha']),
            ('state', '=', 'pending')
        ])
        
        if not in_queue:
            self.create({
                'tw_repo_name': repo_name,
                'tw_technical_name': tech_name,
                'tw_module_path': module_path,
                'tw_manifest_sha': all_shas.get('manifest_sha'),
                'tw_readme_sha': all_shas.get('readme_sha'),
                'tw_readme_path': all_shas.get('readme_path'),
                'tw_index_sha': all_shas.get('index_sha'),
                'tw_module_sha': all_shas.get('module_sha'),
            })
            return True
        
        return False
