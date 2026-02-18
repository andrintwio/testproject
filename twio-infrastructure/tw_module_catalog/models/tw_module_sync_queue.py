from odoo import models, fields

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
    tw_module_sha = fields.Char() # The composite SHA you already calculate

    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('error', 'Error')
    ], default='pending', index=True)
    error_log = fields.Text()