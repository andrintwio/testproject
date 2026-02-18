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
        
        # Check if exact version is in catalog
        in_catalog = self.env['tw.module.catalog'].search_count([
            ('tw_repo_name', '=', repo_name),
            ('tw_technical_name', '=', tech_name),
            ('tw_module_sha', '=', all_shas['module_sha'])
        ])
        if in_catalog:
            return False

        # Check if there is already a PENDING task for this exact version
        in_queue = self.search_count([
            ('tw_repo_name', '=', repo_name),
            ('tw_technical_name', '=', tech_name),
            ('tw_module_sha', '=', all_shas['module_sha']),
            ('state', '=', 'pending')
        ])

        # If it's already pending and the SHA matches, we do nothing
        if in_queue and in_queue.tw_module_sha == module_sha:
            return False

        # Find if we have an OLD version of this module in the queue (any state)
        existing_task = self.search([
            ('tw_repo_name', '=', repo_name),
            ('tw_technical_name', '=', tech_name)
        ], limit=1)
        
        values = {
            'tw_repo_name': repo_name,
            'tw_technical_name': tech_name,
            'tw_module_path': module_path,
            'tw_manifest_sha': all_shas.get('manifest_sha'),
            'tw_readme_sha': all_shas.get('readme_sha'),
            'tw_readme_path': all_shas.get('readme_path'),
            'tw_index_sha': all_shas.get('index_sha'),
            'tw_module_sha': all_shas.get('module_sha'),
            'state': 'pending', # Reset to pending if we are updating
        }

        if existing_task:
            # Update the existing record
            existing_task.write(values)
        else:
            # Brand new module
            self.create(values)
            
        return True
