# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AumannMeasurement(models.Model):
    _name = 'manufacturing.aumann.measurement'
    _description = 'Aumann Measurement System Data'
    _order = 'test_date desc'
    _rec_name = 'serial_number'

    serial_number = fields.Char('Serial Number', required=True, index=True)
    machine_id = fields.Many2one('manufacturing.machine.config', 'Machine', required=True)
    test_date = fields.Datetime('Test Date', default=fields.Datetime.now, required=True)

    # Part information
    part_type = fields.Char('Type')
    part_form = fields.Char('Part Form', default='Exhaust CAMSHAFT')
    product_id = fields.Char('Product ID', default='Q50-11502-0056810')
    assembly = fields.Char('Assembly', default='MSA')

    # Measurement summary
    total_measurements = fields.Integer('Total Measurements')
    measurements_passed = fields.Integer('Measurements Passed')
    measurements_failed = fields.Integer('Measurements Failed', compute='_compute_measurements_failed', store=True)
    pass_rate = fields.Float('Pass Rate %', compute='_compute_pass_rate', store=True)

    # Wheel Angle Measurements
    wheel_angle_left_120 = fields.Float('Wheel Angle Left 120 (deg)', digits=(10, 6))
    wheel_angle_left_150 = fields.Float('Wheel Angle Left 150 (deg)', digits=(10, 6))
    wheel_angle_left_180 = fields.Float('Wheel Angle Left 180 (deg)', digits=(10, 6))
    wheel_angle_right_120 = fields.Float('Wheel Angle Right 120 (deg)', digits=(10, 6))
    wheel_angle_right_150 = fields.Float('Wheel Angle Right 150 (deg)', digits=(10, 6))
    wheel_angle_to_reference = fields.Float('Wheel Angle to Reference (deg)', digits=(10, 6))

    # Angle Lobe Measurements
    angle_lobe_e11_to_ref = fields.Float('Angle Lobe E11 to Ref (deg)', digits=(10, 6))
    angle_lobe_e12_to_ref = fields.Float('Angle Lobe E12 to Ref (deg)', digits=(10, 6))
    angle_lobe_e21_to_ref = fields.Float('Angle Lobe E21 to Ref (deg)', digits=(10, 6))
    angle_lobe_e22_to_ref = fields.Float('Angle Lobe E22 to Ref (deg)', digits=(10, 6))
    angle_lobe_e31_to_ref = fields.Float('Angle Lobe E31 to Ref (deg)', digits=(10, 6))
    angle_lobe_e32_to_ref = fields.Float('Angle Lobe E32 to Ref (deg)', digits=(10, 6))

    # Base Circle Radius Measurements
    base_circle_radius_lobe_e11 = fields.Float('Base Circle Radius Lobe E11 (mm)', digits=(10, 6))
    base_circle_radius_lobe_e12 = fields.Float('Base Circle Radius Lobe E12 (mm)', digits=(10, 6))
    base_circle_radius_lobe_e21 = fields.Float('Base Circle Radius Lobe E21 (mm)', digits=(10, 6))
    base_circle_radius_lobe_e22 = fields.Float('Base Circle Radius Lobe E22 (mm)', digits=(10, 6))
    base_circle_radius_lobe_e31 = fields.Float('Base Circle Radius Lobe E31 (mm)', digits=(10, 6))
    base_circle_radius_lobe_e32 = fields.Float('Base Circle Radius Lobe E32 (mm)', digits=(10, 6))

    # Base Circle Runout Measurements
    base_circle_runout_lobe_e11_adj = fields.Float('Base Circle Runout Lobe E11 adj (mm)', digits=(10, 6))
    base_circle_runout_lobe_e12_adj = fields.Float('Base Circle Runout Lobe E12 adj (mm)', digits=(10, 6))
    base_circle_runout_lobe_e21_adj = fields.Float('Base Circle Runout Lobe E21 adj (mm)', digits=(10, 6))
    base_circle_runout_lobe_e22_adj = fields.Float('Base Circle Runout Lobe E22 adj (mm)', digits=(10, 6))
    base_circle_runout_lobe_e31_adj = fields.Float('Base Circle Runout Lobe E31 adj (mm)', digits=(10, 6))
    base_circle_runout_lobe_e32_adj = fields.Float('Base Circle Runout Lobe E32 adj (mm)', digits=(10, 6))

    # Bearing and Width Measurements
    bearing_width = fields.Float('Bearing Width (mm)', digits=(10, 6))
    cam_angle12 = fields.Float('Cam Angle12 (deg)', digits=(10, 6))
    cam_angle34 = fields.Float('Cam Angle34 (deg)', digits=(10, 6))
    cam_angle56 = fields.Float('Cam Angle56 (deg)', digits=(10, 6))

    # Concentricity Measurements
    concentricity_front_bearing_h = fields.Float('Concentricity Front Bearing H (mm)', digits=(10, 6))
    concentricity_io_front_end_dia_39 = fields.Float('Concentricity IO Front End Dia 39 (mm)', digits=(10, 6))
    concentricity_io_front_end_major_dia_40 = fields.Float('Concentricity IO Front End Major Dia 40 (mm)', digits=(10, 6))
    concentricity_io_step_diameter_32_5 = fields.Float('Concentricity IO Step Diameter 32.5 (mm)', digits=(10, 6))

    # Concentricity Results
    concentricity_result_front_end_dia_39 = fields.Float('Concentricity Result Front End Dia 39 (mm)', digits=(10, 6))
    concentricity_result_front_end_major_dia_40 = fields.Float('Concentricity Result Front End Major Dia 40 (mm)', digits=(10, 6))
    concentricity_result_step_diameter_32_5 = fields.Float('Concentricity Result Step Diameter 32.5 (mm)', digits=(10, 6))

    # Diameter Measurements
    diameter_front_bearing_h = fields.Float('Diameter Front Bearing H (mm)', digits=(10, 6))
    diameter_front_end = fields.Float('Diameter Front End (mm)', digits=(10, 6))
    diameter_front_end_major = fields.Float('Diameter Front End Major (mm)', digits=(10, 6))
    diameter_journal_a1 = fields.Float('Diameter Journal A1 (mm)', digits=(10, 6))
    diameter_journal_a2 = fields.Float('Diameter Journal A2 (mm)', digits=(10, 6))
    diameter_journal_a3 = fields.Float('Diameter Journal A3 (mm)', digits=(10, 6))
    diameter_journal_b1 = fields.Float('Diameter Journal B1 (mm)', digits=(10, 6))
    diameter_journal_b2 = fields.Float('Diameter Journal B2 (mm)', digits=(10, 6))
    diameter_step_diameter_tpc = fields.Float('Diameter Step Diameter TPC (mm)', digits=(10, 6))

    # Distance Measurements
    distance_lobe_e11 = fields.Float('Distance Lobe E11 (mm)', digits=(10, 6))
    distance_lobe_e12 = fields.Float('Distance Lobe E12 (mm)', digits=(10, 6))
    distance_lobe_e21 = fields.Float('Distance Lobe E21 (mm)', digits=(10, 6))
    distance_lobe_e22 = fields.Float('Distance Lobe E22 (mm)', digits=(10, 6))
    distance_lobe_e31 = fields.Float('Distance Lobe E31 (mm)', digits=(10, 6))
    distance_lobe_e32 = fields.Float('Distance Lobe E32 (mm)', digits=(10, 6))
    distance_rear_end = fields.Float('Distance Rear End (mm)', digits=(10, 6))
    distance_step_length_front_face = fields.Float('Distance Step Length Front Face (mm)', digits=(10, 6))
    distance_trigger_length = fields.Float('Distance Trigger Length (mm)', digits=(10, 6))
    distance_from_front_end_face = fields.Float('Distance from Front End Face (mm)', digits=(10, 6))

    # Face Measurements
    face_total_runout_bearing_face_0 = fields.Float('Face Total Runout Bearing Face 0 (mm)', digits=(10, 6))
    face_total_runout_bearing_face_25 = fields.Float('Face Total Runout Bearing Face 25 (mm)', digits=(10, 6))
    front_face_flatness_concav = fields.Float('Front Face Flatness Concav (mm)', digits=(10, 6))
    front_face_flatness_convex = fields.Float('Front Face Flatness Convex (mm)', digits=(10, 6))
    front_face_runout = fields.Float('Front Face Runout (mm)', digits=(10, 6))

    # Profile Measurements
    max_profile_30_trigger_wheel_diameter = fields.Float('Max Profile 30 Trigger Wheel Diameter (mm)', digits=(10, 6))
    max_profile_42_trigger_wheel_diameter = fields.Float('Max Profile 42 Trigger Wheel Diameter (mm)', digits=(10, 6))
    min_profile_30_trigger_wheel_diameter = fields.Float('Min Profile 30 Trigger Wheel Diameter (mm)', digits=(10, 6))
    min_profile_42_trigger_wheel_diameter = fields.Float('Min Profile 42 Trigger Wheel Diameter (mm)', digits=(10, 6))

    # Profile Error Measurements (E11)
    profile_error_lobe_e11_zone_1 = fields.Float('Profile Error Lobe E11 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_e11_zone_2 = fields.Float('Profile Error Lobe E11 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_e11_zone_3 = fields.Float('Profile Error Lobe E11 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_e11_zone_4 = fields.Float('Profile Error Lobe E11 Zone 4 (mm)', digits=(10, 6))

    # Profile Error Measurements (E12)
    profile_error_lobe_e12_zone_1 = fields.Float('Profile Error Lobe E12 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_e12_zone_2 = fields.Float('Profile Error Lobe E12 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_e12_zone_3 = fields.Float('Profile Error Lobe E12 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_e12_zone_4 = fields.Float('Profile Error Lobe E12 Zone 4 (mm)', digits=(10, 6))

    # Profile Error Measurements (E21)
    profile_error_lobe_e21_zone_1 = fields.Float('Profile Error Lobe E21 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_e21_zone_2 = fields.Float('Profile Error Lobe E21 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_e21_zone_3 = fields.Float('Profile Error Lobe E21 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_e21_zone_4 = fields.Float('Profile Error Lobe E21 Zone 4 (mm)', digits=(10, 6))

    # Profile Error Measurements (E22)
    profile_error_lobe_e22_zone_1 = fields.Float('Profile Error Lobe E22 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_e22_zone_2 = fields.Float('Profile Error Lobe E22 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_e22_zone_3 = fields.Float('Profile Error Lobe E22 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_e22_zone_4 = fields.Float('Profile Error Lobe E22 Zone 4 (mm)', digits=(10, 6))

    # Profile Error Measurements (E31)
    profile_error_lobe_e31_zone_1 = fields.Float('Profile Error Lobe E31 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_e31_zone_2 = fields.Float('Profile Error Lobe E31 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_e31_zone_3 = fields.Float('Profile Error Lobe E31 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_e31_zone_4 = fields.Float('Profile Error Lobe E31 Zone 4 (mm)', digits=(10, 6))

    # Profile Error Measurements (E32)
    profile_error_lobe_e32_zone_1 = fields.Float('Profile Error Lobe E32 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_e32_zone_2 = fields.Float('Profile Error Lobe E32 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_e32_zone_3 = fields.Float('Profile Error Lobe E32 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_e32_zone_4 = fields.Float('Profile Error Lobe E32 Zone 4 (mm)', digits=(10, 6))

    # Rear End Length
    rear_end_length = fields.Float('Rear End Length (mm)', digits=(10, 6))

    # Roundness Measurements
    roundness_journal_a1 = fields.Float('Roundness Journal A1 (mm)', digits=(10, 6))
    roundness_journal_a2 = fields.Float('Roundness Journal A2 (mm)', digits=(10, 6))
    roundness_journal_a3 = fields.Float('Roundness Journal A3 (mm)', digits=(10, 6))
    roundness_journal_b1 = fields.Float('Roundness Journal B1 (mm)', digits=(10, 6))
    roundness_journal_b2 = fields.Float('Roundness Journal B2 (mm)', digits=(10, 6))

    # Runout Measurements
    runout_journal_a1_a1_b1 = fields.Float('Runout Journal A1 A1-B1 (mm)', digits=(10, 6))
    runout_journal_a2_a1_b1 = fields.Float('Runout Journal A2 A1-B1 (mm)', digits=(10, 6))
    runout_journal_a3_a1_b1 = fields.Float('Runout Journal A3 A1-B1 (mm)', digits=(10, 6))
    runout_journal_b1_a1_a3 = fields.Float('Runout Journal B1 A1-A3 (mm)', digits=(10, 6))
    runout_journal_b2_a1_a3 = fields.Float('Runout Journal B2 A1-A3 (mm)', digits=(10, 6))

    # Temperature Measurements
    temperature_machine = fields.Float('Temperature Machine (°C)', digits=(10, 2))
    temperature_sensor = fields.Float('Temperature Sensor (°C)', digits=(10, 2))

    # Trigger Wheel Measurements
    trigger_wheel_diameter = fields.Float('Trigger Wheel Diameter (mm)', digits=(10, 6))
    trigger_wheel_width = fields.Float('Trigger Wheel Width (mm)', digits=(10, 6))

    # Two Flat Measurements
    two_flat_size = fields.Float('Two Flat Size (mm)', digits=(10, 6))
    two_flat_symmetry = fields.Float('Two Flat Symmetry (mm)', digits=(10, 6))

    # Velocity Error Measurements (E11)
    velocity_error_lobe_e11_zone_1 = fields.Float('Velocity Error Lobe E11 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_e11_zone_2 = fields.Float('Velocity Error Lobe E11 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_e11_zone_3 = fields.Float('Velocity Error Lobe E11 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_e11_zone_4 = fields.Float('Velocity Error Lobe E11 Zone 4 (deg)', digits=(10, 6))

    # Velocity Error Measurements (E12)
    velocity_error_lobe_e12_zone_1 = fields.Float('Velocity Error Lobe E12 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_e12_zone_2 = fields.Float('Velocity Error Lobe E12 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_e12_zone_3 = fields.Float('Velocity Error Lobe E12 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_e12_zone_4 = fields.Float('Velocity Error Lobe E12 Zone 4 (deg)', digits=(10, 6))

    # Velocity Error Measurements (E21)
    velocity_error_lobe_e21_zone_1 = fields.Float('Velocity Error Lobe E21 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_e21_zone_2 = fields.Float('Velocity Error Lobe E21 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_e21_zone_3 = fields.Float('Velocity Error Lobe E21 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_e21_zone_4 = fields.Float('Velocity Error Lobe E21 Zone 4 (deg)', digits=(10, 6))

    # Velocity Error Measurements (E22)
    velocity_error_lobe_e22_zone_1 = fields.Float('Velocity Error Lobe E22 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_e22_zone_2 = fields.Float('Velocity Error Lobe E22 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_e22_zone_3 = fields.Float('Velocity Error Lobe E22 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_e22_zone_4 = fields.Float('Velocity Error Lobe E22 Zone 4 (deg)', digits=(10, 6))

    # Velocity Error Measurements (E31)
    velocity_error_lobe_e31_zone_1 = fields.Float('Velocity Error Lobe E31 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_e31_zone_2 = fields.Float('Velocity Error Lobe E31 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_e31_zone_3 = fields.Float('Velocity Error Lobe E31 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_e31_zone_4 = fields.Float('Velocity Error Lobe E31 Zone 4 (deg)', digits=(10, 6))

    # Velocity Error Measurements (E32)
    velocity_error_lobe_e32_zone_1 = fields.Float('Velocity Error Lobe E32 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_e32_zone_2 = fields.Float('Velocity Error Lobe E32 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_e32_zone_3 = fields.Float('Velocity Error Lobe E32 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_e32_zone_4 = fields.Float('Velocity Error Lobe E32 Zone 4 (deg)', digits=(10, 6))

    # Width Lobe Measurements
    width_lobe_e11 = fields.Float('Width Lobe E11 (mm)', digits=(10, 6))
    width_lobe_e12 = fields.Float('Width Lobe E12 (mm)', digits=(10, 6))
    width_lobe_e21 = fields.Float('Width Lobe E21 (mm)', digits=(10, 6))
    width_lobe_e22 = fields.Float('Width Lobe E22 (mm)', digits=(10, 6))
    width_lobe_e31 = fields.Float('Width Lobe E31 (mm)', digits=(10, 6))
    width_lobe_e32 = fields.Float('Width Lobe E32 (mm)', digits=(10, 6))

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