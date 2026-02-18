from odoo import models, fields

class TWGithubRepoBlacklist(models.Model):
    _name = 'tw.github.repo.blacklist'
    _description = 'GitHub Repo Blacklist'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Blacklisted Repository', required=True, help="Exact name of the GitHub repo to exclude.")
    active = fields.Boolean(default=True, help="Uncheck to re-include this repo without deleting the record.")
    tw_blacklisted_repo_removed = fields.Boolean(default=False, string="Modules Removed", help="True if the blacklisted repo has been removed.")

    _name_unique = models.Constraint(
        'unique (name)', 'This repository is already in the exclusion list!'
    )

    def action_remove_blacklisted_repo(self):
        for rec in self:
            modules = self.env['tw.module.catalog'].search([('tw_repo_name', '=', rec.name)])
            if modules:
                modules.unlink()
                rec.tw_blacklisted_repo_removed = True
