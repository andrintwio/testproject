from odoo import models, fields, api

class TWModuleDependencyTag(models.Model):
    _name = 'tw.module.dependency.tag'
    _description = 'Module Dependency Tag'
    
    name = fields.Char(string="Name", required=True)
    color = fields.Integer(string="Color") # For random tag colors

    @api.model
    def get_or_create_tags(self, depends_list):
        if not depends_list:
            return []

        clean_names = {str(n).strip() for n in depends_list if str(n).strip()}
        
        tag_ids = []
        for name in clean_names:
            tag = self.search([('name', '=', name)], limit=1)
            if not tag:
                tag = self.create({
                    'name': name,
                    'color': (len(name) % 11) + 1
                })
            tag_ids.append(tag.id)
            
        return tag_ids
