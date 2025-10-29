{
    'name': 'Linamar Statistical Process Control System',
    'version': '18.0.1.0',
    'category': 'Custom',
    'summary': 'Linamar Statistical Process Control System Module',
    'description': """""",
    'author': 'ASD',
    'price': 0,
    'license': 'LGPL-3',
    'sequence': 1,
    'currency': "INR",
    'depends': ['mail', 'product'],
    'external_dependencies': {'python': ['matplotlib', 'numpy'],
                              },

    'data': [
        'security/spc_groups.xml',
        'security/ir.model.access.csv',
        'data/spc_sequence.xml',
        'data/control_chart_constants_data.xml',
        'data/mail_template.xml',
        'views/statistical_process_control_view.xml',
        'views/spc_chart_view.xml',
        'views/download_spc_chart.xml',
        # 'views\spc_report.xml'
        
    ],
    
    
    'installable': True,
    'auto_install': False,
    'application': True,
}
