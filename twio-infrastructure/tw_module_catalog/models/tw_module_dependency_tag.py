from odoo import models, fields

class TWModuleDependencyTag(models.Model):
    _name = 'tw.module.dependency.tag'
    _description = 'Module Dependency Tag'
    
    name = fields.Char(string="Name", required=True)
    color = fields.Integer(string="Color") # For random tag colors