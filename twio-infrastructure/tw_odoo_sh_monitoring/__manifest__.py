{
    'name': 'Odoo.sh Monitoring',
    'version': '19.0.1.0.10',
    'category': 'Tools',
    'summary': 'Monitor Odoo.sh repositories and branches',
    'description': """
        This module monitors Odoo.sh repositories and branches.
        It includes:
        - Hourly cron job to fetch repository and branch data
        - Knowledge page to display repositories and branches with dropdowns
    """,
    'author': 'twio.tech AG',
    'website': 'https://www.twio.tech',
    'license': 'OPL-1',
    'depends': [
        'base',
        'knowledge',
        'tw_infrastructure',
        'project',
        'hr',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/tw_odoo_sh_github_device_verification_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
        'views/hr_employee_views.xml',
        'views/tw_odoo_sh_repository_views.xml',
        'views/tw_odoo_sh_repository_user_views.xml',
        'views/tw_odoo_sh_branch_views.xml',
        'views/menu_views.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
