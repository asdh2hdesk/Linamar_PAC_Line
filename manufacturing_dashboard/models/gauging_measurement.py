# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
import re
import pytz

_logger = logging.getLogger(__name__)


class GaugingMeasurement(models.Model):
    _name = 'manufacturing.gauging.measurement'
    _description = 'Gauging Measurement System Data'
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

    # Basic identification fields
    serial_number = fields.Char('Serial Number', required=True, index=True)
    machine_id = fields.Many2one('manufacturing.machine.config', 'Machine', required=True)
    test_date = fields.Datetime('Test Date', required=True)
    
    # Fields based on CSV structure
    component_name = fields.Char('Component Name', index=True)
    job_number = fields.Char('Job Number', index=True)
    
    # Angular measurement (RESULT column)
    angle_measurement = fields.Char('Angle Measurement')  # Store as text initially (e.g., "1°30'0"")
    angle_degrees = fields.Float('Angle (Degrees)', digits=(10, 4))  # Converted to decimal degrees
    angle_minutes = fields.Integer('Minutes')
    angle_seconds = fields.Integer('Seconds')
    
    # Status from Excel
    status = fields.Selection([
        ('accept', 'ACCEPT'),
        ('reject', 'REJECT'),
        ('pending', 'PENDING')
    ], string='Status', default='accept')
    
    # Overall result for consistency with other models
    result = fields.Selection([
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], string='Result', compute='_compute_result', store=True)
    
    # Additional measurement fields that might be in other columns
    measurement_value = fields.Float('Measurement Value', digits=(10, 6))
    nominal_value = fields.Float('Nominal Value', digits=(10, 6))
    upper_tolerance = fields.Float('Upper Tolerance', digits=(10, 6))
    lower_tolerance = fields.Float('Lower Tolerance', digits=(10, 6))
    
    # Quality tracking
    within_tolerance = fields.Boolean('Within Tolerance', compute='_compute_tolerance', store=True)
    deviation = fields.Float('Deviation from Nominal', compute='_compute_deviation', store=True)
    
    # Raw data
    raw_data = fields.Text('Raw Data')
    rejection_reason = fields.Text('Rejection Reason')
    
    @api.depends('status')
    def _compute_result(self):
        for record in self:
            if record.status == 'accept':
                record.result = 'pass'
            elif record.status == 'reject':
                record.result = 'reject'
            else:
                record.result = 'pass'  # Default for pending or unknown
    
    @api.depends('measurement_value', 'nominal_value', 'upper_tolerance', 'lower_tolerance')
    def _compute_tolerance(self):
        for record in self:
            if (record.measurement_value is not None and 
                record.nominal_value is not None and 
                record.upper_tolerance is not None and 
                record.lower_tolerance is not None):
                
                upper_limit = record.nominal_value + record.upper_tolerance
                lower_limit = record.nominal_value + record.lower_tolerance
                
                record.within_tolerance = (lower_limit <= record.measurement_value <= upper_limit)
            else:
                record.within_tolerance = True  # Default to True if no tolerance defined
    
    @api.depends('measurement_value', 'nominal_value')
    def _compute_deviation(self):
        for record in self:
            if record.measurement_value is not None and record.nominal_value is not None:
                record.deviation = record.measurement_value - record.nominal_value
            else:
                record.deviation = 0.0
    
    def parse_angle_measurement(self, angle_str):
        """
        Parse angle measurement from format like "1°30'0"" to decimal degrees
        Returns tuple: (degrees_decimal, degrees, minutes, seconds)
        """
        if not angle_str:
            return 0.0, 0, 0, 0
            
        try:
            # Remove any extra quotes or spaces
            angle_str = str(angle_str).strip().strip('"')
            
            # Pattern to match degrees°minutes'seconds" format
            pattern = r"(-?\d+)°(\d+)'(\d+)\"?"
            match = re.match(pattern, angle_str)
            
            if match:
                degrees = int(match.group(1))
                minutes = int(match.group(2))
                seconds = int(match.group(3))
                
                # Convert to decimal degrees
                decimal_degrees = abs(degrees) + minutes/60.0 + seconds/3600.0
                if degrees < 0:
                    decimal_degrees = -decimal_degrees
                    
                return decimal_degrees, degrees, minutes, seconds
            else:
                # Try to parse as simple decimal
                try:
                    decimal_degrees = float(angle_str)
                    return decimal_degrees, int(decimal_degrees), 0, 0
                except:
                    return 0.0, 0, 0, 0
                    
        except Exception as e:
            _logger.warning(f"Failed to parse angle measurement '{angle_str}': {e}")
            return 0.0, 0, 0, 0
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Parse angle measurement if provided
            if 'angle_measurement' in vals and vals['angle_measurement']:
                decimal_degrees, degrees, minutes, seconds = self.parse_angle_measurement(vals['angle_measurement'])
                vals['angle_degrees'] = decimal_degrees
                vals['angle_minutes'] = minutes
                vals['angle_seconds'] = seconds
        
        records = super().create(vals_list)
        
        for record in records:
            # Update or create part quality record
            self._update_part_quality(record)
            
        return records
    
    def write(self, vals):
        # Parse angle measurement if being updated
        if 'angle_measurement' in vals and vals['angle_measurement']:
            decimal_degrees, degrees, minutes, seconds = self.parse_angle_measurement(vals['angle_measurement'])
            vals['angle_degrees'] = decimal_degrees
            vals['angle_minutes'] = minutes
            vals['angle_seconds'] = seconds
            
        return super().write(vals)
    
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
        
        # Find the latest test_date among all Gauging records with the same serial_number
        latest_gauging = self.env['manufacturing.gauging.measurement'].search([
            ('serial_number', '=', record.serial_number)
        ], order='test_date desc', limit=1)
        
        # Update test_date with the latest one if found
        update_vals = {}
        if latest_gauging and latest_gauging.test_date:
            if not part_quality.test_date or latest_gauging.test_date > part_quality.test_date:
                update_vals['test_date'] = latest_gauging.test_date
        
        # Update the gauging result - use write with skip flag to prevent recursion
        if part_quality.gauging_result != record.result:
            update_vals['gauging_result'] = record.result
        
        if update_vals:
            part_quality.with_context(skip_station_recalculate=True).write(update_vals)

    def action_override_result(self):
        """Open wizard to override Gauging result - updates station record first, then syncs to part_quality"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Override Gauging Result',
            'res_model': 'manufacturing.station.override.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_station_model': 'manufacturing.gauging.measurement',
                'default_station_record_id': self.id,
                'default_station_name': 'gauging'
            }
        }
