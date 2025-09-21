# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PartQuality(models.Model):
    _name = 'manufacturing.part.quality'
    _description = 'Part Quality Control'
    _order = 'test_date desc'
    _rec_name = 'serial_number'

    serial_number = fields.Char('Serial Number', required=True, index=True)
    test_date = fields.Datetime('Test Date', default=fields.Datetime.now, index=True)

    # Station results
    vici_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], default='pending', string='VICI Result')

    ruhlamat_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], default='pending', string='Ruhlamat Result')

    aumann_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], default='pending', string='Aumann Result')

    # Final result
    final_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], compute='_compute_final_result', string='Final Result', store=True)

    # Box tracking
    box_number = fields.Char('Box Number')
    box_position = fields.Integer('Position in Box')

    # Quality Engineer Override
    qe_override = fields.Boolean('QE Override')
    qe_comments = fields.Text('QE Comments')


    # Related records
    vici_vision_ids = fields.One2many(
        'manufacturing.vici.vision',
        'serial_number',
        string='VICI Tests'
    )
    ruhlamat_press_ids = fields.One2many(
        'manufacturing.ruhlamat.press',
        'part_quality_id',  # Changed from 'serial_number' to 'part_quality_id'
        string='Ruhlamat Tests'
    )
    aumann_measurement_ids = fields.One2many(
        'manufacturing.aumann.measurement',
        'serial_number',
        string='Aumann Tests'
    )

    @api.depends('vici_result', 'ruhlamat_result', 'aumann_result', 'qe_override')
    def _compute_final_result(self):
        for record in self:
            if record.qe_override:
                # If QE has overridden, keep current final_result
                continue

            results = [record.vici_result, record.ruhlamat_result, record.aumann_result]

            if 'reject' in results:
                record.final_result = 'reject'
            elif all(result == 'pass' for result in results):
                record.final_result = 'pass'
            else:
                record.final_result = 'pending'

    def qe_override_result(self, new_result, comments):
        """Allow Quality Engineer to override the result"""
        self.ensure_one()
        self.write({
            'final_result': new_result,
            'qe_override': True,
            'qe_comments': comments
        })

        # Log the override
        self.message_post(
            body=f"QE Override: Result changed to {new_result}. Comments: {comments}",
            message_type='notification'
        )