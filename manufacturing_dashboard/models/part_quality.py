# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
import pytz

_logger = logging.getLogger(__name__)


class PartQuality(models.Model):
    _name = 'manufacturing.part.quality'
    _description = 'Part Quality Control'
    _inherit = ['mail.thread', 'mail.activity.mixin']
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
    test_date = fields.Datetime('Test Date', index=True)
    
    # Part variant information
    part_variant = fields.Selection([
        ('exhaust', 'Exhaust'),
        ('intake', 'Intake')
    ], compute='_compute_part_variant', string='Part Variant', store=True)
    
    part_description = fields.Char('Part Description', compute='_compute_part_description', store=True)

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

    gauging_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], default='pending', string='Gauging Result')

    # Final result
    final_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], compute='_compute_final_result', string='Final Result', store=True)

    # Box tracking
    box_number = fields.Char('Box Number')
    box_position = fields.Integer('Position in Box')
    box_id = fields.Many2one('manufacturing.box.management', string='Box')

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
    gauging_measurement_ids = fields.One2many(
        'manufacturing.gauging.measurement',
        'serial_number',
        string='Gauging Tests'
    )

    @api.depends('serial_number')
    def _compute_part_variant(self):
        """Detect part variant based on serial number prefix"""
        for record in self:
            if record.serial_number:
                if record.serial_number.startswith('480'):
                    record.part_variant = 'exhaust'
                elif record.serial_number.startswith('980'):
                    record.part_variant = 'intake'
                else:
                    record.part_variant = False
            else:
                record.part_variant = False

    @api.depends('part_variant')
    def _compute_part_description(self):
        """Set part description based on variant"""
        for record in self:
            if record.part_variant == 'exhaust':
                record.part_description = 'Exhaust Camshaft'
            elif record.part_variant == 'intake':
                record.part_description = 'Intake Camshaft'
            else:
                record.part_description = 'Unknown Part'

    @api.depends('vici_result', 'ruhlamat_result', 'aumann_result', 'gauging_result', 'qe_override')
    def _compute_final_result(self):
        for record in self:
            if record.qe_override:
                # If QE has overridden, keep current final_result
                continue

            results = [record.vici_result, record.ruhlamat_result, record.aumann_result, record.gauging_result]

            if 'reject' in results:
                record.final_result = 'reject'
            elif all(result == 'pass' for result in results):
                record.final_result = 'pass'
                # Automatically assign to box when part passes
                record._assign_to_box_if_passed()
            else:
                record.final_result = 'pending'
    
    def _assign_to_box_if_passed(self):
        """Assign part to box if it passes all tests"""
        self.ensure_one()
        
        # Only assign if not already assigned to a box and has a valid variant
        if not self.box_id and self.final_result == 'pass' and self.part_variant:
            try:
                box_management = self.env['manufacturing.box.management']
                current_box = box_management.get_or_create_current_box(self.part_variant)
                position = current_box.add_part_to_box(self.id)
                
                _logger.info(f"Assigned {self.part_variant} part {self.serial_number} to box {current_box.box_number} at position {position}")
                
            except Exception as e:
                _logger.error(f"Error assigning part {self.serial_number} to box: {str(e)}")

    def qe_override_result(self, new_result=None, comments=None):
        """Allow Quality Engineer to override the result"""
        self.ensure_one()
        
        # If no parameters provided, open the wizard
        if new_result is None or comments is None:
            return {
                'type': 'ir.actions.act_window',
                'name': 'QE Override',
                'res_model': 'manufacturing.qe.override.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_part_quality_id': self.id}
            }
        
        self.write({
            'final_result': new_result,
            'qe_override': True,
            'qe_comments': comments
        })

        # Log the override (temporarily disabled chatter)
        # self.message_post(
        #     body=f"QE Override: Result changed to {new_result}. Comments: {comments}",
        #     message_type='notification'
        # )