# -*- coding: utf-8 -*-

from odoo import models, fields, api


class RuhlamatPress(models.Model):
    _name = 'manufacturing.ruhlamat.press'
    _description = 'Ruhlamat Press System Data'
    _order = 'test_date desc'
    _rec_name = 'serial_number'

    serial_number = fields.Char('Serial Number', required=True, index=True)
    machine_id = fields.Many2one('manufacturing.machine.config', 'Machine', required=True)
    test_date = fields.Datetime('Test Date', default=fields.Datetime.now, required=True)

    # Press measurements
    press_force = fields.Float('Press Force (N)', digits=(10, 2))
    press_distance = fields.Float('Press Distance (mm)', digits=(10, 4))
    press_duration = fields.Float('Press Duration (seconds)', digits=(10, 2))

    # Tolerance limits
    force_min = fields.Float('Min Force Tolerance', default=1000.0)
    force_max = fields.Float('Max Force Tolerance', default=2000.0)
    distance_min = fields.Float('Min Distance Tolerance', default=10.0)
    distance_max = fields.Float('Max Distance Tolerance', default=20.0)

    # Test results
    press_test_ok = fields.Boolean('Press Test OK')
    crack_test_result = fields.Boolean('Crack Test OK')
    mpi_test_result = fields.Boolean('MPI Test OK')

    result = fields.Selection([
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], string='Result', required=True)

    rejection_reason = fields.Text('Rejection Reason')
    raw_data = fields.Text('Raw Data')

    # Computed fields
    press_within_tolerance = fields.Boolean('Press Within Tolerance', compute='_compute_press_tolerance')
    overall_test_ok = fields.Boolean('Overall Test OK', compute='_compute_overall_test')

    @api.depends('press_force', 'press_distance', 'force_min', 'force_max', 'distance_min', 'distance_max')
    def _compute_press_tolerance(self):
        for record in self:
            force_ok = record.force_min <= record.press_force <= record.force_max if record.press_force else False
            distance_ok = record.distance_min <= record.press_distance <= record.distance_max if record.press_distance else False
            record.press_within_tolerance = force_ok and distance_ok

    @api.depends('press_test_ok', 'crack_test_result', 'mpi_test_result')
    def _compute_overall_test(self):
        for record in self:
            record.overall_test_ok = record.press_test_ok and record.crack_test_result and record.mpi_test_result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            # Update or create part quality record
            self._update_part_quality(record)
        return records

    def _update_part_quality(self, record):
        """Update the corresponding part quality record"""
        part_quality = self.env['manufacturing.part.quality'].search([
            ('serial_number', '=', record.serial_number)
        ], limit=1)

        if not part_quality:
            part_quality = self.env['manufacturing.part.quality'].create({
                'serial_number': record.serial_number,
                'test_date': record.test_date,
            })

        part_quality.ruhlamat_result = record.result