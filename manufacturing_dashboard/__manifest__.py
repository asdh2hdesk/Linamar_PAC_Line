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
    'external_dependencies': {
        'python': ['barcode', 'Pillow'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/final_station_data.xml',
        'views/part_quality_views.xml',
        'views/machine_config_views.xml',
        'views/vici_vision_views.xml',
        'views/ruhlamat_press_views.xml',
        'views/aumann_measurement_views.xml',
        'views/gauging_measurement_views.xml',
        'views/final_station_measurement_views.xml',
        'views/box_management_views.xml',
        'views/qe_override_wizard_views.xml',
        'views/dashboard_views.xml',
        'views/menu_views.xml',
        'data/cron_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Chart.js library - using unpkg CDN
            'https://unpkg.com/chart.js@4.4.0/dist/chart.min.js',
            # Dashboard assets
            'manufacturing_dashboard/static/src/css/dashboard.css',
            'manufacturing_dashboard/static/src/js/dashboard.js',
            'manufacturing_dashboard/static/src/xml/dashboard.xml',
            # Final Station Dashboard assets
            'manufacturing_dashboard/static/src/css/final_station_dashboard.css',
            'manufacturing_dashboard/static/src/js/final_station_dashboard.js',
            'manufacturing_dashboard/static/src/xml/final_station_dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3', 
}