# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
import json
import pytz

_logger = logging.getLogger(__name__)
from odoo.exceptions import UserError


class AumannMeasurement(models.Model):
    _name = 'manufacturing.aumann.measurement'
    _description = 'Aumann Measurement System Data'
    _order = 'test_date desc'
    _rec_name = 'serial_number'

    @api.model
    def get_ist_now(self):
        """Get current IST datetime for consistent timezone handling"""
        try:
            ist = pytz.timezone('Asia/Kolkata')
            utc_now = fields.Datetime.now()
            # Convert UTC to IST
            ist_now = pytz.UTC.localize(utc_now).astimezone(ist)
            # Return as naive datetime in IST (Odoo will handle display)
            return ist_now.replace(tzinfo=None)
        except Exception as e:
            _logger.warning(f"Error getting IST time: {e}, falling back to UTC")
            return fields.Datetime.now()

    serial_number = fields.Char('Serial Number', required=True, index=True)
    machine_id = fields.Many2one('manufacturing.machine.config', 'Machine', required=True)
    test_date = fields.Datetime('Test Date', required=True)

    # Part information
    part_type = fields.Char('Type')
    part_form = fields.Selection([
        ('intake', 'Intake CAMSHAFT'),
        ('exhaust', 'Exhaust CAMSHAFT')
    ], string='Part Form', default='exhaust', required=True)
    product_id = fields.Char('Product ID', default='Q50-11502-0056810')
    assembly = fields.Char('Assembly', default='MSA')

    # Camshaft type determines which lobe fields are used
    camshaft_type = fields.Selection([
        ('intake', 'Intake (A-Lobes with Pump)'),
        ('exhaust', 'Exhaust (E-Lobes)')
    ], string='Camshaft Type', compute='_compute_camshaft_type', store=True)

    # Measurement summary
    total_measurements = fields.Integer('Total Measurements')
    measurements_passed = fields.Integer('Measurements Passed')
    measurements_failed = fields.Integer('Measurements Failed', compute='_compute_measurements_failed', store=True)
    pass_rate = fields.Float('Pass Rate %', compute='_compute_pass_rate', store=True)

    # Wheel Angle Measurements
    wheel_angle_left_120 = fields.Float('Wheel Angle Left 120 (deg)', digits=(10, 6))
    wheel_angle_left_150 = fields.Float('Wheel Angle Left 150 (deg)', digits=(10, 6))
    wheel_angle_left_180 = fields.Float('Wheel Angle Left 180 (deg)', digits=(10, 6))
    wheel_angle_left_30 = fields.Float('Wheel Angle Left 30 (deg)', digits=(10, 6))
    wheel_angle_right_120 = fields.Float('Wheel Angle Right 120 (deg)', digits=(10, 6))
    wheel_angle_right_150 = fields.Float('Wheel Angle Right 150 (deg)', digits=(10, 6))
    wheel_angle_right_90 = fields.Float('Wheel Angle Right 90 (deg)', digits=(10, 6))
    wheel_angle_right_60 = fields.Float('Wheel Angle Right 60 (deg)', digits=(10, 6))
    wheel_angle_right_30 = fields.Float('Wheel Angle Right 30 (deg)', digits=(10, 6))
    wheel_angle_to_reference = fields.Float('Wheel Angle to Reference (deg)', digits=(10, 6))

    # Universal Lobe Angle Measurements (used for both A and E lobes)
    angle_lobe_11_to_ref = fields.Float('Angle Lobe 11 to Ref (deg)', digits=(10, 6))
    angle_lobe_12_to_ref = fields.Float('Angle Lobe 12 to Ref (deg)', digits=(10, 6))
    angle_lobe_21_to_ref = fields.Float('Angle Lobe 21 to Ref (deg)', digits=(10, 6))
    angle_lobe_22_to_ref = fields.Float('Angle Lobe 22 to Ref (deg)', digits=(10, 6))
    angle_lobe_31_to_ref = fields.Float('Angle Lobe 31 to Ref (deg)', digits=(10, 6))
    angle_lobe_32_to_ref = fields.Float('Angle Lobe 32 to Ref (deg)', digits=(10, 6))

    # Pump Lobe - Intake only
    angle_pumplobe_to_ref = fields.Float('Angle Pump Lobe to Ref (deg)', digits=(10, 6))

    # Universal Base Circle Radius Measurements
    base_circle_radius_lobe_11 = fields.Float('Base Circle Radius Lobe 11 (mm)', digits=(10, 6))
    base_circle_radius_lobe_12 = fields.Float('Base Circle Radius Lobe 12 (mm)', digits=(10, 6))
    base_circle_radius_lobe_21 = fields.Float('Base Circle Radius Lobe 21 (mm)', digits=(10, 6))
    base_circle_radius_lobe_22 = fields.Float('Base Circle Radius Lobe 22 (mm)', digits=(10, 6))
    base_circle_radius_lobe_31 = fields.Float('Base Circle Radius Lobe 31 (mm)', digits=(10, 6))
    base_circle_radius_lobe_32 = fields.Float('Base Circle Radius Lobe 32 (mm)', digits=(10, 6))
    base_circle_radius_pump_lobe = fields.Float('Base Circle Radius Pump Lobe (mm)', digits=(10, 6))

    # Universal Base Circle Runout Measurements
    base_circle_runout_lobe_11_adj = fields.Float('Base Circle Runout Lobe 11 adj (mm)', digits=(10, 6))
    base_circle_runout_lobe_12_adj = fields.Float('Base Circle Runout Lobe 12 adj (mm)', digits=(10, 6))
    base_circle_runout_lobe_21_adj = fields.Float('Base Circle Runout Lobe 21 adj (mm)', digits=(10, 6))
    base_circle_runout_lobe_22_adj = fields.Float('Base Circle Runout Lobe 22 adj (mm)', digits=(10, 6))
    base_circle_runout_lobe_31_adj = fields.Float('Base Circle Runout Lobe 31 adj (mm)', digits=(10, 6))
    base_circle_runout_lobe_32_adj = fields.Float('Base Circle Runout Lobe 32 adj (mm)', digits=(10, 6))

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

    # Universal Distance Measurements
    distance_lobe_11 = fields.Float('Distance Lobe 11 (mm)', digits=(10, 6))
    distance_lobe_12 = fields.Float('Distance Lobe 12 (mm)', digits=(10, 6))
    distance_lobe_21 = fields.Float('Distance Lobe 21 (mm)', digits=(10, 6))
    distance_lobe_22 = fields.Float('Distance Lobe 22 (mm)', digits=(10, 6))
    distance_lobe_31 = fields.Float('Distance Lobe 31 (mm)', digits=(10, 6))
    distance_lobe_32 = fields.Float('Distance Lobe 32 (mm)', digits=(10, 6))
    distance_pump_lobe = fields.Float('Distance Pump Lobe (mm)', digits=(10, 6))
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

    # Universal Profile Error Measurements (Lobe 11)
    profile_error_lobe_11_zone_1 = fields.Float('Profile Error Lobe 11 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_11_zone_2 = fields.Float('Profile Error Lobe 11 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_11_zone_3 = fields.Float('Profile Error Lobe 11 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_11_zone_4 = fields.Float('Profile Error Lobe 11 Zone 4 (mm)', digits=(10, 6))

    # Universal Profile Error Measurements (Lobe 12)
    profile_error_lobe_12_zone_1 = fields.Float('Profile Error Lobe 12 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_12_zone_2 = fields.Float('Profile Error Lobe 12 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_12_zone_3 = fields.Float('Profile Error Lobe 12 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_12_zone_4 = fields.Float('Profile Error Lobe 12 Zone 4 (mm)', digits=(10, 6))

    # Universal Profile Error Measurements (Lobe 21)
    profile_error_lobe_21_zone_1 = fields.Float('Profile Error Lobe 21 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_21_zone_2 = fields.Float('Profile Error Lobe 21 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_21_zone_3 = fields.Float('Profile Error Lobe 21 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_21_zone_4 = fields.Float('Profile Error Lobe 21 Zone 4 (mm)', digits=(10, 6))

    # Universal Profile Error Measurements (Lobe 22)
    profile_error_lobe_22_zone_1 = fields.Float('Profile Error Lobe 22 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_22_zone_2 = fields.Float('Profile Error Lobe 22 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_22_zone_3 = fields.Float('Profile Error Lobe 22 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_22_zone_4 = fields.Float('Profile Error Lobe 22 Zone 4 (mm)', digits=(10, 6))

    # Universal Profile Error Measurements (Lobe 31)
    profile_error_lobe_31_zone_1 = fields.Float('Profile Error Lobe 31 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_31_zone_2 = fields.Float('Profile Error Lobe 31 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_31_zone_3 = fields.Float('Profile Error Lobe 31 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_31_zone_4 = fields.Float('Profile Error Lobe 31 Zone 4 (mm)', digits=(10, 6))

    # Universal Profile Error Measurements (Lobe 32)
    profile_error_lobe_32_zone_1 = fields.Float('Profile Error Lobe 32 Zone 1 (mm)', digits=(10, 6))
    profile_error_lobe_32_zone_2 = fields.Float('Profile Error Lobe 32 Zone 2 (mm)', digits=(10, 6))
    profile_error_lobe_32_zone_3 = fields.Float('Profile Error Lobe 32 Zone 3 (mm)', digits=(10, 6))
    profile_error_lobe_32_zone_4 = fields.Float('Profile Error Lobe 32 Zone 4 (mm)', digits=(10, 6))

    # Profile Error Measurements (Pump Lobe)
    profile_error_pumplobe_rising_side = fields.Float('Profile Error Pump Lobe Rising Side (mm)', digits=(10, 6))
    profile_error_pumplobe_closing_side = fields.Float('Profile Error Pump Lobe Closing Side (mm)', digits=(10, 6))
    profile_error_pumplobe_rising_side_hide= fields.Float('Profile Error Pump Lobe Rising Side (mm)', digits=(10, 6))
    profile_error_pumplobe_closing_side_hide = fields.Float('Profile Error Pump Lobe Closing Side (mm)', digits=(10, 6))

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

    # Universal Velocity Error Measurements (Lobe 11)
    velocity_error_lobe_11_zone_1 = fields.Float('Velocity Error Lobe 11 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_11_zone_2 = fields.Float('Velocity Error Lobe 11 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_11_zone_3 = fields.Float('Velocity Error Lobe 11 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_11_zone_4 = fields.Float('Velocity Error Lobe 11 Zone 4 (deg)', digits=(10, 6))

    # Universal Velocity Error Measurements (Lobe 12)
    velocity_error_lobe_12_zone_1 = fields.Float('Velocity Error Lobe 12 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_12_zone_2 = fields.Float('Velocity Error Lobe 12 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_12_zone_3 = fields.Float('Velocity Error Lobe 12 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_12_zone_4 = fields.Float('Velocity Error Lobe 12 Zone 4 (deg)', digits=(10, 6))

    # Universal Velocity Error Measurements (Lobe 21)
    velocity_error_lobe_21_zone_1 = fields.Float('Velocity Error Lobe 21 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_21_zone_2 = fields.Float('Velocity Error Lobe 21 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_21_zone_3 = fields.Float('Velocity Error Lobe 21 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_21_zone_4 = fields.Float('Velocity Error Lobe 21 Zone 4 (deg)', digits=(10, 6))

    # Universal Velocity Error Measurements (Lobe 22)
    velocity_error_lobe_22_zone_1 = fields.Float('Velocity Error Lobe 22 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_22_zone_2 = fields.Float('Velocity Error Lobe 22 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_22_zone_3 = fields.Float('Velocity Error Lobe 22 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_22_zone_4 = fields.Float('Velocity Error Lobe 22 Zone 4 (deg)', digits=(10, 6))

    # Universal Velocity Error Measurements (Lobe 31)
    velocity_error_lobe_31_zone_1 = fields.Float('Velocity Error Lobe 31 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_31_zone_2 = fields.Float('Velocity Error Lobe 31 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_31_zone_3 = fields.Float('Velocity Error Lobe 31 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_31_zone_4 = fields.Float('Velocity Error Lobe 31 Zone 4 (deg)', digits=(10, 6))

    # Universal Velocity Error Measurements (Lobe 32)
    velocity_error_lobe_32_zone_1 = fields.Float('Velocity Error Lobe 32 Zone 1 (deg)', digits=(10, 6))
    velocity_error_lobe_32_zone_2 = fields.Float('Velocity Error Lobe 32 Zone 2 (deg)', digits=(10, 6))
    velocity_error_lobe_32_zone_3 = fields.Float('Velocity Error Lobe 32 Zone 3 (deg)', digits=(10, 6))
    velocity_error_lobe_32_zone_4 = fields.Float('Velocity Error Lobe 32 Zone 4 (deg)', digits=(10, 6))

    # Velocity Error Measurements (Pump Lobe)
    velocity_error_pumplobe_1_deg_rising_side = fields.Float('Velocity Error Pump Lobe 1° Rising Side (deg)', digits=(10, 6))
    velocity_error_pumplobe_1_deg_closing_side = fields.Float('Velocity Error Pump Lobe 1° Closing Side (deg)', digits=(10, 6))

    # Universal Width Lobe Measurements
    width_lobe_11 = fields.Float('Width Lobe 11 (mm)', digits=(10, 6))
    width_lobe_12 = fields.Float('Width Lobe 12 (mm)', digits=(10, 6))
    width_lobe_21 = fields.Float('Width Lobe 21 (mm)', digits=(10, 6))
    width_lobe_22 = fields.Float('Width Lobe 22 (mm)', digits=(10, 6))
    width_lobe_31 = fields.Float('Width Lobe 31 (mm)', digits=(10, 6))
    width_lobe_32 = fields.Float('Width Lobe 32 (mm)', digits=(10, 6))
    width_pump_lobe = fields.Float('Width Pump Lobe (mm)', digits=(10, 6))

    # Straightness Journal Measurements
    straightness_journal_a1 = fields.Float('Straightness Journal A1 (mm)', digits=(10, 6))
    straightness_journal_a2 = fields.Float('Straightness Journal A2 (mm)', digits=(10, 6))
    straightness_journal_a3 = fields.Float('Straightness Journal A3 (mm)', digits=(10, 6))
    straightness_journal_b1 = fields.Float('Straightness Journal B1 (mm)', digits=(10, 6))
    straightness_journal_b2 = fields.Float('Straightness Journal B2 (mm)', digits=(10, 6))

    # Universal Straightness Lobe Measurements
    straightness_lobe_11 = fields.Float('Straightness Lobe 11 (mm)', digits=(10, 6))
    straightness_lobe_12 = fields.Float('Straightness Lobe 12 (mm)', digits=(10, 6))
    straightness_lobe_21 = fields.Float('Straightness Lobe 21 (mm)', digits=(10, 6))
    straightness_lobe_22 = fields.Float('Straightness Lobe 22 (mm)', digits=(10, 6))
    straightness_lobe_31 = fields.Float('Straightness Lobe 31 (mm)', digits=(10, 6))
    straightness_lobe_32 = fields.Float('Straightness Lobe 32 (mm)', digits=(10, 6))
    straightness_pump_lobe = fields.Float('Straightness Pump Lobe (mm)', digits=(10, 6))

    # Universal Parallelism Measurements
    parallelism_lobe_11_a1_b1 = fields.Float('Parallelism Lobe 11 A1-B1 (mm)', digits=(10, 6))
    parallelism_lobe_12_a1_b1 = fields.Float('Parallelism Lobe 12 A1-B1 (mm)', digits=(10, 6))
    parallelism_lobe_21_a1_b1 = fields.Float('Parallelism Lobe 21 A1-B1 (mm)', digits=(10, 6))
    parallelism_lobe_22_a1_b1 = fields.Float('Parallelism Lobe 22 A1-B1 (mm)', digits=(10, 6))
    parallelism_lobe_31_a1_b1 = fields.Float('Parallelism Lobe 31 A1-B1 (mm)', digits=(10, 6))
    parallelism_lobe_32_a1_b1 = fields.Float('Parallelism Lobe 32 A1-B1 (mm)', digits=(10, 6))
    parallelism_pump_lobe_a1_b1 = fields.Float('Parallelism Pump Lobe A1-B1 (mm)', digits=(10, 6))

    # Universal M PSA Lobing Notation
    m_psa_lobing_notation_lobe_11 = fields.Float('M PSA Lobing Notation Lobe 11', digits=(10, 6))
    m_psa_lobing_notation_lobe_12 = fields.Float('M PSA Lobing Notation Lobe 12', digits=(10, 6))
    m_psa_lobing_notation_lobe_21 = fields.Float('M PSA Lobing Notation Lobe 21', digits=(10, 6))
    m_psa_lobing_notation_lobe_22 = fields.Float('M PSA Lobing Notation Lobe 22', digits=(10, 6))
    m_psa_lobing_notation_lobe_31 = fields.Float('M PSA Lobing Notation Lobe 31', digits=(10, 6))
    m_psa_lobing_notation_lobe_32 = fields.Float('M PSA Lobing Notation Lobe 32', digits=(10, 6))
    m_psa_lobing_notation_pumplobe = fields.Float('M PSA Lobing Notation Pump Lobe', digits=(10, 6))

    result = fields.Selection([
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], string='Result', required=True)

    rejection_reason = fields.Text('Rejection Reason')
    raw_data = fields.Text('Raw Data')

    # Rendered tolerance table (read-only)
    tolerance_table_html = fields.Html(string='Tolerance Summary', compute='_compute_tolerance_table', sanitize=False)

    @api.depends('part_form')
    def _compute_camshaft_type(self):
        """Determine camshaft type based on part_form"""
        for record in self:
            if 'Intake' in (record.part_form or ''):
                record.camshaft_type = 'intake'
            else:
                record.camshaft_type = 'exhaust'

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

    # Tolerance handling by serial prefix
    def _serial_prefix(self):
        return str(self.serial_number or '')[:3]

    def _normalize_tolerance_key(self, key):
        """Normalize external JSON keys to model field names.
        - Lowercase
        - Strip trailing `_ctf` or `_ctf_###`
        - Map A-lobe identifiers to existing E-lobe fields (intake uses same slots)
        - Map known alias prefixes
        """
        k = str(key or '').strip().lower()
        # Strip trailing _ctf or _ctf_123
        if k.endswith('_ctf'):
            k = k[:-4]
        # Remove `_ctf_<num>` suffix
        if '_ctf_' in k:
            parts = k.split('_ctf_')
            k = parts[0]

        # Replace aXX with eXX for lobe identifiers used in field names
        for ident in ['11', '12', '21', '22', '31', '32']:
            k = k.replace(f'lobe_a{ident}', f'lobe_e{ident}')

        # Known alias mappings
        aliases = {
            'concentricity_io_m_step_diameter': 'concentricity_io_step_diameter_32_5',
            'concentricity_result_step_diameter': 'concentricity_result_step_diameter_32_5',
            'concentricity_io_m_front_end': 'concentricity_io_front_end_dia_39',
            'concentricity_result_front_end': 'concentricity_result_front_end_dia_39',
            'concentricity_io_m_front_end_major': 'concentricity_io_front_end_major_dia_40',
            'concentricity_io_m_front_end_major_dia': 'concentricity_io_front_end_major_dia_40',
            'concentricity_result_front_end_major': 'concentricity_result_front_end_major_dia_40',
            'concentricity_result_front_end_major_dia': 'concentricity_result_front_end_major_dia_40',
            'face_total_runout_of_bearing_face_0': 'face_total_runout_bearing_face_0',
            'face_total_runout_of_bearing_face_25': 'face_total_runout_bearing_face_25',
            'trigger_wheel_diameter_ctf': 'trigger_wheel_diameter',
            'trigger_wheel_width_ctf': 'trigger_wheel_width',
        }
        if k in aliases:
            k = aliases[k]
        return k

    def _get_tolerances_for_serial(self):
        """Fetch tolerances for current serial prefix from system parameters as JSON.
        Prefix to parameter key mapping:
          980 → manufacturing.aumann.intake_tolerances_json
          480 → manufacturing.aumann.exhaust_tolerances_json
        Expected format: {"field_name": [lower_limit, upper_limit], ...}
        """
        prefix = self._serial_prefix()
        key_map = {
            '980': 'manufacturing.aumann.intake_tolerances_json',
            '480': 'manufacturing.aumann.exhaust_tolerances_json',
        }
        param_key = key_map.get(prefix)
        if not param_key:
            return {}
        raw = self.env['ir.config_parameter'].sudo().get_param(param_key) or ''
        try:
            data = json.loads(raw) if raw else {}
            # Normalize keys to strings and values to (lower, upper)
            normalized = {}
            for k, v in (data or {}).items():
                if isinstance(v, (list, tuple)) and len(v) == 2:
                    try:
                        field_name = self._normalize_tolerance_key(k)
                        normalized[str(field_name)] = (float(v[0]), float(v[1]))
                    except Exception:
                        continue
            return normalized
        except Exception as e:
            _logger.warning(f"Invalid tolerance JSON for prefix {prefix}: {e}")
            return {}

    def _evaluate_against_tolerances(self, tolerance_map):
        """Check all present fields against provided tolerances.
        Returns tuple: (result_str, reason_str, total, passed, failed)
        """
        failures = []
        total = 0
        passed = 0
        for field_name, (lower_limit, upper_limit) in (tolerance_map or {}).items():
            # Skip unknown fields to avoid AttributeError
            if not hasattr(self, field_name):
                continue
            value = getattr(self, field_name)
            if value is None:
                continue
            total += 1
            if lower_limit <= value <= upper_limit:
                passed += 1
            else:
                label = self._fields.get(field_name).string if field_name in self._fields else field_name
                failures.append(f"{label} ({field_name}) = {value} not in [{lower_limit}, {upper_limit}]")

        failed = max(total - passed, 0)
        if failures:
            return 'reject', '; '.join(failures)[:2000], total, passed, failed
        return 'pass', '', total, passed, failed

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            # Auto-evaluate for supported serial prefixes when tolerances exist
            tol = record._get_tolerances_for_serial()
            if tol:
                result, reason, total, passed, failed = record._evaluate_against_tolerances(tol)
                record.write({
                    'result': result,
                    'rejection_reason': reason,
                    'total_measurements': total,
                    'measurements_passed': passed,
                })
            # Update or create part quality record
            self._update_part_quality(record)
        return records

    def write(self, vals):
        res = super().write(vals)
        for record in self:
            tol = record._get_tolerances_for_serial()
            if tol:
                result, reason, total, passed, failed = record._evaluate_against_tolerances(tol)
                updates = {}
                if record.result != result:
                    updates['result'] = result
                if (record.rejection_reason or '') != (reason or ''):
                    updates['rejection_reason'] = reason
                if record.total_measurements != total:
                    updates['total_measurements'] = total
                if record.measurements_passed != passed:
                    updates['measurements_passed'] = passed
                if updates:
                    super(AumannMeasurement, record).write(updates)
            # Keep part quality in sync
            self._update_part_quality(record)
        return res

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

        # Find the latest test_date among all Aumann records with the same serial_number
        latest_aumann = self.env['manufacturing.aumann.measurement'].search([
            ('serial_number', '=', record.serial_number)
        ], order='test_date desc', limit=1)
        
        # Update test_date with the latest one if found
        update_vals = {}
        if latest_aumann and latest_aumann.test_date:
            if not part_quality.test_date or latest_aumann.test_date > part_quality.test_date:
                update_vals['test_date'] = latest_aumann.test_date

        # Update aumann_result - use write with skip flag to prevent recursion
        if part_quality.aumann_result != record.result:
            update_vals['aumann_result'] = record.result
        
        if update_vals:
            part_quality.with_context(skip_station_recalculate=True).write(update_vals)

    def action_override_result(self):
        """Open wizard to override Aumann result - updates station record first, then syncs to part_quality"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Override Aumann Result',
            'res_model': 'manufacturing.station.override.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_station_model': 'manufacturing.aumann.measurement',
                'default_station_record_id': self.id,
                'default_station_name': 'aumann'
            }
        }

    def _compute_tolerance_table(self):
        for record in self:
            tol = record._get_tolerances_for_serial()
            if not tol:
                record.tolerance_table_html = '<div class="text-muted">No tolerances configured for this serial prefix.</div>'
                continue
            # Build HTML table
            rows = []
            header = (
                '<table class="o_table table table-sm table-striped">'
                '<thead><tr>'
                '<th>Label</th><th>LTL</th><th>UTL</th><th>Actual</th><th>Result</th>'
                '</tr></thead><tbody>'
            )
            for field_name, (ltl, utl) in tol.items():
                if not hasattr(record, field_name):
                    continue
                value = getattr(record, field_name)
                if value is None:
                    continue
                label = record._fields.get(field_name).string if field_name in record._fields else field_name
                ok = (ltl <= value <= utl)
                result_badge = '<span class="badge text-bg-success">OK</span>' if ok else '<span class="badge text-bg-danger">NOK</span>'
                rows.append(
                    f"<tr><td>{label}</td><td>{ltl}</td><td>{utl}</td><td>{value}</td><td>{result_badge}</td></tr>"
                )
            footer = '</tbody></table>'
            record.tolerance_table_html = header + ''.join(rows) + footer

    tolerance_line_ids = fields.One2many(
        'aumann.tolerance.line',
        'measurement_id',
        string='Tolerance Lines',
        compute='_compute_tolerance_lines'
    )

    spc_chart_ids = fields.One2many(
        'aumann.measurement.spc.link',
        'measurement_id',
        string='SPC Charts'
    )

    @api.depends('serial_number', 'test_date')
    def _compute_tolerance_lines(self):
        """Generate tolerance lines for display"""
        ToleranceLine = self.env['aumann.tolerance.line']

        for record in self:
            # Delete existing transient records for this measurement
            ToleranceLine.search([('measurement_id', '=', record.id)]).unlink()

            tol = record._get_tolerances_for_serial()
            if not tol:
                record.tolerance_line_ids = False
                continue

            lines = []
            for field_name, (ltl, utl) in tol.items():
                if not hasattr(record, field_name):
                    continue
                value = getattr(record, field_name)
                if value is None:
                    continue

                label = record._fields.get(field_name).string if field_name in record._fields else field_name

                # Check if SPC exists - SAFE ACCESS
                spc_chart_id = False
                try:
                    spc_link = record.spc_chart_ids.filtered(lambda x: x.field_name == field_name)
                    if spc_link:
                        spc_chart = spc_link[0].spc_chart_id
                        # Check if it's a valid record with proper model name
                        if spc_chart and hasattr(spc_chart,
                                                 '_name') and spc_chart._name == 'statistical.process.control':
                            # Use try-except for exists() check
                            try:
                                if spc_chart.exists():
                                    spc_chart_id = spc_chart.id
                                else:
                                    # Clean up broken link
                                    spc_link.unlink()
                            except Exception:
                                # exists() failed - clean up broken link
                                spc_link.unlink()
                except (AttributeError, IndexError, TypeError, KeyError) as e:
                    _logger.warning(f"Error checking SPC for field {field_name}: {e}")
                    spc_chart_id = False

                line = ToleranceLine.create({
                    'measurement_id': record.id,
                    'field_name': field_name,
                    'label': label,
                    'lower_limit': ltl,
                    'upper_limit': utl,
                    'actual_value': value,
                    'spc_chart_id': spc_chart_id,
                })
                lines.append(line.id)

            record.tolerance_line_ids = [(6, 0, lines)]

    def action_create_spc_for_field(self, field_name):
        """Create SPC chart for a specific measurement field"""
        self.ensure_one()

        # Check if SPC already exists
        existing_link = self.spc_chart_ids.filtered(lambda x: x.field_name == field_name)
        if existing_link:
            spc_chart = existing_link[0].spc_chart_id
            try:
                if spc_chart and hasattr(spc_chart, '_name') and spc_chart._name == 'statistical.process.control':
                    if spc_chart.exists():
                        return {
                            'type': 'ir.actions.act_window',
                            'res_model': 'statistical.process.control',
                            'res_id': spc_chart.id,
                            'view_mode': 'form',
                            'target': 'current',
                        }
            except Exception as e:
                _logger.warning(f"Error checking SPC existence for {field_name}: {e}")
            existing_link.unlink()

        field_value = getattr(self, field_name)
        if not field_value:
            raise UserError(f'No value available for {field_name}')

        # Get tolerances
        tol = self._get_tolerances_for_serial()
        if field_name not in tol:
            raise UserError(f'No tolerance defined for {field_name}')

        lower_limit, upper_limit = tol[field_name]

        # Get machine name
        machine_name = ''
        if self.machine_id:
            for field in ['name', 'machine_name', 'display_name', 'code']:
                if hasattr(self.machine_id, field):
                    machine_name = getattr(self.machine_id, field, '')
                    if machine_name:
                        break
            if not machine_name:
                machine_name = f"Machine {self.machine_id.id}"

        field_label = self._fields.get(field_name).string if field_name in self._fields else field_name

        # Get last 50 readings + current reading = 51 total
        similar_measurements = self.env['manufacturing.aumann.measurement'].search([
            ('machine_id', '=', self.machine_id.id if self.machine_id else False),
            ('part_form', '=', self.part_form),
            (field_name, '!=', False),
            ('id', '<=', self.id),
        ], order='test_date desc', limit=101)

        if self not in similar_measurements:
            similar_measurements = similar_measurements[:100] | self
        else:
            similar_measurements = similar_measurements[:101]

        _logger.info(f"Creating SPC for {field_name} with {len(similar_measurements)} measurements")

        # Create SPC record
        spc_vals = {
            'date': fields.Date.today(),
            'operation': f'{field_label} - {self.part_form}',
            'machine_name': machine_name,
            'usl': upper_limit,
            'lsl': lower_limit,
            'least_count': 0.001,
            'is_auto_created': True,
        }

        spc_record = self.env['statistical.process.control'].create(spc_vals)

        # Delete auto-created empty groups
        empty_groups = self.env['spc.measurement.group'].search([
            ('spc_id', '=', spc_record.id),
            ('measurement_value_ids', '=', False)
        ])
        if empty_groups:
            empty_groups.unlink()

        # Create 5 parameters (X1, X2, X3, X4, X5)
        parameters = []
        for i in range(1, 6):
            parameter = self.env['spc.measurement.parameter'].create({
                'name': f'X{i}',
                'sequence': i * 10,
                'spc_id': spc_record.id,
            })
            parameters.append(parameter)

        # Reverse to get chronological order (oldest to newest)
        measurements_list = list(reversed(similar_measurements))

        # Create groups with 5 measurements each
        group_number = 0
        for i in range(0, len(measurements_list), 5):
            group_number += 1
            chunk = measurements_list[i:i + 5]  # Get 5 measurements

            # Use the first measurement's test_date for the group
            group = self.env['spc.measurement.group'].create({
                'spc_id': spc_record.id,
                'date_of_measurement': chunk[0].test_date or fields.Datetime.now(),
            })

            # Create measurement values for each measurement in the chunk
            for idx, measurement in enumerate(chunk):
                if idx < len(parameters):  # Safety check
                    self.env['spc.measurement.value'].create({
                        'parameter_id': parameters[idx].id,
                        'group_id': group.id,
                        'spc_id': spc_record.id,
                        'value': getattr(measurement, field_name),
                    })

        # Create link
        self.env['aumann.measurement.spc.link'].create({
            'measurement_id': self.id,
            'field_name': field_name,
            'spc_chart_id': spc_record.id,
        })

        # Calculate statistics
        spc_record.action_calculate_statistics()

        _logger.info(f"Created SPC chart {spc_record.id} for {field_name} with {group_number} groups")

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'statistical.process.control',
            'res_id': spc_record.id,
            'view_mode': 'form',
            'target': 'current',
        }

class AumannMeasurementSPCLink(models.Model):
    _name = 'aumann.measurement.spc.link'
    _description = 'Link between Aumann Measurements and SPC Charts'

    measurement_id = fields.Many2one('manufacturing.aumann.measurement', required=True, ondelete='cascade')
    field_name = fields.Char('Field Name', required=True)
    spc_chart_id = fields.Many2one('statistical.process.control', 'SPC Chart', required=True, ondelete='cascade')


class AumannToleranceLine(models.TransientModel):
    _name = 'aumann.tolerance.line'
    _description = 'Tolerance Line'

    measurement_id = fields.Many2one('manufacturing.aumann.measurement', required=True, ondelete='cascade')
    field_name = fields.Char('Field Name', required=True)
    label = fields.Char('Label')
    lower_limit = fields.Float('LTL', digits=(10, 6))
    upper_limit = fields.Float('UTL', digits=(10, 6))
    actual_value = fields.Float('Actual', digits=(10, 6))
    result = fields.Char('Result', compute='_compute_result')
    spc_chart_id = fields.Many2one('statistical.process.control', 'SPC Chart')
    has_spc = fields.Boolean('Has SPC', compute='_compute_has_spc')

    @api.depends('actual_value', 'lower_limit', 'upper_limit')
    def _compute_result(self):
        for line in self:
            if line.lower_limit <= line.actual_value <= line.upper_limit:
                line.result = 'OK'
            else:
                line.result = 'NOK'

    @api.depends('spc_chart_id')
    def _compute_has_spc(self):
        for line in self:
            try:
                if line.spc_chart_id and line.spc_chart_id.exists():
                    line.has_spc = True
                else:
                    line.has_spc = False
            except Exception:
                line.has_spc = False

    def action_create_spc(self):
        """Create SPC for this tolerance line"""
        self.ensure_one()
        return self.measurement_id.action_create_spc_for_field(self.field_name)

    def action_view_spc(self):
        """View existing SPC"""
        self.ensure_one()

        # Verify SPC chart exists
        if not self.spc_chart_id or not self.spc_chart_id.exists():
            raise UserError('SPC Chart no longer exists. Please create a new one.')

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'statistical.process.control',
            'res_id': self.spc_chart_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_download_x_chart(self):
        """Download X-Chart for this tolerance line"""
        self.ensure_one()

        # Verify SPC chart exists
        if not self.spc_chart_id or not self.spc_chart_id.exists():
            raise UserError('SPC Chart no longer exists. Please create a new one.')

        spc = self.spc_chart_id

        # Generate chart if not already generated
        if not spc.x_chart_image:
            spc.action_generate_charts()

        return spc.action_download_x_chart()
    def action_download_r_chart(self):
        """Download X-Chart for this tolerance line"""
        self.ensure_one()

        # Verify SPC chart exists
        if not self.spc_chart_id or not self.spc_chart_id.exists():
            raise UserError('SPC Chart no longer exists. Please create a new one.')

        spc = self.spc_chart_id

        # Generate chart if not already generated
        if not spc.r_chart_image:
            spc.action_generate_charts()

        return spc.action_download_r_chart()

    def action_download_interval_frequency_chart(self):
        """Download X-Chart for this tolerance line"""
        self.ensure_one()

        # Verify SPC chart exists
        if not self.spc_chart_id or not self.spc_chart_id.exists():
            raise UserError('SPC Chart no longer exists. Please create a new one.')

        spc = self.spc_chart_id

        # Generate chart if not already generated
        if not spc.interval_frequency_chart_image:
            spc.action_generate_charts()

        return spc.action_download_interval_frequency_chart()