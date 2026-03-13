from odoo import models, fields, api

class TWModuleSyncQueue(models.Model):
    _name = 'tw.module.sync.queue'
    _description = 'GitHub Sync Queue'

    tw_repo_id = fields.Many2one('tw.github.repo', index=True, ondelete='cascade')
    tw_technical_name = fields.Char(index=True)
    tw_module_path = fields.Char()
    
    # SHAs captured from the Git Tree scan
    tw_manifest_sha = fields.Char()
    tw_readme_sha = fields.Char()
    tw_readme_path = fields.Char()
    tw_index_sha = fields.Char()
    tw_module_sha = fields.Char()
    tw_retry_count = fields.Integer(string="Retry Count", default=0)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('error', 'Error')
    ], default='pending', index=True)
    error_log = fields.Text()

    @api.model
    def add_to_queue(self, repo_id, tech_name, module_path, all_shas):
        """Checks if module is in catalog or existing queue.
        If model is already in catalog with matching module_sha we skip.
        If model is already pending and the SHA matches, we do nothing.
        If model is already pending and the SHA dont matches, we update the queue entry.
        If model is in catalog but with different sha we update the queue entry.
        If model is not in catalog and not in queue we add it to the queue."""
        module_sha = all_shas.get('module_sha')
        # Check if exact version is in catalog
        in_catalog = self.env['tw.module.catalog'].search_count([
            ('tw_repo_id', '=', repo_id),
            ('tw_technical_name', '=', tech_name),
            ('tw_module_sha', '=', module_sha)
        ])
        if in_catalog:
            return False

        # Check if there is already a PENDING task for this exact version
        in_queue = self.search([
            ('tw_repo_id', '=', repo_id),
            ('tw_technical_name', '=', tech_name),
            ('state', '=', 'pending')
        ], limit=1)

        # If it's already pending and the SHA matches, we do nothing
        if in_queue and in_queue.tw_module_sha == module_sha:
            return False

        # Find if we have an OLD version of this module in the queue (any state)
        existing_task = self.search([
            ('tw_repo_id', '=', repo_id),
            ('tw_technical_name', '=', tech_name)
        ], limit=1)

        # Handle 'error' state
        if existing_task:
            if existing_task.tw_module_sha == module_sha:
                # If it failed, but we haven't exhausted retries, reset to pending
                if existing_task.state == 'error' and existing_task.tw_retry_count < 3:
                    existing_task.write({
                        'state': 'pending',
                        'tw_retry_count': existing_task.tw_retry_count + 1
                    })
                    return True
        
                # If it's already pending or has failed too many times, leave it alone
                return False
        
        values = {
            'tw_repo_id': repo_id,
            'tw_technical_name': tech_name,
            'tw_module_path': module_path,
            'tw_manifest_sha': all_shas.get('manifest_sha'),
            'tw_readme_sha': all_shas.get('readme_sha'),
            'tw_readme_path': all_shas.get('readme_path'),
            'tw_index_sha': all_shas.get('index_sha'),
            'tw_module_sha': module_sha,
            'state': 'pending', # Reset to pending if we are updating
            'tw_retry_count': 0,
        }

        if existing_task:
            # Update the existing record
            existing_task.write(values)
        else:
            # Brand new module
            self.create(values)
            
        return True
