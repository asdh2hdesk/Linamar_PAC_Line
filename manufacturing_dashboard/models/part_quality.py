# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
import pytz

_logger = logging.getLogger(__name__)


class PartQuality(models.Model):
    _name = 'manufacturing.part.quality'
    _description = 'Part Quality Control'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'translation.mixin']
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
    
    part_description = fields.Char('Part Description', compute='_compute_part_description', store=True,translate=True)

    # Station results
    vici_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject'),
        ('bypass', 'Bypass')
    ], default='pending', string='VICI Result')

    ruhlamat_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject'),
        ('bypass', 'Bypass')
    ], default='pending', string='Ruhlamat Result')

    aumann_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject'),
        ('bypass', 'Bypass')
    ], default='pending', string='Aumann Result')

    gauging_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject'),
        ('bypass', 'Bypass')
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

    # Final station scan gating
    final_station_scanned = fields.Boolean('Scanned at Final Station', default=False)
    final_station_scan_time = fields.Datetime('Final Station Scan Time')

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

            # Use actual results from part_quality fields (bypass status is already set in the fields)
            results = [record.vici_result, record.ruhlamat_result, record.aumann_result, record.gauging_result]

            # Determine final result logic:
            # - If ANY station is reject -> reject
            # - If ALL stations are pass or bypass -> pass
            # - If ANY station is bypass and no reject -> pass
            # - Otherwise -> pending
            old_result = record.final_result
            
            if 'reject' in results:
                record.final_result = 'reject'
                # If part was previously passed and assigned to box, remove it
                if old_result == 'pass' and record.box_id:
                    record._remove_from_box_if_rejected()
            elif all(result in ('pass', 'bypass') for result in results):
                record.final_result = 'pass'
            elif 'bypass' in results and 'reject' not in results:
                record.final_result = 'pass'  # Pass if any station is bypassed and no failures
            else:
                record.final_result = 'pending'
                # If part was previously passed and assigned to box, remove it
                if old_result == 'pass' and record.box_id:
                    record._remove_from_box_if_rejected()
    
    def _get_machine_bypass_status(self):
        """Get current bypass status for all machines"""
        self.ensure_one()
        
        try:
            # Get all active machines and their bypass status
            machines = self.env['manufacturing.machine.config'].search([
                ('is_active', '=', True),
                ('machine_type', 'in', ['vici_vision', 'ruhlamat', 'aumann', 'gauging'])
            ])
            
            bypass_status = {}
            for machine in machines:
                bypass_status[machine.machine_type] = machine.is_bypassed
            
            return bypass_status
        except Exception as e:
            _logger.error(f"Error getting machine bypass status: {str(e)}")
            return {}

    def _assign_to_box_if_passed(self):
        """Assign part to box only when passed and scanned at final station"""
        self.ensure_one()
        
        # Only assign if: not already assigned, final_result == pass, scanned at final station, and valid variant
        if not self.box_id and self.final_result == 'pass' and self.final_station_scanned and self.part_variant:
            try:
                box_management = self.env['manufacturing.box.management']
                current_box = box_management.get_or_create_current_box(self.part_variant)
                position = current_box.add_part_to_box(self.id)
                
                _logger.info(f"Assigned {self.part_variant} part {self.serial_number} to box {current_box.box_number} at position {position}")
                
            except Exception as e:
                _logger.error(f"Error assigning part {self.serial_number} to box: {str(e)}")

    def _remove_from_box_if_rejected(self):
        """Remove part from box if it's rejected"""
        self.ensure_one()
        
        # Only remove if currently assigned to a box and final result is reject
        if self.box_id and self.final_result == 'reject':
            try:
                box_number = self.box_number
                self.write({
                    'box_id': False,
                    'box_number': False,
                    'box_position': 0
                })
                
                _logger.info(f"Removed rejected {self.part_variant} part {self.serial_number} from box {box_number}")
                
            except Exception as e:
                _logger.error(f"Error removing rejected part {self.serial_number} from box: {str(e)}")

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
            'test_date': self.get_ist_now(),  # Update test_date to current datetime
            'qe_override': True,
            'qe_comments': comments
        })

        # Log the override (temporarily disabled chatter)
        # self.message_post(
        #     body=f"QE Override: Result changed to {new_result}. Comments: {comments}",
        #     message_type='notification'
        # )

    def override_station_result(self, station_name, new_result, comments):
        """Override a specific station result
        
        :param station_name: One of 'vici', 'ruhlamat', 'aumann', 'gauging'
        :param new_result: New result value ('pending', 'pass', 'reject', 'bypass')
        :param comments: Reason for override
        """
        self.ensure_one()
        
        station_map = {
            'vici': 'vici_result',
            'ruhlamat': 'ruhlamat_result',
            'aumann': 'aumann_result',
            'gauging': 'gauging_result'
        }
        
        if station_name not in station_map:
            raise ValueError(f"Invalid station name: {station_name}")
        
        field_name = station_map[station_name]
        
        # Update the station result and test_date to current datetime
        # Note: final_result will be automatically recalculated since it depends on station results
        self.with_context(skip_station_recalculate=True).write({
            field_name: new_result,
            'test_date': self.get_ist_now(),  # Update test_date to current datetime
            'qe_override': True,
            'qe_comments': f"[{station_name.upper()} Override] {comments}"
        })
        
        _logger.info(f"Station override applied: {station_name} -> {new_result} for serial {self.serial_number}, test_date updated to {self.test_date}")

    def action_override_vici_result(self):
        """Open wizard to override VICI result"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Override VICI Result',
            'res_model': 'manufacturing.station.override.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_part_quality_id': self.id,
                'default_station_name': 'vici'
            }
        }

    def action_override_ruhlamat_result(self):
        """Open wizard to override Ruhlamat result"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Override Ruhlamat Result',
            'res_model': 'manufacturing.station.override.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_part_quality_id': self.id,
                'default_station_name': 'ruhlamat'
            }
        }

    def action_override_aumann_result(self):
        """Open wizard to override Aumann result"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Override Aumann Result',
            'res_model': 'manufacturing.station.override.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_part_quality_id': self.id,
                'default_station_name': 'aumann'
            }
        }

    def action_override_gauging_result(self):
        """Open wizard to override Gauging result"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Override Gauging Result',
            'res_model': 'manufacturing.station.override.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_part_quality_id': self.id,
                'default_station_name': 'gauging'
            }
        }

    # def recalculate_station_result(self, station_name):
    #     """Recalculate and update a specific station result from measurement records
    #
    #     :param station_name: One of 'vici', 'ruhlamat', 'aumann', 'gauging'
    #     :return: True if successful, False otherwise
    #     """
    #     self.ensure_one()
    #
    #     if not self.serial_number:
    #         _logger.warning(f"Cannot recalculate station result: serial_number is missing")
    #         return False
    #
    #     try:
    #         station_map = {
    #             'vici': {
    #                 'model': 'manufacturing.vici.vision',
    #                 'field': 'vici_result',
    #                 'result_field': 'result',
    #                 'search_field': 'serial_number'
    #             },
    #             'ruhlamat': {
    #                 'model': 'manufacturing.ruhlamat.press',
    #                 'field': 'ruhlamat_result',
    #                 'result_field': 'result',
    #                 'search_field': 'part_id1'
    #             },
    #             'aumann': {
    #                 'model': 'manufacturing.aumann.measurement',
    #                 'field': 'aumann_result',
    #                 'result_field': 'result',
    #                 'search_field': 'serial_number'
    #             },
    #             'gauging': {
    #                 'model': 'manufacturing.gauging.measurement',
    #                 'field': 'gauging_result',
    #                 'result_field': 'result',
    #                 'search_field': 'serial_number'
    #             }
    #         }
    #
    #         if station_name not in station_map:
    #             _logger.error(f"Invalid station name: {station_name}. Must be one of: {list(station_map.keys())}")
    #             return False
    #
    #         station_info = station_map[station_name]
    #         measurement_model = self.env[station_info['model']]
    #
    #         # Search for the latest measurement record
    #         search_domain = [(station_info['search_field'], '=', self.serial_number)]
    #
    #         # For ruhlamat, we need to search by part_id1 and also check part_quality_id
    #         if station_name == 'ruhlamat':
    #             # Try to find by part_quality_id first (more reliable)
    #             ruhlamat_records = measurement_model.search([
    #                 ('part_quality_id', '=', self.id)
    #             ], order='cycle_date desc', limit=1)
    #
    #             if not ruhlamat_records:
    #                 # Fallback to part_id1 search
    #                 ruhlamat_records = measurement_model.search([
    #                     ('part_id1', '=', self.serial_number)
    #                 ], order='cycle_date desc', limit=1)
    #
    #             latest_measurement = ruhlamat_records[0] if ruhlamat_records else None
    #         else:
    #             # For other stations, order by test_date
    #             order_field = 'test_date' if hasattr(measurement_model, 'test_date') else 'id'
    #             latest_measurement = measurement_model.search(
    #                 search_domain,
    #                 order=f'{order_field} desc',
    #                 limit=1
    #             )
    #
    #         if not latest_measurement:
    #             _logger.info(f"No {station_name} measurement found for serial {self.serial_number}, setting to pending")
    #             self.with_context(skip_station_recalculate=True).write({station_info['field']: 'pending'})
    #             return True
    #
    #         # Get the result from the measurement record
    #         measurement_result = getattr(latest_measurement, station_info['result_field'], None)
    #
    #         if measurement_result:
    #             # Map 'pass'/'reject' to part_quality format (which also supports 'bypass')
    #             if measurement_result in ('pass', 'reject'):
    #                 self.with_context(skip_station_recalculate=True).write({station_info['field']: measurement_result})
    #                 _logger.info(f"Recalculated {station_name} result for serial {self.serial_number}: {measurement_result}")
    #                 return True
    #             else:
    #                 _logger.warning(f"Unexpected result value '{measurement_result}' for {station_name} measurement")
    #                 return False
    #         else:
    #             _logger.warning(f"No result field found in {station_name} measurement for serial {self.serial_number}")
    #             return False
    #
    #     except Exception as e:
    #         _logger.error(f"Error recalculating {station_name} result for serial {self.serial_number}: {str(e)}")
    #         return False
    #
    # def write(self, vals):
    #     """Override write to recalculate station results when serial_number is present"""
    #     # Skip recalculation if flag is set (prevents recursion)
    #     if self.env.context.get('skip_station_recalculate'):
    #         return super().write(vals)
    #
    #     # Only recalculate if serial_number is being set or changed
    #     should_recalculate = False
    #     serial_to_check = None
    #
    #     if 'serial_number' in vals:
    #         # Serial number is being set/changed
    #         should_recalculate = True
    #         serial_to_check = vals['serial_number']
    #     elif self and len(self) == 1 and self.serial_number:
    #         # Check if we're updating station result fields - if so, don't recalculate
    #         # (station results are synced from station records, not recalculated)
    #         station_result_fields = {'vici_result', 'ruhlamat_result', 'aumann_result', 'gauging_result'}
    #         if not any(field in vals for field in station_result_fields):
    #             # Only recalculate if serial exists and we're not just updating station results
    #             should_recalculate = True
    #             serial_to_check = self.serial_number
    #
    #     # Call super write first
    #     res = super().write(vals)
    #
    #     # After write, recalculate all station results only if serial_number was set/changed
    #     if should_recalculate and serial_to_check:
    #         for record in self:
    #             # Get the current serial number (may have been updated in write)
    #             current_serial = record.serial_number or serial_to_check
    #
    #             if not current_serial:
    #                 continue
    #
    #             _logger.info(f"Recalculating station results for serial: {current_serial}")
    #
    #             # Recalculate all station results using the recalculate_station_result method
    #             stations_to_recalculate = ['vici', 'ruhlamat', 'aumann', 'gauging']
    #
    #             for station_name in stations_to_recalculate:
    #                 try:
    #                     # Use recalculate_station_result which will update the field directly
    #                     record.recalculate_station_result(station_name)
    #                 except Exception as e:
    #                     _logger.error(f"Error recalculating {station_name} for serial {current_serial}: {str(e)}")
    #
    #             # Special handling for aumann: update test_date if aumann record exists and part_quality shows pending
    #             if record.aumann_result == 'pending':
    #                 aumann_record = self.env['manufacturing.aumann.measurement'].search([
    #                     ('serial_number', '=', current_serial)
    #                 ], order='test_date desc', limit=1)
    #
    #                 if aumann_record:
    #                     update_vals = {}
    #
    #                     # Update aumann_result if it's still pending
    #                     if record.aumann_result == 'pending':
    #                         update_vals['aumann_result'] = aumann_record.result
    #
    #                     # Update test_date from aumann's test_date
    #                     if aumann_record.test_date and (not record.test_date or record.test_date != aumann_record.test_date):
    #                         update_vals['test_date'] = aumann_record.test_date
    #                         _logger.info(f"Updated test_date to {aumann_record.test_date} from aumann record for serial {current_serial}")
    #
    #                     # Apply updates if any
    #                     if update_vals:
    #                         record.with_context(skip_station_recalculate=True).write(update_vals)
    #                         _logger.info(f"Updated aumann_result and test_date for serial {current_serial}: {update_vals}")
    #
    #     return res

    @api.model
    def cleanup_rejected_parts_from_boxes(self):
        """Clean up any rejected parts that are still assigned to boxes (data integrity)"""
        try:
            rejected_parts_in_boxes = self.search([
                ('final_result', '=', 'reject'),
                ('box_id', '!=', False)
            ])
            
            if rejected_parts_in_boxes:
                _logger.info(f"Found {len(rejected_parts_in_boxes)} rejected parts still assigned to boxes - cleaning up")
                
                for part in rejected_parts_in_boxes:
                    part._remove_from_box_if_rejected()
                
                _logger.info(f"Cleaned up {len(rejected_parts_in_boxes)} rejected parts from boxes")
                return len(rejected_parts_in_boxes)
            else:
                _logger.info("No rejected parts found in boxes - data integrity is good")
                return 0
                
        except Exception as e:
            _logger.error(f"Error cleaning up rejected parts from boxes: {str(e)}")
            return 0

    @api.model
    def calculate_daily_stats(self):
        """Calculate daily statistics for manufacturing parts"""
        try:
            _logger.info("Starting daily statistics calculation...")
            
            # First, clean up any rejected parts that might still be in boxes (data integrity)
            cleaned_count = self.cleanup_rejected_parts_from_boxes()
            if cleaned_count > 0:
                _logger.info(f"Data integrity cleanup: Removed {cleaned_count} rejected parts from boxes")
            
            # Get current IST date
            ist_now = self.get_ist_now()
            today_start = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = ist_now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Get all parts tested today
            today_parts = self.search([
                ('test_date', '>=', today_start),
                ('test_date', '<=', today_end)
            ])
            
            if not today_parts:
                _logger.info("No parts tested today, skipping statistics calculation")
                return
            
            # Calculate statistics
            total_parts = len(today_parts)
            passed_parts = len(today_parts.filtered(lambda p: p.final_result == 'pass'))
            rejected_parts = len(today_parts.filtered(lambda p: p.final_result == 'reject'))
            pending_parts = len(today_parts.filtered(lambda p: p.final_result == 'pending'))
            
            # Calculate pass rate
            pass_rate = (passed_parts / total_parts * 100) if total_parts > 0 else 0
            
            # Calculate statistics by part variant
            exhaust_parts = today_parts.filtered(lambda p: p.part_variant == 'exhaust')
            intake_parts = today_parts.filtered(lambda p: p.part_variant == 'intake')
            
            exhaust_passed = len(exhaust_parts.filtered(lambda p: p.final_result == 'pass'))
            intake_passed = len(intake_parts.filtered(lambda p: p.final_result == 'pass'))
            
            # Calculate station-specific statistics
            vici_passed = len(today_parts.filtered(lambda p: p.vici_result == 'pass'))
            ruhlamat_passed = len(today_parts.filtered(lambda p: p.ruhlamat_result == 'pass'))
            aumann_passed = len(today_parts.filtered(lambda p: p.aumann_result == 'pass'))
            gauging_passed = len(today_parts.filtered(lambda p: p.gauging_result == 'pass'))
            
            # Log the statistics
            _logger.info(f"=== Daily Statistics for {ist_now.strftime('%Y-%m-%d')} ===")
            _logger.info(f"Total Parts Tested: {total_parts}")
            _logger.info(f"Passed Parts: {passed_parts}")
            _logger.info(f"Rejected Parts: {rejected_parts}")
            _logger.info(f"Pending Parts: {pending_parts}")
            _logger.info(f"Overall Pass Rate: {pass_rate:.2f}%")
            _logger.info(f"Exhaust Parts: {len(exhaust_parts)} (Passed: {exhaust_passed})")
            _logger.info(f"Intake Parts: {len(intake_parts)} (Passed: {intake_passed})")
            _logger.info(f"VICI Passed: {vici_passed}")
            _logger.info(f"Ruhlamat Passed: {ruhlamat_passed}")
            _logger.info(f"Aumann Passed: {aumann_passed}")
            _logger.info(f"Gauging Passed: {gauging_passed}")
            _logger.info("=== End of Daily Statistics ===")
            
            # Store statistics in a model if needed (optional)
            # You could create a daily_stats model to store these values
            
        except Exception as e:
            _logger.error(f"Error calculating daily statistics: {str(e)}")
            raise