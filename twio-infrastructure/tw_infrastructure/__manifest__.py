# -*- coding: utf-8 -*-
{
    'name': "tw_infrastructure",
    'author': "twio.tech AG",
    'summary': 'Base module for tracking development infrastructure',
    'website': "https://www.twio.tech",
    'version': '19.0.1.0.0',
    'license': 'OPL-1',
    'depends': [
        'base'
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/menu_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'application': True,
}
