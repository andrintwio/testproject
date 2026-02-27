{
    'name': 'TW Module Catalog',
    'version': '19.0.0.0.0',
    'summary': 'GitHub-integrated Odoo module catalog with automated sync, similarity detection, and team usage tracking.',
    'license': 'OPL-1',
    'author': 'twio.tech AG',
    'website': 'https://www.twio.tech',
    'category': 'Tools, Infrastructure, GitHub',
    'depends': [
        'tw_infrastructure',
        'tw_odoo_sh_monitoring',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/module_catalog_views.xml',
        'views/github_blacklist_views.xml',
        'views/github_repo.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
        'data/ir_cron.xml',
    ],
    'installable': True,
    'application': True,

    'external_dependencies': {
        'python': ['PyGithub', 'markdown'],
    },
}