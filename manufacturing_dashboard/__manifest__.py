# -*- coding: utf-8 -*-
{
    'name': 'PSA Line Dashboard',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Real-time Manufacturing Quality Control Dashboard',
    'description': """
Manufacturing Quality Control Dashboard
======================================

Multi-station manufacturing quality control system with real-time data monitoring:

Features:
* VICI Vision System Integration
* Ruhlamat Press System Integration  
* Aumann Measurement System Integration
* Real-time CSV data processing
* Combined dashboard with live monitoring
* Quality control tracking and reporting
* Box management (540 parts per box)
* Quality Engineer override capabilities
* Predictive maintenance alerts
* Comprehensive reporting
    """,
    'author': 'ASD Rakesh',
    'website': 'https://www.yourcompany.com',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/part_quality_views.xml',
        'views/machine_config_views.xml',
        'views/vici_vision_views.xml',
        'views/ruhlamat_press_views.xml',
        'views/aumann_measurement_views.xml',
        'views/dashboard_views.xml',
        'views/menu_views.xml',
        'data/cron_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Chart.js library
            'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.min.js',
            # Dashboard assets
            'manufacturing_dashboard/static/src/css/dashboard.css',
            'manufacturing_dashboard/static/src/js/dashboard.js',
            'manufacturing_dashboard/static/src/xml/dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}