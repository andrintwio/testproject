{
    'name': 'PDF Customizations',
    'summary': '''
    Surface level changes to the PDF & Conditional Requests based on Locations for Invoices
    ''',
    'description': '''
    This module provides customizations for PDF generation and conditional requests based on locations for invoices.
    ''',
    'author': 'twio.tech AG',
    'website': 'https://www.twio.tech',
    'license': 'OPL-1',
    'version': '19.0.1.0.0',
    'depends': [
        'l10n_din5008_sale',
        'l10n_din5008_stock',
        'sale',
        'stock_account',
        'stock_delivery',
    ],
    'data': [
        'report/din5008_report.xml',
        'report/din5008_report_invoice.xml',
        'report/din5008_sale_templates.xml',
        'report/din5008_stock_picking_layout.xml',
        'report/din5008_stock_templates.xml',
        'report/ir_actions_report_templates.xml',
        'report/report_deliveryslip.xml',
        'report/report_invoice.xml',
        'views/account_move_views.xml',
        'views/delivery_view.xml',
        'views/product_template_view.xml',
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
    ],
}