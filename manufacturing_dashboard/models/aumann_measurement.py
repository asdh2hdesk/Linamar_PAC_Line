# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AumannMeasurement(models.Model):
    _name = 'manufacturing.aumann.measurement'
    _description = 'Aumann Measurement System Data'
    _order = 'test_date desc'
    _rec_name = 'serial_number'

    serial_number = fields.Char('Serial Number', required=True, index=True)
    machine_id = fields.Many2one('manufacturing.machine.config', 'Machine', required=True)
    test_date = fields.Datetime('Test Date', default=fields.Datetime.now, required=True)

    # Part information
    part_form = fields.Char('Part Form', default='Exhaust CAMSHAFT')
    product_id = fields.Char('Product ID', default='Q50-11502-0056810')
    assembly = fields.Char('Assembly', default='MSA')

    # Measurement summary
    total_measurements = fields.Integer('Total Measurements')
    measurements_passed = fields.Integer('Measurements Passed')
    measurements_failed = fields.Integer('Measurements Failed', compute='_compute_measurements_failed', store=True)
    pass_rate = fields.Float('Pass Rate %', compute='_compute_pass_rate', store=True)

    # Key measurements from your Aumann data
    diameter_journal_a1 = fields.Float('Diameter Journal A1 (mm)', digits=(10, 4))
    diameter_journal_a2 = fields.Float('Diameter Journal A2 (mm)', digits=(10, 4))
    diameter_journal_a3 = fields.Float('Diameter Journal A3 (mm)', digits=(10, 4))
    diameter_journal_b1 = fields.Float('Diameter Journal B1 (mm)', digits=(10, 4))
    diameter_journal_b2 = fields.Float('Diameter Journal B2 (mm)', digits=(10, 4))

    # Roundness measurements
    roundness_journal_a1 = fields.Float('Roundness Journal A1 (mm)', digits=(10, 6))
    roundness_journal_a2 = fields.Float('Roundness Journal A2 (mm)', digits=(10, 6))
    roundness_journal_a3 = fields.Float('Roundness Journal A3 (mm)', digits=(10, 6))

    # Base circle measurements
    base_circle_radius_e11 = fields.Float('Base Circle Radius E11 (mm)', digits=(10, 4))
    base_circle_radius_e12 = fields.Float('Base Circle Radius E12 (mm)', digits=(10, 4))
    base_circle_radius_e21 = fields.Float('Base Circle Radius E21 (mm)', digits=(10, 4))

    # Cam lobe measurements
    lobe_width_e11 = fields.Float('Lobe Width E11 (mm)', digits=(10, 4))
    lobe_width_e12 = fields.Float('Lobe Width E12 (mm)', digits=(10, 4))
    lobe_width_e21 = fields.Float('Lobe Width E21 (mm)', digits=(10, 4))

    # Angle measurements
    angle_lobe_e11 = fields.Float('Angle Lobe E11 (deg)', digits=(10, 4))
    angle_lobe_e12 = fields.Float('Angle Lobe E12 (deg)', digits=(10, 4))
    angle_lobe_e21 = fields.Float('Angle Lobe E21 (deg)', digits=(10, 4))

    # Trigger wheel measurements
    trigger_wheel_diameter = fields.Float('Trigger Wheel Diameter (mm)', digits=(10, 4))
    trigger_wheel_width = fields.Float('Trigger Wheel Width (mm)', digits=(10, 4))

    # Two flat measurements
    two_flat_size = fields.Float('Two Flat Size (mm)', digits=(10, 4))
    two_flat_symmetry = fields.Float('Two Flat Symmetry (mm)', digits=(10, 6))

    result = fields.Selection([
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], string='Result', required=True)

    rejection_reason = fields.Text('Rejection Reason')
    raw_data = fields.Text('Raw Data')

    # Quality indicators
    critical_measurements_ok = fields.Boolean('Critical Measurements OK', compute='_compute_critical_measurements')
    dimensional_accuracy = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('acceptable', 'Acceptable'),
        ('poor', 'Poor')
    ], compute='_compute_dimensional_accuracy', string='Dimensional Accuracy')

    @api.depends('total_measurements', 'measurements_passed')
    def _compute_measurements_failed(self):
        for record in self:
            record.measurements_failed = record.total_measurements - record.measurements_passed

    @api.depends('total_measurements', 'measurements_passed')
    def _compute_pass_rate(self):
        for record in self:
            if record.total_measurements > 0:
                record.pass_rate = (record.measurements_passed / record.total_measurements) * 100
            else:
                record.pass_rate = 0.0

    @api.depends('diameter_journal_a1', 'diameter_journal_a2', 'diameter_journal_a3',
                 'diameter_journal_b1', 'diameter_journal_b2', 'roundness_journal_a1',
                 'roundness_journal_a2', 'roundness_journal_a3')
    def _compute_critical_measurements(self):
        for record in self:
            # Define tolerance ranges for critical measurements
            tolerances = {
                'diameter_journal_a1': (23.959, 23.980),
                'diameter_journal_a2': (23.959, 23.980),
                'diameter_journal_a3': (23.959, 23.980),
                'diameter_journal_b1': (28.959, 28.980),
                'diameter_journal_b2': (28.959, 28.980),
            }

            critical_ok = True
            for field, (min_val, max_val) in tolerances.items():
                value = getattr(record, field, 0)
                if value and not (min_val <= value <= max_val):
                    critical_ok = False
                    break

            record.critical_measurements_ok = critical_ok

    @api.depends('pass_rate')
    def _compute_dimensional_accuracy(self):
        for record in self:
            if record.pass_rate >= 98:
                record.dimensional_accuracy = 'excellent'
            elif record.pass_rate >= 95:
                record.dimensional_accuracy = 'good'
            elif record.pass_rate >= 90:
                record.dimensional_accuracy = 'acceptable'
            else:
                record.dimensional_accuracy = 'poor'

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

        part_quality.aumann_result = record.result