# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
import barcode
from barcode.writer import ImageWriter
import io
import base64
import pytz

_logger = logging.getLogger(__name__)


class BoxManagement(models.Model):
    _name = 'manufacturing.box.management'
    _description = 'Box Management for Final Station'
    _order = 'create_date desc'
    _rec_name = 'box_number'

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

    box_number = fields.Char('Box Number', required=True, index=True)
    part_variant = fields.Selection([
        ('exhaust', 'Exhaust'),
        ('intake', 'Intake')
    ], required=True, string='Part Variant')
    
    status = fields.Selection([
        ('open', 'Open'),
        ('full', 'Full'),
        ('printed', 'Barcode Printed')
    ], default='open', string='Status')
    
    current_position = fields.Integer('Current Position', default=0)
    max_capacity = fields.Integer('Max Capacity', default=540)
    
    # Box details
    create_date = fields.Datetime('Created Date')
    complete_date = fields.Datetime('Completed Date')
    print_date = fields.Datetime('Barcode Print Date')
    
    # Related parts
    part_quality_ids = fields.One2many(
        'manufacturing.part.quality',
        'box_id',
        string='Parts in Box'
    )
    
    # Barcode data
    barcode_data = fields.Binary('Barcode Image', attachment=True)
    barcode_filename = fields.Char('Barcode Filename')
    zebra_print_data = fields.Text('Zebra Print Data')
    
    # Statistics
    total_parts = fields.Integer('Total Parts', compute='_compute_statistics', store=True)
    passed_parts = fields.Integer('Passed Parts', compute='_compute_statistics', store=True)
    rejected_parts = fields.Integer('Rejected Parts', compute='_compute_statistics', store=True)
    
    @api.depends('part_quality_ids', 'part_quality_ids.final_result')
    def _compute_statistics(self):
        for record in self:
            record.total_parts = len(record.part_quality_ids)
            record.passed_parts = len(record.part_quality_ids.filtered(lambda p: p.final_result == 'pass'))
            record.rejected_parts = len(record.part_quality_ids.filtered(lambda p: p.final_result == 'reject'))
    
    @api.model
    def get_or_create_current_box(self, part_variant):
        """Get the current open box for a specific variant or create a new one"""
        current_box = self.search([
            ('status', '=', 'open'),
            ('part_variant', '=', part_variant)
        ], limit=1, order='create_date desc')
        
        if not current_box:
            # Create new box for this variant
            box_number = self._generate_box_number(part_variant)
            current_box = self.create({
                'box_number': box_number,
                'part_variant': part_variant,
                'status': 'open',
                'current_position': 0
            })
            _logger.info(f"Created new {part_variant} box: {box_number}")
        
        return current_box
    
    def _generate_box_number(self, part_variant):
        """Generate a unique box number for a specific variant"""
        # Get the last box number for this variant
        last_box = self.search([
            ('part_variant', '=', part_variant)
        ], limit=1, order='box_number desc')
        
        if last_box and last_box.box_number:
            try:
                # Extract number from box number (format: EXH001, INT001, etc.)
                prefix = 'EXH' if part_variant == 'exhaust' else 'INT'
                last_number = int(last_box.box_number.replace(prefix, ''))
                next_number = last_number + 1
            except (ValueError, AttributeError):
                next_number = 1
        else:
            next_number = 1
        
        prefix = 'EXH' if part_variant == 'exhaust' else 'INT'
        return f"{prefix}{next_number:03d}"
    
    def add_part_to_box(self, part_quality_id):
        """Add a part to the current box and return position"""
        self.ensure_one()
        
        if self.status != 'open':
            raise ValueError(f"Cannot add part to box {self.box_number} - status is {self.status}")
        
        if self.current_position >= self.max_capacity:
            raise ValueError(f"Box {self.box_number} is already full")
        
        # Increment position
        self.current_position += 1
        
        # Update part quality record
        part_quality = self.env['manufacturing.part.quality'].browse(part_quality_id)
        part_quality.write({
            'box_number': self.box_number,
            'box_position': self.current_position,
            'box_id': self.id
        })
        
        _logger.info(f"Added part {part_quality.serial_number} to box {self.box_number} at position {self.current_position}")
        
        # Check if box is now full
        if self.current_position >= self.max_capacity:
            self._complete_box()
        
        return self.current_position
    
    def _complete_box(self):
        """Mark box as full and generate barcode"""
        self.ensure_one()
        
        self.write({
            'status': 'full',
            'complete_date': fields.Datetime.now()
        })
        
        _logger.info(f"Box {self.box_number} is now full with {self.current_position} parts")
        
        # Generate barcode
        self._generate_barcode()
    
    def _generate_barcode(self):
        """Generate barcode for Zebra printer"""
        self.ensure_one()
        
        try:
            # Create barcode data matching the sample format
            part_description = "Exhaust Camshaft" if self.part_variant == 'exhaust' else "Intake Camshaft"
            barcode_data = f"{part_description} / {self.box_number}"
            
            # Generate barcode image (using Data Matrix for 2D barcode like in sample)
            try:
                datamatrix = barcode.get_barcode_class('datamatrix')
                barcode_instance = datamatrix(barcode_data, writer=ImageWriter())
            except:
                # Fallback to Code128 if DataMatrix not available
                code128 = barcode.get_barcode_class('code128')
                barcode_instance = code128(barcode_data, writer=ImageWriter())
            
            # Save to buffer
            buffer = io.BytesIO()
            barcode_instance.write(buffer)
            buffer.seek(0)
            
            # Convert to base64
            barcode_image = base64.b64encode(buffer.getvalue())
            
            # Generate Zebra printer ZPL commands
            zebra_commands = self._generate_zebra_commands(barcode_data)
            
            # Update record
            self.write({
                'barcode_data': barcode_image,
                'barcode_filename': f"{self.box_number}_barcode.png",
                'zebra_print_data': zebra_commands,
                'print_date': fields.Datetime.now()
            })
            
            _logger.info(f"Generated barcode for {self.part_variant} box {self.box_number}")
            
        except Exception as e:
            _logger.error(f"Error generating barcode for box {self.box_number}: {str(e)}")
    
    def _generate_zebra_commands(self, barcode_data):
        """Generate ZPL commands for Zebra printer matching sample format"""
        part_description = "Exhaust Camshaft" if self.part_variant == 'exhaust' else "Intake Camshaft"
        part_number = "56823"  # Based on sample
        
        # ZPL template matching the sample label format
        zpl_template = f"""
^XA
^FO50,50^GB700,400,3^FS
^FO70,80^A0N,40,40^FDPSA-AVTEC^FS
^FO70,130^A0N,30,30^FDPart Number: {part_number}^FS
^FO70,160^A0N,30,30^FDPart Description: {part_description}^FS
^FO70,190^A0N,30,30^FDDate: {self.complete_date.strftime('%d-%m-%Y %H:%M:%S')}^FS
^FO70,220^A0N,30,30^FDBox/Skid#: {self.box_number}^FS
^FO300,280^BY3
^BXN,10,200
^FD{barcode_data}^FS
^FO250,500^A0N,25,25^FD{barcode_data}^FS
^XZ
"""
        return zpl_template.strip()
    
    def print_barcode(self):
        """Print barcode to Zebra printer"""
        self.ensure_one()
        
        if not self.zebra_print_data:
            raise ValueError("No barcode data available for printing")
        
        # Here you would implement the actual printer communication
        # For now, we'll just log the ZPL commands
        _logger.info(f"Printing barcode for box {self.box_number}")
        _logger.info(f"ZPL Commands:\n{self.zebra_print_data}")
        
        # Update status
        self.write({'status': 'printed'})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Barcode Printed',
                'message': f'Barcode for box {self.box_number} has been sent to printer',
                'type': 'success',
            }
        }
    
    @api.model
    def get_box_statistics(self):
        """Get overall box statistics by variant"""
        all_boxes = self.search([])
        exhaust_boxes = all_boxes.filtered(lambda b: b.part_variant == 'exhaust')
        intake_boxes = all_boxes.filtered(lambda b: b.part_variant == 'intake')
        
        return {
            'total_boxes': len(all_boxes),
            'exhaust_boxes': {
                'total': len(exhaust_boxes),
                'open': len(exhaust_boxes.filtered(lambda b: b.status == 'open')),
                'full': len(exhaust_boxes.filtered(lambda b: b.status == 'full')),
                'printed': len(exhaust_boxes.filtered(lambda b: b.status == 'printed')),
                'total_parts': sum(exhaust_boxes.mapped('total_parts')),
                'passed_parts': sum(exhaust_boxes.mapped('passed_parts')),
            },
            'intake_boxes': {
                'total': len(intake_boxes),
                'open': len(intake_boxes.filtered(lambda b: b.status == 'open')),
                'full': len(intake_boxes.filtered(lambda b: b.status == 'full')),
                'printed': len(intake_boxes.filtered(lambda b: b.status == 'printed')),
                'total_parts': sum(intake_boxes.mapped('total_parts')),
                'passed_parts': sum(intake_boxes.mapped('passed_parts')),
            }
        }
