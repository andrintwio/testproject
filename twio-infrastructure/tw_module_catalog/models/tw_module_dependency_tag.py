from odoo import models, fields

class TWModuleDependencyTag(models.Model):
    _name = 'tw.module.dependency.tag'
    _description = 'Module Dependency Tag'
    
    name = fields.Char(string="Name", required=True)
    color = fields.Integer(string="Color") # For random tag colors

    @api.model
    def get_or_create_tags(self, depends_list):
        """Standardizes and retrieves tag IDs, creating missing ones."""
        if not depends_list:
            return []
            
        tag_ids = []
        for name in depends_list:
            name = str(name).strip()
            if not name:
                continue
                
            # Odoo optimization: search for existing tag
            tag = self.search([('name', '=', name)], limit=1)
            if not tag:
                tag = self.create({
                    'name': name,
                    'color': (len(name) % 11) + 1
                })
            tag_ids.append(tag.id)
            
        return tag_ids
        