# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
from datetime import datetime
import pytz

_logger = logging.getLogger(__name__)


class FinalStationMeasurement(models.Model):
    _name = 'manufacturing.final.station.measurement'
    _description = 'Final Station Measurement Records'
    _rec_name = 'serial_number'
    _order = 'capture_date desc'

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

    # Basic Information
    machine_id = fields.Many2one('manufacturing.machine.config', string='Final Station', required=True)
    serial_number = fields.Char('Serial Number', required=True)
    capture_date = fields.Datetime('Capture Date/Time', required=True)
    result = fields.Selection([
        ('ok', 'OK'),
        ('nok', 'NOK'),
        ('pending', 'Pending')
    ], string='Result', default='pending', required=True)
    
    # Operation Details
    operation_mode = fields.Selection([
        ('auto', 'Auto'),
        ('manual', 'Manual')
    ], string='Operation Mode', required=True)
    trigger_type = fields.Selection([
        ('auto', 'Auto Trigger'),
        ('manual', 'Manual Trigger'),
        ('sensor', 'Sensor Trigger')
    ], string='Trigger Type', required=True)
    
    # Additional Data
    raw_data = fields.Text('Raw Data', help='Raw data from camera/PLC')
    notes = fields.Text('Notes', help='Additional notes or comments')
    
    # Quality Metrics
    pass_rate = fields.Float('Pass Rate %', compute='_compute_pass_rate', store=True)
    is_quality_issue = fields.Boolean('Quality Issue', default=False)
    rejection_reason = fields.Char('Rejection Reason')
    
    # Timestamps
    created_date = fields.Datetime('Created Date')
    modified_date = fields.Datetime('Modified Date')
    
    @api.depends('result')
    def _compute_pass_rate(self):
        """Compute pass rate for the measurement"""
        for record in self:
            if record.result == 'ok':
                record.pass_rate = 100.0
            elif record.result == 'nok':
                record.pass_rate = 0.0
            else:
                record.pass_rate = 0.0

    @api.model
    def create_measurement_record(self, machine_id, serial_number, result='ok', operation_mode='auto', trigger_type='auto', raw_data='', capture_date=None):
        """Create a new measurement record"""
        try:
            # Use provided capture_date or current IST time
            if capture_date is None:
                capture_date = self.get_ist_now()
            
            measurement = self.create({
                'machine_id': machine_id,
                'serial_number': serial_number,
                'capture_date': capture_date,
                'result': result,
                'operation_mode': operation_mode,
                'trigger_type': trigger_type,
                'raw_data': raw_data,
                'created_date': self.get_ist_now(),
                'modified_date': self.get_ist_now(),
            })
            
            _logger.info(f"Created measurement record: {serial_number} - {result}")
            return measurement
            
        except Exception as e:
            _logger.error(f"Error creating measurement record: {str(e)}")
            return False

    @api.model
    def get_today_statistics(self, machine_id):
        """Get today's statistics for a specific machine"""
        try:
            today = fields.Date.today()
            measurements = self.search([
                ('machine_id', '=', machine_id),
                ('capture_date', '>=', today)
            ])
            
            total = len(measurements)
            ok_count = len(measurements.filtered(lambda r: r.result == 'ok'))
            nok_count = len(measurements.filtered(lambda r: r.result == 'nok'))
            pending_count = len(measurements.filtered(lambda r: r.result == 'pending'))
            
            pass_rate = 0
            if total > 0:
                pass_rate = (ok_count / total) * 100
            
            return {
                'total_measurements': total,
                'ok_measurements': ok_count,
                'nok_measurements': nok_count,
                'pending_measurements': pending_count,
                'pass_rate': round(pass_rate, 2)
            }
            
        except Exception as e:
            _logger.error(f"Error getting statistics: {str(e)}")
            return {
                'total_measurements': 0,
                'ok_measurements': 0,
                'nok_measurements': 0,
                'pending_measurements': 0,
                'pass_rate': 0
            }

    @api.model
    def get_recent_measurements(self, machine_id, limit=10):
        """Get recent measurements for a specific machine"""
        try:
            measurements = self.search([
                ('machine_id', '=', machine_id)
            ], limit=limit, order='capture_date desc')
            
            return [{
                'id': m.id,
                'serial_number': m.serial_number,
                'capture_date': m.capture_date.isoformat() if m.capture_date else None,
                'result': m.result,
                'operation_mode': m.operation_mode,
                'trigger_type': m.trigger_type
            } for m in measurements]
            
        except Exception as e:
            _logger.error(f"Error getting recent measurements: {str(e)}")
            return []

    def action_mark_ok(self):
        """Mark measurement as OK"""
        self.ensure_one()
        self.result = 'ok'
        self.modified_date = self.get_ist_now()
        _logger.info(f"Measurement {self.serial_number} marked as OK")

    def action_mark_nok(self):
        """Mark measurement as NOK"""
        self.ensure_one()
        self.result = 'nok'
        self.modified_date = self.get_ist_now()
        _logger.info(f"Measurement {self.serial_number} marked as NOK")

    def action_mark_pending(self):
        """Mark measurement as Pending"""
        self.ensure_one()
        self.result = 'pending'
        self.modified_date = self.get_ist_now()
        _logger.info(f"Measurement {self.serial_number} marked as Pending")
