# -*- coding: utf-8 -*-

from odoo import models, fields, api
import os
import csv
import json
import logging
import pyodbc  # or pypyodbc
from datetime import datetime, timedelta
from .plc_monitor_service import get_plc_monitor_service

_logger = logging.getLogger(__name__)



class MachineConfig(models.Model):
    _name = 'manufacturing.machine.config'
    _description = 'Machine Configuration'
    _rec_name = 'machine_name'

    machine_name = fields.Char('Machine Name', required=True)
    machine_type = fields.Selection([
        ('vici_vision', 'VICI Vision System'),
        ('ruhlamat', 'Ruhlamat Press'),
        ('gauging', 'Gauging System'),
        ('aumann', 'Aumann Measurement'),
        ('final_station', 'Final Station'),
    ], string='Machine Type', required=True)

    csv_file_path = fields.Char('CSV File Path', 
                                help='Full path to the CSV file for this machine (not required for final stations)')
    aumann_tolerance_dirs = fields.Char('Aumann Tolerance Directories',
                                       help='Directory paths containing JSON tolerance files (480.json, 980.json). Separate multiple paths with semicolons.')
    is_active = fields.Boolean('Active', default=True)
    last_sync = fields.Datetime('Last Sync')
    sync_interval = fields.Integer('Sync Interval (seconds)', default=30)

    # Status fields
    status = fields.Selection([
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('error', 'Error'),
        ('maintenance', 'Maintenance')
    ], default='stopped')

    # Progress tracking fields
    sync_progress = fields.Float('Sync Progress %', default=0.0, help='Current sync progress percentage')
    sync_stage = fields.Char('Current Sync Stage', help='Current stage of sync process')
    sync_total_records = fields.Integer('Total Records to Process', default=0)
    sync_processed_records = fields.Integer('Processed Records', default=0)
    sync_start_time = fields.Datetime('Sync Start Time')
    sync_estimated_completion = fields.Datetime('Estimated Completion Time')

    # File tracking for incremental sync
    last_synced_files = fields.Text('Last Synced Files', 
        help='JSON mapping of filename -> last_modified_timestamp for incremental sync')
    sync_mode = fields.Selection([
        ('quick', 'Quick Sync (Incremental)'),
        ('full', 'Full Sync (All Files)')
    ], default='quick', string='Sync Mode')

    parts_processed_today = fields.Integer('Parts Processed Today', compute='_compute_daily_stats')
    rejection_rate = fields.Float('Rejection Rate %', compute='_compute_daily_stats')

    # Final Station specific fields
    plc_ip_address = fields.Char('PLC IP Address', help='PLC IP address for final station')
    plc_port = fields.Integer('PLC Port', default=502, help='PLC port for final station')
    camera_ip_address = fields.Char('Camera IP Address', help='Keyence camera IP address')
    camera_port = fields.Integer('Camera Port', default=80, help='Camera port for final station')
    operation_mode = fields.Selection([
        ('auto', 'Auto'),
        ('manual', 'Manual')
    ], default='auto', string='Operation Mode', help='Final station operation mode')
    
        # Final Station status fields
    plc_online = fields.Boolean('PLC Online', compute='_compute_plc_status', store=True)
    last_plc_communication = fields.Datetime('Last PLC Communication')
    part_present = fields.Boolean('Part Present', readonly=True)
    camera_triggered = fields.Boolean('Camera Triggered', readonly=True)
    cylinder_forward = fields.Boolean('Cylinder Forward', readonly=True)
    cylinder_reverse = fields.Boolean('Cylinder Reverse', readonly=True)
    processing_part = fields.Boolean('Processing Part', default=False, help='Flag to prevent multiple triggers')

    # Final Station measurement fields
    last_serial_number = fields.Char('Last Serial Number')
    last_capture_time = fields.Datetime('Last Capture Time')
    last_result = fields.Selection([
        ('ok', 'OK'),
        ('nok', 'NOK'),
        ('pending', 'Pending')
    ], default='pending', string='Last Result')
    
    # Manual control fields
    manual_camera_trigger = fields.Boolean('Manual Camera Trigger', default=False)
    manual_cylinder_forward = fields.Boolean('Manual Cylinder Forward', default=False)
    manual_cylinder_reverse = fields.Boolean('Manual Cylinder Reverse', default=False)
    
    # Final Station Measurements
    measurement_ids = fields.One2many('manufacturing.final.station.measurement', 'machine_id', string='Measurements')
    
    # PLC Monitoring Service fields
    plc_monitoring_active = fields.Boolean('PLC Monitoring Active', default=False, help='Indicates if continuous PLC monitoring is active')
    plc_scan_rate = fields.Float('PLC Scan Rate (seconds)', default=0.1, help='Scan rate for PLC monitoring in seconds')
    last_plc_scan = fields.Datetime('Last PLC Scan', readonly=True)
    plc_monitoring_errors = fields.Integer('PLC Monitoring Errors', default=0, help='Number of consecutive PLC monitoring errors')
    
    # Gauging System Tolerance fields (DMS format)
    gauging_utl_degrees = fields.Integer('UTL Degrees', default=1)
    gauging_utl_minutes = fields.Integer('UTL Minutes', default=30)
    gauging_utl_seconds = fields.Integer('UTL Seconds', default=0)
    gauging_ltl_degrees = fields.Integer('LTL Degrees', default=-1)
    gauging_ltl_minutes = fields.Integer('LTL Minutes', default=30)
    gauging_ltl_seconds = fields.Integer('LTL Seconds', default=0)
    gauging_nominal_degrees = fields.Integer('Nominal Degrees', default=0)
    gauging_nominal_minutes = fields.Integer('Nominal Minutes', default=0)
    gauging_nominal_seconds = fields.Integer('Nominal Seconds', default=0)
    
    # Computed decimal values for internal calculations
    gauging_upper_tolerance = fields.Float('Upper Tolerance Limit (UTL)', digits=(10, 6), 
                                         compute='_compute_gauging_tolerance_decimal', store=True,
                                         help='Upper tolerance limit for gauging measurements in decimal degrees')
    gauging_lower_tolerance = fields.Float('Lower Tolerance Limit (LTL)', digits=(10, 6), 
                                         compute='_compute_gauging_tolerance_decimal', store=True,
                                         help='Lower tolerance limit for gauging measurements in decimal degrees')
    gauging_nominal_value = fields.Float('Nominal Value', digits=(10, 6), 
                                       compute='_compute_gauging_tolerance_decimal', store=True,
                                       help='Nominal value for gauging measurements in decimal degrees')
    
    # Aumann System Tolerance fields (JSON format)
    aumann_intake_tolerances_json = fields.Text('Intake Tolerances JSON (980)', 
                                               help='JSON mapping of field name to [lower, upper] limits for serial prefix 980. Example: {"diameter_journal_a1": [23.959, 23.98]}')
    aumann_exhaust_tolerances_json = fields.Text('Exhaust Tolerances JSON (480)', 
                                                help='JSON mapping of field name to [lower, upper] limits for serial prefix 480. Example: {"diameter_journal_a1": [23.959, 23.98]}')

    @api.depends('gauging_utl_degrees', 'gauging_utl_minutes', 'gauging_utl_seconds',
                 'gauging_ltl_degrees', 'gauging_ltl_minutes', 'gauging_ltl_seconds',
                 'gauging_nominal_degrees', 'gauging_nominal_minutes', 'gauging_nominal_seconds')
    def _compute_gauging_tolerance_decimal(self):
        """Convert DMS values to decimal degrees for tolerance calculations"""
        for record in self:
            # Convert UTL to decimal degrees
            record.gauging_upper_tolerance = record._dms_to_decimal(
                record.gauging_utl_degrees, record.gauging_utl_minutes, record.gauging_utl_seconds
            )
            
            # Convert LTL to decimal degrees
            record.gauging_lower_tolerance = record._dms_to_decimal(
                record.gauging_ltl_degrees, record.gauging_ltl_minutes, record.gauging_ltl_seconds
            )
            
            # Convert Nominal to decimal degrees
            record.gauging_nominal_value = record._dms_to_decimal(
                record.gauging_nominal_degrees, record.gauging_nominal_minutes, record.gauging_nominal_seconds
            )
    
    def _dms_to_decimal(self, degrees, minutes, seconds):
        """Convert degrees, minutes, seconds to decimal degrees"""
        if degrees is None:
            degrees = 0
        if minutes is None:
            minutes = 0
        if seconds is None:
            seconds = 0
            
        # Convert to decimal degrees
        decimal_degrees = abs(degrees) + minutes/60.0 + seconds/3600.0
        if degrees < 0:
            decimal_degrees = -decimal_degrees
            
        return decimal_degrees
    
    def save_aumann_tolerances(self):
        """Save Aumann tolerance JSON to ir.config_parameter"""
        for record in self:
            if record.machine_type == 'aumann':
                try:
                    # Validate and save intake tolerances (980 prefix)
                    if record.aumann_intake_tolerances_json:
                        import json
                        # Validate JSON format
                        json.loads(record.aumann_intake_tolerances_json)
                        # Save to ir.config_parameter
                        self.env['ir.config_parameter'].sudo().set_param(
                            'manufacturing.aumann.intake_tolerances_json',
                            record.aumann_intake_tolerances_json
                        )
                        _logger.info(f"Saved intake tolerances for machine {record.machine_name}")
                    
                    # Validate and save exhaust tolerances (480 prefix)
                    if record.aumann_exhaust_tolerances_json:
                        import json
                        # Validate JSON format
                        json.loads(record.aumann_exhaust_tolerances_json)
                        # Save to ir.config_parameter
                        self.env['ir.config_parameter'].sudo().set_param(
                            'manufacturing.aumann.exhaust_tolerances_json',
                            record.aumann_exhaust_tolerances_json
                        )
                        _logger.info(f"Saved exhaust tolerances for machine {record.machine_name}")
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Success',
                            'message': 'Aumann tolerances saved successfully!',
                            'type': 'success',
                        }
                    }
                    
                except json.JSONDecodeError as e:
                    _logger.error(f"Invalid JSON format in Aumann tolerances: {e}")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Error',
                            'message': f'Invalid JSON format: {str(e)}',
                            'type': 'danger',
                        }
                    }
                except Exception as e:
                    _logger.error(f"Error saving Aumann tolerances: {e}")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Error',
                            'message': f'Error saving tolerances: {str(e)}',
                            'type': 'danger',
                        }
                    }
    
    def load_aumann_tolerances(self):
        """Load Aumann tolerance JSON from ir.config_parameter"""
        for record in self:
            if record.machine_type == 'aumann':
                # Load intake tolerances (980 prefix)
                intake_tolerances = self.env['ir.config_parameter'].sudo().get_param(
                    'manufacturing.aumann.intake_tolerances_json', ''
                )
                record.aumann_intake_tolerances_json = intake_tolerances
                
                # Load exhaust tolerances (480 prefix)
                exhaust_tolerances = self.env['ir.config_parameter'].sudo().get_param(
                    'manufacturing.aumann.exhaust_tolerances_json', ''
                )
                record.aumann_exhaust_tolerances_json = exhaust_tolerances
                
                _logger.info(f"Loaded Aumann tolerances for machine {record.machine_name}")
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to load tolerances for Aumann machines"""
        records = super().create(vals_list)
        for record in records:
            if record.machine_type == 'aumann':
                record.load_aumann_tolerances()
        return records
    
    def write(self, vals):
        """Override write to load tolerances for Aumann machines"""
        result = super().write(vals)
        for record in self:
            if record.machine_type == 'aumann' and 'machine_type' in vals:
                record.load_aumann_tolerances()
        return result

    @api.onchange('manual_cylinder_forward')
    def _onchange_manual_cylinder_forward(self):
        """If toggled in UI, send a 1s pulse on D3 (1 then 0)."""
        for rec in self:
            if rec.machine_type != 'final_station' or not rec.manual_cylinder_forward:
                continue
            try:
                if rec._write_plc_register(3, 1):
                    _logger.info("Onchange: D3=1 (forward)")
                    import time
                    time.sleep(1)
                    rec._write_plc_register(3, 0)
                    _logger.info("Onchange: D3 reset to 0")
                rec.manual_cylinder_forward = False
                rec.cylinder_forward = False
                rec.cylinder_reverse = False
            except Exception as e:
                _logger.error(f"Onchange manual_cylinder_forward error: {str(e)}")

    @api.onchange('manual_cylinder_reverse')
    def _onchange_manual_cylinder_reverse(self):
        """If toggled in UI, send a 1s pulse on D4 (1 then 0)."""
        for rec in self:
            if rec.machine_type != 'final_station' or not rec.manual_cylinder_reverse:
                continue
            try:
                if rec._write_plc_register(4, 1):
                    _logger.info("Onchange: D4=1 (reverse)")
                    import time
                    time.sleep(1)
                    rec._write_plc_register(4, 0)
                    _logger.info("Onchange: D4 reset to 0")
                rec.manual_cylinder_reverse = False
                rec.cylinder_reverse = False
                rec.cylinder_forward = False
            except Exception as e:
                _logger.error(f"Onchange manual_cylinder_reverse error: {str(e)}")

    @api.onchange('operation_mode')
    def _onchange_operation_mode_sync_plc(self):
        """When user changes mode in UI, also write D2 on PLC."""
        for rec in self:
            if rec.machine_type != 'final_station' or not rec.plc_ip_address or not rec.plc_port:
                continue
            try:
                d2_value = 1 if rec.operation_mode == 'manual' else 0
                ok = rec._write_plc_register(2, d2_value)
                if ok:
                    _logger.info(f"Onchange: Synced operation mode to PLC D2={d2_value} for {rec.machine_name}")
                else:
                    _logger.warning(f"Onchange: Failed syncing operation mode to PLC for {rec.machine_name}")
            except Exception as e:
                _logger.error(f"Onchange operation_mode PLC sync error: {str(e)}")

    def write(self, vals):
        """Ensure PLC D2 matches operation_mode when saved from form."""
        res = super().write(vals)
        try:
            if 'operation_mode' in vals:
                for rec in self:
                    if rec.machine_type != 'final_station' or not rec.plc_ip_address or not rec.plc_port:
                        continue
                    d2_value = 1 if rec.operation_mode == 'manual' else 0
                    ok = rec._write_plc_register(2, d2_value)
                    if ok:
                        _logger.info(f"Write: Synced operation mode to PLC D2={d2_value} for {rec.machine_name}")
                    else:
                        _logger.warning(f"Write: Failed syncing operation mode to PLC for {rec.machine_name}")
        except Exception as e:
            _logger.error(f"Write operation_mode PLC sync error: {str(e)}")
        return res

    @api.depends('last_plc_communication')
    def _compute_plc_status(self):
        """Compute PLC online status for final stations"""
        for record in self:
            if record.machine_type == 'final_station':
                if record.last_plc_communication and (datetime.now() - record.last_plc_communication).total_seconds() < 60:
                    record.plc_online = True
                else:
                    record.plc_online = False
            else:
                record.plc_online = False

    @api.depends('machine_type')
    def _compute_daily_stats(self):
        for record in self:
            today = fields.Date.today()
            parts = self.env['manufacturing.part.quality'].browse()

            if record.machine_type == 'vici_vision':
                vici_parts = self.env['manufacturing.vici.vision'].search([
                    ('machine_id', '=', record.id),
                    ('test_date', '>=', today)
                ])
                # Update part quality records
                for vici_part in vici_parts:
                    part_quality = self.env['manufacturing.part.quality'].search([
                        ('serial_number', '=', vici_part.serial_number)
                    ], limit=1)
                    if part_quality:
                        parts |= part_quality

            elif record.machine_type == 'ruhlamat':
                ruhlamat_parts = self.env['manufacturing.ruhlamat.press'].search([
                    ('machine_id', '=', record.id),
                    ('test_date', '>=', today)
                ])
                for ruhlamat_part in ruhlamat_parts:
                    part_quality = self.env['manufacturing.part.quality'].search([
                        ('serial_number', '=', ruhlamat_part.part_id1)
                    ], limit=1)
                    if part_quality:
                        parts |= part_quality

            elif record.machine_type == 'gauging':
                gauging_parts = self.env['manufacturing.gauging.measurement'].search([
                    ('machine_id', '=', record.id),
                    ('test_date', '>=', today)
                ])
                for gauging_part in gauging_parts:
                    part_quality = self.env['manufacturing.part.quality'].search([
                        ('serial_number', '=', gauging_part.serial_number)
                    ], limit=1)
                    if part_quality:
                        parts |= part_quality

            elif record.machine_type == 'aumann':
                aumann_parts = self.env['manufacturing.aumann.measurement'].search([
                    ('machine_id', '=', record.id),
                    ('test_date', '>=', today)
                ])
                for aumann_part in aumann_parts:
                    part_quality = self.env['manufacturing.part.quality'].search([
                        ('serial_number', '=', aumann_part.serial_number)
                    ], limit=1)
                    if part_quality:
                        parts |= part_quality

            record.parts_processed_today = len(parts)
            rejected_parts = parts.filtered(lambda p: p.final_result == 'reject')
            record.rejection_rate = (len(rejected_parts) / len(parts)) * 100 if parts else 0

    @api.model
    def sync_all_machines(self):
        """Optimized cron job method to sync all active machines in parallel"""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        # Get all active machines
        machines = self.search([('is_active', '=', True)])
        if not machines:
            _logger.info("No active machines to sync")
            return
            
        now_dt = fields.Datetime.now()
        machines_to_sync = []
        
        # Pre-filter machines that need syncing
        for machine in machines:
            try:
                should_sync = False
                if not machine.last_sync:
                    should_sync = True
                else:
                    try:
                        # Compute elapsed seconds since last sync
                        elapsed = (now_dt - machine.last_sync).total_seconds()
                        should_sync = elapsed >= (machine.sync_interval or 0)
                    except Exception:
                        # Fallback to syncing if comparison fails
                        should_sync = True

                if should_sync:
                    machines_to_sync.append(machine)
                else:
                    _logger.debug(
                        f"Skipping sync for {machine.machine_name}; next in {(machine.sync_interval or 0) - int((now_dt - machine.last_sync).total_seconds())}s"
                    )
            except Exception as e:
                _logger.error(f"Error checking sync status for machine {machine.machine_name}: {str(e)}")
        
        if not machines_to_sync:
            _logger.info("No machines need syncing at this time")
            return
            
        _logger.info(f"Starting parallel sync for {len(machines_to_sync)} machines")
        start_time = time.time()
        
        # Use ThreadPoolExecutor for parallel processing
        # Dynamic worker count based on machine types and system load
        max_workers = self._calculate_optimal_workers(machines_to_sync)
        
        _logger.info(f"Using {max_workers} workers for parallel sync")
        
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="MachineSync") as executor:
            # Submit all sync tasks
            future_to_machine = {
                executor.submit(self._sync_machine_async, machine): machine 
                for machine in machines_to_sync
            }
            
            # Process completed tasks
            completed_count = 0
            for future in as_completed(future_to_machine):
                machine = future_to_machine[future]
                completed_count += 1
                try:
                    result = future.result()
                    _logger.info(f"[{completed_count}/{len(machines_to_sync)}] Completed sync for {machine.machine_name}: {result}")
                except Exception as e:
                    _logger.error(f"[{completed_count}/{len(machines_to_sync)}] Error syncing machine {machine.machine_name}: {str(e)}")
        
        total_time = time.time() - start_time
        _logger.info(f"All machine syncs completed in {total_time:.2f}s (avg: {total_time/len(machines_to_sync):.2f}s per machine)")

    def _calculate_optimal_workers(self, machines_to_sync):
        """Calculate optimal number of workers based on machine types and system load"""
        # Base calculation
        total_machines = len(machines_to_sync)
        
        # Count machine types for optimization
        final_stations = sum(1 for m in machines_to_sync if m.machine_type == 'final_station')
        heavy_machines = sum(1 for m in machines_to_sync if m.machine_type in ['ruhlamat', 'gauging'])
        light_machines = sum(1 for m in machines_to_sync if m.machine_type in ['vici_vision', 'aumann'])
        
        # Calculate optimal workers
        if total_machines <= 2:
            return total_machines  # All machines can run simultaneously
        elif total_machines <= 4:
            return min(total_machines, 3)  # Max 3 for small sets
        elif heavy_machines > 0:
            return min(total_machines, 4)  # Limit for heavy operations
        else:
            return min(total_machines, 6)  # More workers for light operations

    def _sync_machine_async(self, machine):
        """Async wrapper for machine sync with proper database handling"""
        try:
            # Create a new database cursor for this thread
            with self.env.registry.cursor() as new_cr:
                new_env = api.Environment(new_cr, self.env.uid, self.env.context)
                machine_record = new_env['manufacturing.machine.config'].browse(machine.id)
                
                if machine_record.exists():
                    result = machine_record.sync_machine_data_optimized()
                    new_cr.commit()
                    return result
                else:
                    return f"Machine {machine.machine_name} not found"
        except Exception as e:
            _logger.error(f"Error in async sync for {machine.machine_name}: {str(e)}")
            return f"Error: {str(e)}"

    @api.model
    def force_sync_all_machines(self):
        """Force sync all active machines immediately, ignoring sync intervals"""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        _logger.info("=== FORCE SYNC ALL MACHINES ===")
        
        # Get all active machines
        machines = self.search([('is_active', '=', True)])
        if not machines:
            _logger.info("No active machines to force sync")
            return "No active machines found"
            
        _logger.info(f"Force syncing {len(machines)} machines simultaneously")
        start_time = time.time()
        
        # Use maximum workers for force sync
        max_workers = min(len(machines), 6)  # Allow more workers for force sync
        
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ForceSync") as executor:
            # Submit all sync tasks
            future_to_machine = {
                executor.submit(self._sync_machine_async, machine): machine 
                for machine in machines
            }
            
            # Process completed tasks
            completed_count = 0
            results = []
            for future in as_completed(future_to_machine):
                machine = future_to_machine[future]
                completed_count += 1
                try:
                    result = future.result()
                    results.append(f"{machine.machine_name}: {result}")
                    _logger.info(f"[{completed_count}/{len(machines)}] Force sync completed for {machine.machine_name}")
                except Exception as e:
                    results.append(f"{machine.machine_name}: ERROR - {str(e)}")
                    _logger.error(f"[{completed_count}/{len(machines)}] Force sync error for {machine.machine_name}: {str(e)}")
        
        total_time = time.time() - start_time
        summary = f"Force sync completed in {total_time:.2f}s for {len(machines)} machines"
        _logger.info(f"=== {summary} ===")
        
        return {
            'summary': summary,
            'total_machines': len(machines),
            'total_time': total_time,
            'avg_time_per_machine': total_time / len(machines),
            'results': results
        }

    @api.model
    def get_sync_status(self):
        """Get current sync status for all machines"""
        machines = self.search([('is_active', '=', True)])
        now_dt = fields.Datetime.now()
        
        status_info = {
            'total_machines': len(machines),
            'active_machines': 0,
            'needs_sync': 0,
            'last_sync_times': {},
            'sync_intervals': {},
            'machine_status': {}
        }
        
        for machine in machines:
            status_info['active_machines'] += 1
            status_info['machine_status'][machine.machine_name] = machine.status
            status_info['sync_intervals'][machine.machine_name] = machine.sync_interval
            
            if machine.last_sync:
                elapsed = (now_dt - machine.last_sync).total_seconds()
                status_info['last_sync_times'][machine.machine_name] = {
                    'last_sync': machine.last_sync.isoformat(),
                    'elapsed_seconds': elapsed,
                    'needs_sync': elapsed >= (machine.sync_interval or 0)
                }
                if elapsed >= (machine.sync_interval or 0):
                    status_info['needs_sync'] += 1
            else:
                status_info['last_sync_times'][machine.machine_name] = {
                    'last_sync': None,
                    'elapsed_seconds': None,
                    'needs_sync': True
                }
                status_info['needs_sync'] += 1
        
        return status_info

    def force_sync_all_machines(self):
        """Button method to force sync all machines with user feedback"""
        result = self.env['manufacturing.machine.config'].force_sync_all_machines()
        
        if isinstance(result, dict):
            message = f"Force sync completed!\n\n"
            message += f"Total machines: {result['total_machines']}\n"
            message += f"Total time: {result['total_time']:.2f}s\n"
            message += f"Average per machine: {result['avg_time_per_machine']:.2f}s\n\n"
            message += "Results:\n" + "\n".join(result['results'])
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Force Sync Complete',
                    'message': message,
                    'type': 'success',
                    'sticky': True,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Force Sync Result',
                    'message': str(result),
                    'type': 'info',
                    'sticky': True,
                }
            }

    def sync_machine_data(self):
        """Sync data from CSV file based on machine type (legacy method)"""
        return self.sync_machine_data_optimized()

    def sync_machine_data_optimized(self):
        """Optimized sync data from CSV file based on machine type"""
        import time
        
        # For final stations, we don't sync CSV data - they use PLC monitoring
        if self.machine_type == 'final_station':
            # Final stations only update their status, not CSV data
            self.last_sync = fields.Datetime.now()
            self.status = 'running'
            return f"Final station status updated (PLC monitoring active: {self.plc_monitoring_active})"
        
        # Check if CSV file exists for other machine types (Aumann may provide multiple paths; handled inside its sync)
        if self.machine_type != 'aumann' and not os.path.exists(self.csv_file_path):
            _logger.warning(f"CSV file not found: {self.csv_file_path}")
            self.status = 'error'
            return f"CSV file not found: {self.csv_file_path}"

        try:
            _logger.info(f"Starting optimized sync for {self.machine_name} ({self.machine_type})")
            start_time = time.time()
            
            if self.machine_type == 'vici_vision':
                result = self._sync_vici_data_optimized()
            elif self.machine_type == 'ruhlamat':
                result = self._sync_ruhlamat_data_optimized()
            elif self.machine_type == 'gauging':
                result = self._sync_gauging_data_optimized()
            elif self.machine_type == 'aumann':
                result = self._sync_aumann_data_optimized()
            else:
                result = f"Unknown machine type: {self.machine_type}"

            # Update status and timing
            self.last_sync = fields.Datetime.now()
            self.status = 'running'
            
            sync_duration = time.time() - start_time
            _logger.info(f"Completed sync for {self.machine_name} in {sync_duration:.2f}s: {result}")
            
            return result
            
        except Exception as e:
            _logger.error(f"Error syncing {self.machine_name}: {str(e)}")
            self.status = 'error'
            return f"Error: {str(e)}"

    def force_full_sync(self):
        """Force a full sync of all files regardless of modification time"""
        self.ensure_one()
        
        # Check if sync_mode field exists
        if not hasattr(self, 'sync_mode'):
            # If field doesn't exist, just run normal sync (will process all files)
            result = self.sync_machine_data_optimized()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Full Sync Complete',
                    'message': f'Full sync completed: {result}',
                    'type': 'success',
                    'sticky': False,
                }
            }
        
        # Temporarily set sync mode to full
        original_mode = self.sync_mode
        self.sync_mode = 'full'
        
        try:
            result = self.sync_machine_data_optimized()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Full Sync Complete',
                    'message': f'Full sync completed: {result}',
                    'type': 'success',
                    'sticky': False,
                }
            }
        finally:
            # Restore original mode
            self.sync_mode = original_mode

    def cancel_current_sync(self):
        """Cancel the current sync operation and reset status"""
        self.ensure_one()
        
        self.status = 'stopped'
        self.sync_progress = 0.0
        self.sync_stage = "Sync cancelled by user"
        self.sync_processed_records = 0
        self.sync_total_records = 0
        self.env.cr.commit()
        
        _logger.info(f"Sync cancelled for machine: {self.machine_name}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Cancelled',
                'message': f'Sync operation cancelled for {self.machine_name}',
                'type': 'warning',
                'sticky': False,
            }
        }

    def _sync_vici_data(self):
        """Sync VICI Vision system data using multi-row CSV (header + nominal/tolerances)."""
        try:
            if not os.path.exists(self.csv_file_path):
                _logger.error(f"VICI CSV file not found: {self.csv_file_path}")
                return

            with open(self.csv_file_path, 'r', encoding='utf-8-sig', newline='') as file:
                reader = csv.reader(file)
                rows = list(reader)

                if len(rows) < 7:
                    _logger.warning(f"VICI CSV seems too short (rows={len(rows)}). Path: {self.csv_file_path}")
                    return

                header = rows[0]
                nominal_row = rows[3]
                lower_row = rows[4]
                upper_row = rows[5]

                # Map CSV measurement names to Odoo field names
                field_map = {
                    'L 64.8': 'l_64_8',
                    'L 35.4': 'l_35_4',
                    'L 46.6': 'l_46_6',
                    'L 82': 'l_82',
                    'L 128.6': 'l_128_6',
                    'L 164': 'l_164',
                    'Runout E31-E22': 'runout_e31_e22',
                    'Runout E21-E12': 'runout_e21_e12',
                    'Runout E11 tube end': 'runout_e11_tube_end',
                    'Angular difference E32-E12 pos tool': 'ang_diff_e32_e12_pos_tool',
                    'Angular difference E31-E12 pos tool': 'ang_diff_e31_e12_pos_tool',
                    'Angular difference E22-E12 pos tool': 'ang_diff_e22_e12_pos_tool',
                    'Angular difference E21-E12 pos tool': 'ang_diff_e21_e12_pos_tool',
                    'Angular difference E11-E12 pos tool': 'ang_diff_e11_e12_pos_tool',
                }

                def parse_float(val):
                    try:
                        return float(val) if val not in (None, '',) else None
                    except Exception:
                        try:
                            return float(str(val).replace(',', '.'))
                        except Exception:
                            return None

                # Build nominal/tolerance lookups by column index
                col_to_nominal = {}
                col_to_tol_low = {}
                col_to_tol_high = {}
                for idx, name in enumerate(header):
                    if name in field_map:
                        col_to_nominal[idx] = parse_float(nominal_row[idx] if idx < len(nominal_row) else None)
                        col_to_tol_low[idx] = parse_float(lower_row[idx] if idx < len(lower_row) else None)
                        col_to_tol_high[idx] = parse_float(upper_row[idx] if idx < len(upper_row) else None)

                def within(n, lo, hi, val):
                    if val is None or n is None or lo is None or hi is None:
                        return True
                    return (n + lo) <= val <= (n + hi)

                def parse_dt(date_str_val, time_str_val):
                    import pytz
                    for fmt in ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                        try:
                            # Parse the datetime string
                            parsed_dt = datetime.strptime(f"{date_str_val} {time_str_val}", fmt)
                            
                            # Since CSV contains IST time, we need to treat it as IST and convert to UTC
                            # for Odoo to store correctly, then it will display back as IST
                            ist = pytz.timezone('Asia/Kolkata')
                            ist_dt = ist.localize(parsed_dt)
                            utc_dt = ist_dt.astimezone(pytz.UTC)
                            
                            # Return in UTC format for Odoo storage
                            return utc_dt.strftime('%Y-%m-%d %H:%M:%S')
                        except Exception:
                            continue
                    return None

                created = 0
                for row in rows[6:]:
                    if not row or len(row) < 7:
                        continue

                    date_str = row[0].strip() if len(row) > 0 else ''
                    time_str = row[1].strip() if len(row) > 1 else ''
                    operator = row[2].strip() if len(row) > 2 else ''
                    batch_sn = row[3].strip() if len(row) > 3 else ''
                    measure_number = row[4].strip() if len(row) > 4 else ''
                    measure_state = row[5].strip() if len(row) > 5 else ''
                    serial = row[6].strip() if len(row) > 6 else ''

                    if not serial:
                        continue

                    # Avoid duplicates for same machine/serial
                    exists = self.env['manufacturing.vici.vision'].search([
                        ('serial_number', '=', serial),
                        ('machine_id', '=', self.id)
                    ], limit=1)
                    if exists:
                        continue

                    # Parse datetime strictly (accept DD-MM-YYYY or DD/MM/YYYY); skip if invalid
                    if not date_str or not time_str:
                        _logger.warning(f"Skipping VICI row due to missing date/time. Row: {row}")
                        continue
                    test_date = parse_dt(date_str, time_str)
                    if not test_date:
                        _logger.warning(f"Skipping VICI row due to invalid date/time '{date_str} {time_str}'. Row: {row}")
                        continue

                    vals = {
                        'serial_number': serial,
                        'machine_id': self.id,
                        'test_date': test_date,
                        'log_date': test_date.date(),
                        'log_time': time_str or test_date.strftime("%H:%M:%S"),
                        'operator_name': operator,
                        'batch_serial_number': batch_sn,
                        'measure_number': int(measure_number) if measure_number.isdigit() else None,
                        'measure_state': int(measure_state) if measure_state.isdigit() else None,
                        'raw_data': ','.join(row)[:2000],
                    }
                    
                    failed = []
                    # Fill measurement and tolerance fields
                    for idx, name in enumerate(header):
                        if name in field_map and idx < len(row):
                            field_name = field_map[name]
                            value = parse_float(row[idx])
                            vals[field_name] = value
                            n = col_to_nominal.get(idx)
                            lo = col_to_tol_low.get(idx)
                            hi = col_to_tol_high.get(idx)
                            vals[f"{field_name}_nominal"] = n
                            vals[f"{field_name}_tol_low"] = lo
                            vals[f"{field_name}_tol_high"] = hi
                            if not within(n, lo, hi, value):
                                failed.append(name)

                    vals['result'] = 'pass' if not failed else 'reject'
                    vals['rejection_reason'] = False if not failed else 'Out of tolerance: ' + ', '.join(failed)
                    vals['failed_fields'] = False if not failed else ', '.join(failed)

                    try:
                        self.env['manufacturing.vici.vision'].create(vals)
                        created += 1
                    except Exception as e:
                        _logger.error(f"Failed to create VICI record for SN {serial}: {e}")

                _logger.info(f"VICI sync created {created} records for machine {self.machine_name}")
        except Exception as e:
            _logger.error(f"Error syncing VICI data: {str(e)}")
            raise

    def _sync_vici_data_optimized(self):
        """Optimized VICI Vision system data sync with batch processing"""
        try:
            if not os.path.exists(self.csv_file_path):
                _logger.error(f"VICI CSV file not found: {self.csv_file_path}")
                return "CSV file not found"

            # Quick sync: check if file was modified since last sync
            force_full_sync = (hasattr(self, 'sync_mode') and self.sync_mode == 'full')
            if not self._should_process_file(self.csv_file_path, force_full_sync):
                _logger.info(f"VICI CSV file not modified since last sync, skipping")
                return "No changes detected"

            with open(self.csv_file_path, 'r', encoding='utf-8-sig', newline='') as file:
                reader = csv.reader(file)
                rows = list(reader)

                if len(rows) < 7:
                    _logger.warning(f"VICI CSV seems too short (rows={len(rows)}). Path: {self.csv_file_path}")
                    return f"CSV too short: {len(rows)} rows"

                header = rows[0]
                nominal_row = rows[3]
                lower_row = rows[4]
                upper_row = rows[5]

                # Map CSV measurement names to Odoo field names
                field_map = {
                    'L 64.8': 'l_64_8',
                    'L 35.4': 'l_35_4',
                    'L 46.6': 'l_46_6',
                    'L 82': 'l_82',
                    'L 128.6': 'l_128_6',
                    'L 164': 'l_164',
                    'Runout E31-E22': 'runout_e31_e22',
                    'Runout E21-E12': 'runout_e21_e12',
                    'Runout E11 tube end': 'runout_e11_tube_end',
                    'Angular difference E32-E12 pos tool': 'ang_diff_e32_e12_pos_tool',
                    'Angular difference E31-E12 pos tool': 'ang_diff_e31_e12_pos_tool',
                    'Angular difference E22-E12 pos tool': 'ang_diff_e22_e12_pos_tool',
                    'Angular difference E21-E12 pos tool': 'ang_diff_e21_e12_pos_tool',
                    'Angular difference E11-E12 pos tool': 'ang_diff_e11_e12_pos_tool',
                }

                def parse_float(val):
                    try:
                        return float(val) if val not in (None, '',) else None
                    except Exception:
                        try:
                            return float(str(val).replace(',', '.'))
                        except Exception:
                            return None

                # Build nominal/tolerance lookups by column index
                col_to_nominal = {}
                col_to_tol_low = {}
                col_to_tol_high = {}
                for idx, name in enumerate(header):
                    if name in field_map:
                        col_to_nominal[idx] = parse_float(nominal_row[idx] if idx < len(nominal_row) else None)
                        col_to_tol_low[idx] = parse_float(lower_row[idx] if idx < len(lower_row) else None)
                        col_to_tol_high[idx] = parse_float(upper_row[idx] if idx < len(upper_row) else None)

                def within(n, lo, hi, val):
                    if val is None or n is None or lo is None or hi is None:
                        return True
                    return (n + lo) <= val <= (n + hi)

                def parse_dt(date_str_val, time_str_val):
                    import pytz
                    for fmt in ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                        try:
                            parsed_dt = datetime.strptime(f"{date_str_val} {time_str_val}", fmt)
                            ist = pytz.timezone('Asia/Kolkata')
                            ist_dt = ist.localize(parsed_dt)
                            utc_dt = ist_dt.astimezone(pytz.UTC)
                            return utc_dt.strftime('%Y-%m-%d %H:%M:%S')
                        except Exception:
                            continue
                    return None

                # Batch processing: collect all records first, then create in batches
                records_to_create = []
                existing_serials = set()
                
                # Get existing serials to avoid duplicates (batch query)
                existing_records = self.env['manufacturing.vici.vision'].search([
                    ('machine_id', '=', self.id)
                ])
                existing_serials = set(existing_records.mapped('serial_number'))

                for row in rows[6:]:
                    if not row or len(row) < 7:
                        continue

                    date_str = row[0].strip() if len(row) > 0 else ''
                    time_str = row[1].strip() if len(row) > 1 else ''
                    operator = row[2].strip() if len(row) > 2 else ''
                    batch_sn = row[3].strip() if len(row) > 3 else ''
                    measure_number = row[4].strip() if len(row) > 4 else ''
                    measure_state = row[5].strip() if len(row) > 5 else ''
                    serial = row[6].strip() if len(row) > 6 else ''

                    if not serial or serial in existing_serials:
                        continue

                    # Parse datetime
                    if not date_str or not time_str:
                        continue
                    test_date = parse_dt(date_str, time_str)
                    if not test_date:
                        continue

                    vals = {
                        'serial_number': serial,
                        'machine_id': self.id,
                        'test_date': test_date,
                        'log_date': test_date.date(),
                        'log_time': time_str or test_date.strftime("%H:%M:%S"),
                        'operator_name': operator,
                        'batch_serial_number': batch_sn,
                        'measure_number': int(measure_number) if measure_number.isdigit() else None,
                        'measure_state': int(measure_state) if measure_state.isdigit() else None,
                        'raw_data': ','.join(row)[:2000],
                    }
                    
                    failed = []
                    # Fill measurement and tolerance fields
                    for idx, name in enumerate(header):
                        if name in field_map and idx < len(row):
                            field_name = field_map[name]
                            value = parse_float(row[idx])
                            vals[field_name] = value
                            n = col_to_nominal.get(idx)
                            lo = col_to_tol_low.get(idx)
                            hi = col_to_tol_high.get(idx)
                            vals[f"{field_name}_nominal"] = n
                            vals[f"{field_name}_tol_low"] = lo
                            vals[f"{field_name}_tol_high"] = hi
                            if not within(n, lo, hi, value):
                                failed.append(name)

                    vals['result'] = 'pass' if not failed else 'reject'
                    vals['rejection_reason'] = False if not failed else 'Out of tolerance: ' + ', '.join(failed)
                    vals['failed_fields'] = False if not failed else ', '.join(failed)

                    records_to_create.append(vals)

                # Batch create records (much faster than individual creates)
                if records_to_create:
                    # Create in batches of 100 to avoid memory issues
                    batch_size = 100
                    total_created = 0
                    
                    for i in range(0, len(records_to_create), batch_size):
                        batch = records_to_create[i:i + batch_size]
                        try:
                            self.env['manufacturing.vici.vision'].create(batch)
                            total_created += len(batch)
                        except Exception as e:
                            _logger.error(f"Failed to create VICI batch {i//batch_size + 1}: {e}")
                            # Try individual creates for this batch
                            for record in batch:
                                try:
                                    self.env['manufacturing.vici.vision'].create(record)
                                    total_created += 1
                                except Exception as e2:
                                    _logger.error(f"Failed to create VICI record for SN {record.get('serial_number', 'unknown')}: {e2}")

                    # Track processed file
                    self._update_synced_files(self.csv_file_path, os.path.getmtime(self.csv_file_path))
                    return f"Created {total_created} VICI records"
                else:
                    return "No new VICI records to create"

        except Exception as e:
            _logger.error(f"Error syncing VICI data: {str(e)}")
            return f"Error: {str(e)}"


    # You'll need to install pyodbc: pip install pyodbc
    # Or use pypyodbc as an alternative: pip install pypyodbc
    def _sync_ruhlamat_data(self):
        """Sync Ruhlamat Press system data from MDB file"""
        _logger.info(f"Starting Ruhlamat MDB sync for machine: {self.machine_name}")
        
        # Initialize progress tracking
        self.sync_start_time = fields.Datetime.now()
        self.sync_progress = 0.0
        self.sync_stage = "Initializing sync process"
        self.sync_processed_records = 0
        self.sync_total_records = 0
        self.env.cr.commit()

        try:
            # Check if file exists
            if not os.path.exists(
                    self.csv_file_path):  # Note: You should rename this field to 'file_path' since it's not CSV anymore
                _logger.error(f"MDB file not found: {self.csv_file_path}")
                self.status = 'error'
                self.sync_stage = "Error: File not found"
                return

            # Connect to MDB file using ODBC
            # For Windows, use Microsoft Access Driver
            # For Linux, you might need to use mdbtools or convert to SQLite

            # Windows connection string
            conn_str = (
                r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                f'DBQ={self.csv_file_path};'
            )

            # Alternative for 64-bit systems
            # conn_str = (
            #     r'DRIVER={Microsoft Access Driver (*.mdb)};'
            #     f'DBQ={self.csv_file_path};'
            # )

            try:
                # Update progress: Connecting to database
                self.sync_stage = "Connecting to MDB database"
                self.sync_progress = 5.0
                self.env.cr.commit()
                _logger.info(f"Connecting to MDB database: {self.csv_file_path}")
                
                conn = pyodbc.connect(conn_str)
                cursor = conn.cursor()

                # Update progress: Querying cycles
                self.sync_stage = "Querying cycles from database"
                self.sync_progress = 10.0
                self.env.cr.commit()
                _logger.info("Querying cycles from MDB database...")

                # First, fetch all cycles
                cycles_query = """
                    SELECT CycleId, ProgramName, CycleDate, ProgramId, StationId, 
                           StationName, StationLabel, PartId1, PartId2, PartId3, 
                           PartId4, PartId5, OK, CycleStatus, UfmUsername, 
                           CycleRuntimeNC, CycleRuntimePC, NcRuntimeCycleNo, 
                           NcTotalCycleNo, ProgramDate, UfmVersion, UfmServiceInfo,
                           CustomInt1, CustomInt2, CustomInt3, CustomString1, 
                           CustomString2, CustomString3, CustomXml
                    FROM Cycles
                    ORDER BY CycleDate DESC
                """

                cursor.execute(cycles_query)
                cycles = cursor.fetchall()
                
                # Update progress: Got cycles count
                total_cycles = len(cycles)
                self.sync_total_records = total_cycles
                self.sync_stage = f"Processing {total_cycles} cycles"
                self.sync_progress = 15.0
                self.env.cr.commit()
                _logger.info(f"Found {total_cycles} cycles to process")

                created_cycles = 0
                created_gaugings = 0

                for cycle_index, cycle_row in enumerate(cycles):
                    # Update progress for cycle processing
                    cycle_progress = 15.0 + (cycle_index / total_cycles) * 70.0  # 15-85% for cycles
                    self.sync_progress = cycle_progress
                    self.sync_processed_records = cycle_index + 1
                    self.sync_stage = f"Processing cycle {cycle_index + 1} of {total_cycles}"
                    
                    # Commit progress every 10 cycles or at the end
                    if cycle_index % 10 == 0 or cycle_index == total_cycles - 1:
                        self.env.cr.commit()
                        _logger.info(f"Progress: {cycle_progress:.1f}% - Processing cycle {cycle_index + 1}/{total_cycles}")
                    
                    # Parse the cycle data
                    cycle_data = {
                        'cycle_id': cycle_row.CycleId,
                        'program_name': cycle_row.ProgramName,
                        'cycle_date': cycle_row.CycleDate,
                        'program_id': cycle_row.ProgramId,
                        'station_id': str(cycle_row.StationId) if cycle_row.StationId else '',
                        'station_name': cycle_row.StationName or '',
                        'station_label': cycle_row.StationLabel or '',
                        'part_id1': cycle_row.PartId1.strip() if cycle_row.PartId1 else '',
                        'part_id2': cycle_row.PartId2 or '',
                        'part_id3': cycle_row.PartId3 or '',
                        'part_id4': cycle_row.PartId4 or '',
                        'part_id5': cycle_row.PartId5 or '',
                        'ok_status': cycle_row.OK,
                        'cycle_status': cycle_row.CycleStatus,
                        'ufm_username': cycle_row.UfmUsername or '',
                        'cycle_runtime_nc': float(cycle_row.CycleRuntimeNC or 0),
                        'cycle_runtime_pc': float(cycle_row.CycleRuntimePC or 0),
                        'nc_runtime_cycle_no': cycle_row.NcRuntimeCycleNo or 0,
                        'nc_total_cycle_no': cycle_row.NcTotalCycleNo or 0,
                        'program_date': cycle_row.ProgramDate,
                        'ufm_version': cycle_row.UfmVersion or 0,
                        'ufm_service_info': cycle_row.UfmServiceInfo or 0,
                        'custom_int1': cycle_row.CustomInt1 or 0,
                        'custom_int2': cycle_row.CustomInt2 or 0,
                        'custom_int3': cycle_row.CustomInt3 or 0,
                        'custom_string1': cycle_row.CustomString1 or '',
                        'custom_string2': cycle_row.CustomString2 or '',
                        'custom_string3': cycle_row.CustomString3 or '',
                        'custom_xml': cycle_row.CustomXml or '',
                        'machine_id': self.id,
                    }

                    # Skip if cycle already exists
                    existing_cycle = self.env['manufacturing.ruhlamat.press'].search([
                        ('cycle_id', '=', cycle_row.CycleId),
                        ('machine_id', '=', self.id)
                    ], limit=1)

                    if not existing_cycle:
                        # Create the cycle record
                        cycle_record = self.env['manufacturing.ruhlamat.press'].create(cycle_data)
                        created_cycles += 1

                        # Update progress: Fetching gaugings for cycle
                        self.sync_stage = f"Fetching gaugings for cycle {cycle_index + 1}"
                        self.env.cr.commit()
                        
                        # Now fetch related gaugings for this cycle
                        gaugings_query = """
                            SELECT GaugingId, CycleId, ProgramName, CycleDate, GaugingNo,
                                   GaugingType, Anchor, OK, GaugingStatus, ActualX, 
                                   SignalXUnit, ActualY, SignalYUnit, LimitTesting,
                                   StartX, EndX, UpperLimit, LowerLimit, RunningNo,
                                   GaugingAlias, SignalXName, SignalYName, SignalXId,
                                   SignalYId, AbsOffsetX, AbsOffsetY, EdgeTypeBottom,
                                   EdgeTypeLeft, EdgeTypeRight, EdgeTypeTop, FromStepData,
                                   StepNo, LastStep
                            FROM Gaugings
                            WHERE CycleId = ?
                            ORDER BY GaugingNo
                        """

                        cursor.execute(gaugings_query, (cycle_row.CycleId,))
                        gaugings = cursor.fetchall()
                        
                        # Log gauging count for this cycle
                        if gaugings:
                            _logger.info(f"Found {len(gaugings)} gaugings for cycle {cycle_row.CycleId}")

                        for gauging_index, gauging_row in enumerate(gaugings):
                            gauging_data = {
                                'gauging_id': gauging_row.GaugingId,
                                'cycle_id': gauging_row.CycleId,
                                'cycle_id_ref': cycle_record.id,
                                'program_name': gauging_row.ProgramName or '',
                                'cycle_date': gauging_row.CycleDate,
                                'gauging_no': gauging_row.GaugingNo or 0,
                                'gauging_type': gauging_row.GaugingType or '',
                                'anchor': gauging_row.Anchor or '',
                                'ok_status': gauging_row.OK,
                                'gauging_status': gauging_row.GaugingStatus,
                                'actual_x': float(gauging_row.ActualX or 0),
                                'signal_x_unit': gauging_row.SignalXUnit or '',
                                'actual_y': float(gauging_row.ActualY or 0),
                                'signal_y_unit': gauging_row.SignalYUnit or '',
                                'limit_testing': gauging_row.LimitTesting or 0,
                                'start_x': float(gauging_row.StartX or 0),
                                'end_x': float(gauging_row.EndX or 0),
                                'upper_limit': float(gauging_row.UpperLimit or 0),
                                'lower_limit': float(gauging_row.LowerLimit or 0),
                                'running_no': gauging_row.RunningNo or 0,
                                'gauging_alias': gauging_row.GaugingAlias or '',
                                'signal_x_name': gauging_row.SignalXName or '',
                                'signal_y_name': gauging_row.SignalYName or '',
                                'signal_x_id': gauging_row.SignalXId or 0,
                                'signal_y_id': gauging_row.SignalYId or 0,
                                'abs_offset_x': float(gauging_row.AbsOffsetX or 0),
                                'abs_offset_y': float(gauging_row.AbsOffsetY or 0),
                                'edge_type_bottom': gauging_row.EdgeTypeBottom or '',
                                'edge_type_left': gauging_row.EdgeTypeLeft or '',
                                'edge_type_right': gauging_row.EdgeTypeRight or '',
                                'edge_type_top': gauging_row.EdgeTypeTop or '',
                                'from_step_data': gauging_row.FromStepData or 0,
                                'step_no': gauging_row.StepNo or 0,
                                'last_step': gauging_row.LastStep or 0,
                            }

                            # Check if gauging already exists
                            existing_gauging = self.env['manufacturing.ruhlamat.gauging'].search([
                                ('gauging_id', '=', gauging_row.GaugingId),
                                ('cycle_id', '=', gauging_row.CycleId)
                            ], limit=1)

                            if not existing_gauging:
                                self.env['manufacturing.ruhlamat.gauging'].create(gauging_data)
                                created_gaugings += 1

                cursor.close()
                conn.close()

                # Update progress: Completion
                self.sync_progress = 100.0
                self.sync_stage = "Sync completed successfully"
                self.sync_processed_records = total_cycles
                self.env.cr.commit()

                _logger.info(
                    f"Ruhlamat MDB sync completed. Created {created_cycles} cycles and {created_gaugings} gaugings.")
                _logger.info(f"Total processing time: {fields.Datetime.now() - self.sync_start_time}")
                
                self.last_sync = fields.Datetime.now()
                self.status = 'running'

            except pyodbc.Error as e:
                _logger.error(f"Database connection error: {str(e)}")
                _logger.info("Trying alternative method using mdbtools or pandas...")
                # Alternative method using pandas and mdbtools (for Linux) or pypyodbc
                self._sync_ruhlamat_data_alternative()

        except Exception as e:
            _logger.error(f"Error syncing Ruhlamat MDB data: {str(e)}")
            self.status = 'error'
            raise

    def _sync_ruhlamat_data_optimized(self):
        """Optimized Ruhlamat sync with batch processing for better performance"""
        try:
            if not os.path.exists(self.csv_file_path):
                _logger.error(f"Ruhlamat MDB file not found: {self.csv_file_path}")
                return "MDB file not found"
            
            # Quick sync: check if file was modified since last sync
            force_full_sync = (hasattr(self, 'sync_mode') and self.sync_mode == 'full')
            if not self._should_process_file(self.csv_file_path, force_full_sync):
                _logger.info(f"Ruhlamat MDB file not modified since last sync, skipping")
                return "No changes detected"
            
            # Use optimized batch processing method
            result = self._sync_ruhlamat_data_batch()
            
            # Track processed file
            self._update_synced_files(self.csv_file_path, os.path.getmtime(self.csv_file_path))
            return result
            
        except Exception as e:
            _logger.error(f"Error in optimized Ruhlamat sync: {str(e)}")
            return f"Error: {str(e)}"

    def _sync_ruhlamat_data_batch(self):
        """Optimized Ruhlamat sync with batch processing - much faster than individual processing"""
        _logger.info(f"Starting optimized Ruhlamat MDB sync for machine: {self.machine_name}")
        
        # Initialize progress tracking
        self.sync_start_time = fields.Datetime.now()
        self.sync_progress = 0.0
        self.sync_stage = "Initializing optimized sync process"
        self.sync_processed_records = 0
        self.sync_total_records = 0
        self.env.cr.commit()

        try:
            # Connect to MDB file
            conn_str = (
                r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                f'DBQ={self.csv_file_path};'
            )

            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()

            # Step 1: Get existing cycle IDs to avoid duplicates
            self.sync_stage = "Checking existing cycles"
            self.sync_progress = 5.0
            self.env.cr.commit()
            
            existing_cycles = self.env['manufacturing.ruhlamat.press'].search([
                ('machine_id', '=', self.id)
            ]).mapped('cycle_id')
            existing_cycle_set = set(existing_cycles)
            _logger.info(f"Found {len(existing_cycle_set)} existing cycles")

            # Step 2: Fetch all cycles in one query
            self.sync_stage = "Fetching all cycles from database"
            self.sync_progress = 10.0
            self.env.cr.commit()
            
            cycles_query = """
                SELECT CycleId, ProgramName, CycleDate, ProgramId, StationId, 
                       StationName, StationLabel, PartId1, PartId2, PartId3, 
                       PartId4, PartId5, OK, CycleStatus, UfmUsername, 
                       CycleRuntimeNC, CycleRuntimePC, NcRuntimeCycleNo, 
                       NcTotalCycleNo, ProgramDate, UfmVersion, UfmServiceInfo,
                       CustomInt1, CustomInt2, CustomInt3, CustomString1, 
                       CustomString2, CustomString3, CustomXml
                FROM Cycles
                ORDER BY CycleDate DESC
            """
            cursor.execute(cycles_query)
            all_cycles = cursor.fetchall()
            
            # Filter out existing cycles
            new_cycles = [cycle for cycle in all_cycles if cycle.CycleId not in existing_cycle_set]
            total_new_cycles = len(new_cycles)
            
            self.sync_total_records = total_new_cycles
            self.sync_stage = f"Processing {total_new_cycles} new cycles (skipped {len(all_cycles) - total_new_cycles} existing)"
            self.sync_progress = 15.0
            self.env.cr.commit()
            
            _logger.info(f"Found {total_new_cycles} new cycles to process (skipped {len(all_cycles) - total_new_cycles} existing)")

            if total_new_cycles == 0:
                _logger.info("No new cycles to process")
                return "No new cycles to process"

            # Step 3: Batch process cycles
            batch_size = 100  # Process 100 cycles at a time
            created_cycles = 0
            created_gaugings = 0

            for batch_start in range(0, total_new_cycles, batch_size):
                batch_end = min(batch_start + batch_size, total_new_cycles)
                batch_cycles = new_cycles[batch_start:batch_end]
                
                # Update progress
                batch_progress = 15.0 + (batch_start / total_new_cycles) * 70.0
                self.sync_progress = batch_progress
                self.sync_processed_records = batch_start
                self.sync_stage = f"Processing batch {batch_start//batch_size + 1} ({batch_start}-{batch_end} of {total_new_cycles})"
                self.env.cr.commit()
                
                _logger.info(f"Processing batch {batch_start//batch_size + 1}: cycles {batch_start}-{batch_end}")

                # Prepare batch data for cycles
                cycle_batch_data = []
                cycle_id_to_record_id = {}
                
                for cycle_row in batch_cycles:
                    cycle_data = {
                        'cycle_id': cycle_row.CycleId,
                        'program_name': cycle_row.ProgramName,
                        'cycle_date': cycle_row.CycleDate,
                        'program_id': cycle_row.ProgramId,
                        'station_id': str(cycle_row.StationId) if cycle_row.StationId else '',
                        'station_name': cycle_row.StationName or '',
                        'station_label': cycle_row.StationLabel or '',
                        'part_id1': cycle_row.PartId1.strip() if cycle_row.PartId1 else '',
                        'part_id2': cycle_row.PartId2 or '',
                        'part_id3': cycle_row.PartId3 or '',
                        'part_id4': cycle_row.PartId4 or '',
                        'part_id5': cycle_row.PartId5 or '',
                        'ok_status': cycle_row.OK,
                        'cycle_status': cycle_row.CycleStatus,
                        'ufm_username': cycle_row.UfmUsername or '',
                        'cycle_runtime_nc': float(cycle_row.CycleRuntimeNC or 0),
                        'cycle_runtime_pc': float(cycle_row.CycleRuntimePC or 0),
                        'nc_runtime_cycle_no': cycle_row.NcRuntimeCycleNo or 0,
                        'nc_total_cycle_no': cycle_row.NcTotalCycleNo or 0,
                        'program_date': cycle_row.ProgramDate,
                        'ufm_version': cycle_row.UfmVersion or 0,
                        'ufm_service_info': cycle_row.UfmServiceInfo or 0,
                        'custom_int1': cycle_row.CustomInt1 or 0,
                        'custom_int2': cycle_row.CustomInt2 or 0,
                        'custom_int3': cycle_row.CustomInt3 or 0,
                        'custom_string1': cycle_row.CustomString1 or '',
                        'custom_string2': cycle_row.CustomString2 or '',
                        'custom_string3': cycle_row.CustomString3 or '',
                        'custom_xml': cycle_row.CustomXml or '',
                        'machine_id': self.id,
                    }
                    cycle_batch_data.append(cycle_data)

                # Batch create cycles
                if cycle_batch_data:
                    cycle_records = self.env['manufacturing.ruhlamat.press'].create(cycle_batch_data)
                    created_cycles += len(cycle_records)
                    
                    # Map cycle IDs to record IDs for gauging creation
                    for i, cycle_record in enumerate(cycle_records):
                        cycle_id_to_record_id[batch_cycles[i].CycleId] = cycle_record.id

                # Step 4: Batch fetch and create gaugings for this batch
                if cycle_id_to_record_id:
                    cycle_ids_str = ','.join(map(str, cycle_id_to_record_id.keys()))
                    gaugings_query = f"""
                        SELECT GaugingId, CycleId, ProgramName, CycleDate, GaugingNo,
                               GaugingType, Anchor, OK, GaugingStatus, ActualX, 
                               SignalXUnit, ActualY, SignalYUnit, LimitTesting,
                               StartX, EndX, UpperLimit, LowerLimit, RunningNo,
                               GaugingAlias, SignalXName, SignalYName, SignalXId,
                               SignalYId, AbsOffsetX, AbsOffsetY, EdgeTypeBottom,
                               EdgeTypeLeft, EdgeTypeRight, EdgeTypeTop, FromStepData,
                               StepNo, LastStep
                        FROM Gaugings
                        WHERE CycleId IN ({cycle_ids_str})
                        ORDER BY CycleId, GaugingNo
                    """
                    
                    cursor.execute(gaugings_query)
                    all_gaugings = cursor.fetchall()
                    
                    if all_gaugings:
                        _logger.info(f"Found {len(all_gaugings)} gaugings for batch")
                        
                        # Prepare batch data for gaugings
                        gauging_batch_data = []
                        for gauging_row in all_gaugings:
                            gauging_data = {
                                'gauging_id': gauging_row.GaugingId,
                                'cycle_id': gauging_row.CycleId,
                                'cycle_id_ref': cycle_id_to_record_id[gauging_row.CycleId],
                                'program_name': gauging_row.ProgramName or '',
                                'cycle_date': gauging_row.CycleDate,
                                'gauging_no': gauging_row.GaugingNo or 0,
                                'gauging_type': gauging_row.GaugingType or '',
                                'anchor': gauging_row.Anchor or '',
                                'ok_status': gauging_row.OK,
                                'gauging_status': gauging_row.GaugingStatus,
                                'actual_x': float(gauging_row.ActualX or 0),
                                'signal_x_unit': gauging_row.SignalXUnit or '',
                                'actual_y': float(gauging_row.ActualY or 0),
                                'signal_y_unit': gauging_row.SignalYUnit or '',
                                'limit_testing': gauging_row.LimitTesting or 0,
                                'start_x': float(gauging_row.StartX or 0),
                                'end_x': float(gauging_row.EndX or 0),
                                'upper_limit': float(gauging_row.UpperLimit or 0),
                                'lower_limit': float(gauging_row.LowerLimit or 0),
                                'running_no': gauging_row.RunningNo or 0,
                                'gauging_alias': gauging_row.GaugingAlias or '',
                                'signal_x_name': gauging_row.SignalXName or '',
                                'signal_y_name': gauging_row.SignalYName or '',
                                'signal_x_id': gauging_row.SignalXId or 0,
                                'signal_y_id': gauging_row.SignalYId or 0,
                                'abs_offset_x': float(gauging_row.AbsOffsetX or 0),
                                'abs_offset_y': float(gauging_row.AbsOffsetY or 0),
                                'edge_type_bottom': gauging_row.EdgeTypeBottom or '',
                                'edge_type_left': gauging_row.EdgeTypeLeft or '',
                                'edge_type_right': gauging_row.EdgeTypeRight or '',
                                'edge_type_top': gauging_row.EdgeTypeTop or '',
                                'from_step_data': gauging_row.FromStepData or 0,
                                'step_no': gauging_row.StepNo or 0,
                                'last_step': gauging_row.LastStep or 0,
                            }
                            gauging_batch_data.append(gauging_data)

                        # Batch create gaugings
                        if gauging_batch_data:
                            gauging_records = self.env['manufacturing.ruhlamat.gauging'].create(gauging_batch_data)
                            created_gaugings += len(gauging_records)

            # Final progress update
            self.sync_progress = 100.0
            self.sync_stage = "Ruhlamat sync completed successfully"
            self.sync_processed_records = total_new_cycles
            self.env.cr.commit()
            
            conn.close()
            
            _logger.info(f"Optimized Ruhlamat sync completed. Created {created_cycles} cycles and {created_gaugings} gaugings")
            _logger.info(f"Total processing time: {fields.Datetime.now() - self.sync_start_time}")
            
            self.status = 'running'
            self.last_sync = fields.Datetime.now()
            
            return f"Created {created_cycles} cycles and {created_gaugings} gaugings"
            
        except Exception as e:
            _logger.error(f"Error in optimized Ruhlamat sync: {e}")
            self.status = 'error'
            self.sync_stage = f"Error: {str(e)}"
            raise

    def _sync_gauging_data_optimized(self):
        """Optimized Gauging sync - placeholder for future implementation"""
        try:
            if not os.path.exists(self.csv_file_path):
                _logger.error(f"Gauging CSV file not found: {self.csv_file_path}")
                return "CSV file not found"
            
            # Quick sync: check if file was modified since last sync
            force_full_sync = (hasattr(self, 'sync_mode') and self.sync_mode == 'full')
            if not self._should_process_file(self.csv_file_path, force_full_sync):
                _logger.info(f"Gauging CSV file not modified since last sync, skipping")
                return "No changes detected"
            
            # For now, use the existing method
            # TODO: Implement optimized batch processing
            self._sync_gauging_data()
            
            # Track processed file
            self._update_synced_files(self.csv_file_path, os.path.getmtime(self.csv_file_path))
            return "Gauging sync completed"
            
        except Exception as e:
            _logger.error(f"Error in optimized Gauging sync: {str(e)}")
            return f"Error: {str(e)}"

    def _sync_aumann_data_optimized(self):
        """Optimized Aumann sync - support multiple source folders via csv_file_path"""
        try:
            # Delegate to the main implementation which supports multi-paths
            self._sync_aumann_data()
            return "Aumann sync completed"
        except Exception as e:
            _logger.error(f"Error in optimized Aumann sync: {str(e)}")
            return f"Error: {str(e)}"

    def _sync_ruhlamat_data_alternative(self):
        """Alternative method to sync MDB data using pandas"""
        try:
            # Update progress: Using alternative method
            self.sync_stage = "Using alternative sync method (pandas)"
            self.sync_progress = 5.0
            self.env.cr.commit()
            _logger.info("Using alternative sync method with pandas...")
            
            import pandas as pd
            import pypyodbc  # Alternative pure Python ODBC driver

            # For Linux systems, you might need to convert MDB to SQLite first
            # using mdbtools: mdb-export database.mdb Cycles > cycles.csv

            # Try using pypyodbc
            conn_str = (
                f'Driver={{Microsoft Access Driver (*.mdb)}};'
                f'DBQ={self.csv_file_path};'
            )

            conn = pypyodbc.connect(conn_str)
            
            # Update progress: Reading data
            self.sync_stage = "Reading data from MDB using pandas"
            self.sync_progress = 15.0
            self.env.cr.commit()

            # Read tables into pandas DataFrames
            cycles_df = pd.read_sql("SELECT * FROM Cycles", conn)
            gaugings_df = pd.read_sql("SELECT * FROM Gaugings", conn)
            
            # Update progress: Data loaded
            total_cycles_alt = len(cycles_df)
            self.sync_total_records = total_cycles_alt
            self.sync_stage = f"Processing {total_cycles_alt} cycles (alternative method)"
            self.sync_progress = 20.0
            self.env.cr.commit()
            _logger.info(f"Loaded {total_cycles_alt} cycles and {len(gaugings_df)} gaugings using pandas")

            created_cycles = 0
            created_gaugings = 0

            # Process cycles
            for cycle_index, (_, cycle_row) in enumerate(cycles_df.iterrows()):
                # Update progress for alternative method
                cycle_progress = 20.0 + (cycle_index / total_cycles_alt) * 70.0  # 20-90% for cycles
                self.sync_progress = cycle_progress
                self.sync_processed_records = cycle_index + 1
                self.sync_stage = f"Processing cycle {cycle_index + 1} of {total_cycles_alt} (alternative)"
                
                # Commit progress every 10 cycles
                if cycle_index % 10 == 0 or cycle_index == total_cycles_alt - 1:
                    self.env.cr.commit()
                    _logger.info(f"Alternative method progress: {cycle_progress:.1f}% - Processing cycle {cycle_index + 1}/{total_cycles_alt}")
                cycle_id = cycle_row['CycleId']

                # Check if cycle already exists
                existing_cycle = self.env['manufacturing.ruhlamat.press'].search([
                    ('cycle_id', '=', cycle_id),
                    ('machine_id', '=', self.id)
                ], limit=1)

                if not existing_cycle:
                    # Prepare cycle data
                    cycle_data = {
                        'cycle_id': int(cycle_id),
                        'program_name': str(cycle_row.get('ProgramName', '')),
                        'cycle_date': pd.to_datetime(cycle_row['CycleDate']),
                        'program_id': int(cycle_row.get('ProgramId', 0)),
                        'station_id': str(cycle_row.get('StationId', '')),
                        'station_name': str(cycle_row.get('StationName', '')),
                        'station_label': str(cycle_row.get('StationLabel', '')),
                        'part_id1': str(cycle_row.get('PartId1', '')).strip(),
                        'part_id2': str(cycle_row.get('PartId2', '')),
                        'part_id3': str(cycle_row.get('PartId3', '')),
                        'part_id4': str(cycle_row.get('PartId4', '')),
                        'part_id5': str(cycle_row.get('PartId5', '')),
                        'ok_status': int(cycle_row.get('OK', 0)),
                        'cycle_status': int(cycle_row.get('CycleStatus', 0)),
                        'ufm_username': str(cycle_row.get('UfmUsername', '')),
                        'cycle_runtime_nc': float(cycle_row.get('CycleRuntimeNC', 0)),
                        'cycle_runtime_pc': float(cycle_row.get('CycleRuntimePC', 0)),
                        'nc_runtime_cycle_no': int(cycle_row.get('NcRuntimeCycleNo', 0)),
                        'nc_total_cycle_no': int(cycle_row.get('NcTotalCycleNo', 0)),
                        'program_date': pd.to_datetime(cycle_row.get('ProgramDate')) if pd.notna(
                            cycle_row.get('ProgramDate')) else False,
                        'ufm_version': int(cycle_row.get('UfmVersion', 0)),
                        'ufm_service_info': int(cycle_row.get('UfmServiceInfo', 0)),
                        'custom_int1': int(cycle_row.get('CustomInt1', 0)),
                        'custom_int2': int(cycle_row.get('CustomInt2', 0)),
                        'custom_int3': int(cycle_row.get('CustomInt3', 0)),
                        'custom_string1': str(cycle_row.get('CustomString1', '')),
                        'custom_string2': str(cycle_row.get('CustomString2', '')),
                        'custom_string3': str(cycle_row.get('CustomString3', '')),
                        'custom_xml': str(cycle_row.get('CustomXml', '')),
                        'machine_id': self.id,
                    }

                    # Create cycle record
                    cycle_record = self.env['manufacturing.ruhlamat.press'].create(cycle_data)
                    created_cycles += 1

                    # Get related gaugings
                    cycle_gaugings = gaugings_df[gaugings_df['CycleId'] == cycle_id]

                    for _, gauging_row in cycle_gaugings.iterrows():
                        gauging_data = {
                            'gauging_id': int(gauging_row['GaugingId']),
                            'cycle_id': int(gauging_row['CycleId']),
                            'cycle_id_ref': cycle_record.id,
                            'program_name': str(gauging_row.get('ProgramName', '')),
                            'cycle_date': pd.to_datetime(gauging_row['CycleDate']),
                            'gauging_no': int(gauging_row.get('GaugingNo', 0)),
                            'gauging_type': str(gauging_row.get('GaugingType', '')),
                            'anchor': str(gauging_row.get('Anchor', '')),
                            'ok_status': int(gauging_row.get('OK', 0)),
                            'gauging_status': int(gauging_row.get('GaugingStatus', 0)),
                            'actual_x': float(gauging_row.get('ActualX', 0)),
                            'signal_x_unit': str(gauging_row.get('SignalXUnit', '')),
                            'actual_y': float(gauging_row.get('ActualY', 0)),
                            'signal_y_unit': str(gauging_row.get('SignalYUnit', '')),
                            'limit_testing': int(gauging_row.get('LimitTesting', 0)),
                            'start_x': float(gauging_row.get('StartX', 0)),
                            'end_x': float(gauging_row.get('EndX', 0)),
                            'upper_limit': float(gauging_row.get('UpperLimit', 0)),
                            'lower_limit': float(gauging_row.get('LowerLimit', 0)),
                            'running_no': int(gauging_row.get('RunningNo', 0)),
                            'gauging_alias': str(gauging_row.get('GaugingAlias', '')),
                            'signal_x_name': str(gauging_row.get('SignalXName', '')),
                            'signal_y_name': str(gauging_row.get('SignalYName', '')),
                            'signal_x_id': int(gauging_row.get('SignalXId', 0)),
                            'signal_y_id': int(gauging_row.get('SignalYId', 0)),
                            'abs_offset_x': float(gauging_row.get('AbsOffsetX', 0)),
                            'abs_offset_y': float(gauging_row.get('AbsOffsetY', 0)),
                            'edge_type_bottom': str(gauging_row.get('EdgeTypeBottom', '')),
                            'edge_type_left': str(gauging_row.get('EdgeTypeLeft', '')),
                            'edge_type_right': str(gauging_row.get('EdgeTypeRight', '')),
                            'edge_type_top': str(gauging_row.get('EdgeTypeTop', '')),
                            'from_step_data': int(gauging_row.get('FromStepData', 0)),
                            'step_no': int(gauging_row.get('StepNo', 0)),
                            'last_step': int(gauging_row.get('LastStep', 0)),
                        }

                        self.env['manufacturing.ruhlamat.gauging'].create(gauging_data)
                        created_gaugings += 1

            conn.close()

            # Update progress: Alternative method completion
            self.sync_progress = 100.0
            self.sync_stage = "Alternative sync method completed successfully"
            self.sync_processed_records = total_cycles_alt
            self.env.cr.commit()

            _logger.info(
                f"Ruhlamat MDB sync (alternative method) completed. Created {created_cycles} cycles and {created_gaugings} gaugings.")
            _logger.info(f"Alternative method total processing time: {fields.Datetime.now() - self.sync_start_time}")
            
            self.last_sync = fields.Datetime.now()
            self.status = 'running'

        except Exception as e:
            _logger.error(f"Alternative MDB sync method failed: {str(e)}")
            self.status = 'error'
            raise

    def _sync_aumann_data(self):
        """Sync Aumann Measurement system data from one or multiple folders of CSV files (one file per serial)."""
        _logger.info(f"Starting Aumann data sync for machine: {self.machine_name} from path(s): {self.csv_file_path}")
        
        # Initialize progress tracking
        self.sync_start_time = fields.Datetime.now()
        self.sync_progress = 0.0
        self.sync_stage = "Initializing Aumann sync process"
        self.sync_processed_records = 0
        self.sync_total_records = 0
        self.env.cr.commit()
        
        try:
            # Resolve one or more source directories from csv_file_path
            source_dirs = self._parse_multi_paths(self.csv_file_path)
            if not source_dirs:
                _logger.error("Aumann CSV source path(s) not configured")
                self.status = 'error'
                self.sync_stage = "Error: No source path(s) provided"
                return

            # Filter only existing directories
            valid_dirs = []
            for p in source_dirs:
                if os.path.isdir(p):
                    valid_dirs.append(p)
                else:
                    _logger.warning(f"Skipping invalid Aumann path: {p}")

            if not valid_dirs:
                _logger.error("None of the provided Aumann paths exist or are directories")
                self.status = 'error'
                self.sync_stage = "Error: No valid directories"
                return

            # Update progress: Scanning folders
            self.sync_stage = "Scanning folders for CSV files"
            self.sync_progress = 10.0
            self.env.cr.commit()
            _logger.info(f"Scanning {len(valid_dirs)} Aumann folder(s) for CSV files...")

            # Collect all CSV file full paths across all valid dirs
            all_csv_files = []
            for d in valid_dirs:
                try:
                    files = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith('.csv')]
                    _logger.info(f"Found {len(files)} CSV files in {d}")
                    all_csv_files.extend(files)
                except Exception as e:
                    _logger.error(f"Error listing directory {d}: {e}")

            # Filter files based on sync mode
            force_full_sync = (hasattr(self, 'sync_mode') and self.sync_mode == 'full')
            files_to_process = []

            for csv_path in all_csv_files:
                if self._should_process_file(csv_path, force_full_sync):
                    files_to_process.append(csv_path)

            total_files = len(files_to_process)
            skipped_files = len(all_csv_files) - total_files
            self.sync_total_records = total_files
            self.sync_stage = f"Found {len(all_csv_files)} CSV files, processing {total_files} files, skipping {skipped_files} unchanged files"
            self.sync_progress = 15.0
            self.env.cr.commit()

            _logger.info(f"Quick sync: Processing {total_files} files, skipping {skipped_files} unchanged files")

            records_created = 0

            for file_index, csv_path in enumerate(files_to_process):
                csv_file = os.path.basename(csv_path)
                # Update progress for file processing
                file_progress = 15.0 + ((file_index / total_files) * 80.0 if total_files else 80.0)
                self.sync_progress = file_progress
                self.sync_processed_records = file_index + 1
                self.sync_stage = f"Processing file {file_index + 1} of {total_files}: {csv_file}"

                # Commit progress every 10 files or at the end
                if file_index % 10 == 0 or file_index == total_files - 1:
                    self.env.cr.commit()
                    _logger.info(f"Progress: {file_progress:.1f}% - Processing file {file_index + 1}/{total_files}")

                try:
                    file_records = self._process_aumann_csv_file(csv_path)
                    records_created += file_records
                    if file_records > 0:
                        _logger.debug(f"Created {file_records} records from {csv_file}")
                    
                    # Track processed file
                    self._update_synced_files(csv_path, os.path.getmtime(csv_path))
                except Exception as e:
                    _logger.error(f"Error processing Aumann CSV file {csv_file}: {e}")
                    continue
            
            # Update progress: Completion
            self.sync_progress = 100.0
            self.sync_stage = "Aumann sync completed successfully"
            self.sync_processed_records = total_files
            self.env.cr.commit()
            
            _logger.info(f"Aumann data sync completed. Total records created: {records_created}")
            _logger.info(f"Total processing time: {fields.Datetime.now() - self.sync_start_time}")
            
            self.status = 'running'
            self.last_sync = fields.Datetime.now()
            
        except Exception as e:
            _logger.error(f"Error in Aumann data sync: {e}")
            self.status = 'error'
            self.sync_stage = f"Error: {str(e)}"
            raise

    def _process_aumann_csv_file(self, csv_path):
        """Process a single Aumann CSV file for one serial number"""
        records_created = 0
        filename = os.path.basename(csv_path)
        
        _logger.debug(f"Processing Aumann CSV file: {filename}")

        # Try multiple encodings
        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252']

        file_content = None
        successful_encoding = None

        for encoding in encodings:
            try:
                with open(csv_path, 'r', encoding=encoding) as file:
                    file_content = file.read()
                    successful_encoding = encoding
                    break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if file_content is None:
            _logger.error(f"Could not decode file {csv_path} with any known encoding")
            return 0

        _logger.debug(f"Successfully decoded {filename} using {successful_encoding}")

        try:
            # Process the decoded content
            lines = file_content.split('\n')
            if not lines:
                _logger.warning(f"Empty file: {filename}")
                return 0

            header_line = lines[0].strip()
            delimiter = ';' if ';' in header_line else ','
            _logger.debug(f"Using delimiter '{delimiter}' for {filename}")

            # Use StringIO to create a file-like object from the string
            from io import StringIO
            file_like = StringIO(file_content)
            reader = csv.DictReader(file_like, delimiter=delimiter)

            # Process each row (should be only one row per file for Aumann)
            row_count = 0
            for row in reader:
                row_count += 1
                _logger.debug(f"Processing row {row_count} in {filename}")
                
                try:
                    # Normalize row keys/values (trim and collapse spaces)
                    import re as _re
                    def _norm_key(k):
                        return _re.sub(r"\s+", " ", (k or '').strip())
                    def _norm_val(v):
                        return v.strip() if isinstance(v, str) else v
                    row = { _norm_key(k): _norm_val(v) for k, v in row.items() }
                    # Extract serial number from filename or row data
                    serial_number = self._extract_serial_number_from_filename(csv_path, row)
                    if not serial_number:
                        _logger.warning(f"Could not extract serial number from file: {filename}")
                        continue

                    _logger.debug(f"Extracted serial number: {serial_number} from {filename}")

                    # Check if record already exists
                    existing = self.env['manufacturing.aumann.measurement'].search([
                        ('serial_number', '=', serial_number),
                        ('machine_id', '=', self.id)
                    ], limit=1)

                    if existing:
                        _logger.debug(f"Aumann record for Serial Number {serial_number} already exists. Skipping.")
                        continue

                    # Parse timestamp
                    timestamp_raw = row.get('Timestamp', '')
                    _logger.debug(f"Raw timestamp from CSV: '{timestamp_raw}' for {serial_number}")
                    
                    # If no timestamp in 'Timestamp' field, try to extract from other possible fields
                    if not timestamp_raw or timestamp_raw.strip() == '':
                        # Try alternative timestamp field names
                        alternative_fields = ['timestamp', 'Date', 'date', 'Time', 'time', 'TestDate', 'test_date']
                        for field in alternative_fields:
                            if field in row and row[field]:
                                timestamp_raw = row[field]
                                _logger.debug(f"Found timestamp in alternative field '{field}': '{timestamp_raw}'")
                                break
                    
                    test_date = self._parse_aumann_timestamp(timestamp_raw)
                    _logger.debug(f"Parsed test date: {test_date} for {serial_number}")
                    
                    # Log if we're using current time instead of the actual timestamp
                    if test_date == fields.Datetime.now():
                        _logger.warning(f"Using current time instead of actual timestamp for {serial_number}. Raw timestamp was: '{timestamp_raw}'")
                        # Try to extract timestamp from raw_data as last resort
                        test_date = self._extract_timestamp_from_raw_data(str(row))
                        if test_date != fields.Datetime.now():
                            _logger.info(f"Successfully extracted timestamp from raw data: {test_date}")

                    # Create measurement record with all fields
                    create_vals = {
                        'serial_number': serial_number,
                        'machine_id': self.id,
                        'test_date': test_date,
                        'part_type': row.get('Type', ''),
                        'raw_data': str(row)[:2000],  # Limit raw data size
                    }

                    # Map all measurement fields from CSV to model fields (with normalized keys)
                    field_mapping = self._get_aumann_field_mapping()
                    norm_mapping = { _norm_key(k): v for k, v in field_mapping.items() }
                    mapped_fields = 0
                    for csv_key, raw_val in row.items():
                        model_field = norm_mapping.get(_norm_key(csv_key))
                        if not model_field:
                            continue
                        if raw_val in (None, ''):
                            continue
                        try:
                            create_vals[model_field] = float(raw_val)
                            mapped_fields += 1
                        except (ValueError, TypeError):
                            _logger.warning(f"Could not parse {csv_key} value: {raw_val} in {filename}")

                    _logger.debug(f"Mapped {mapped_fields} measurement fields for {serial_number}")

                    # Determine result based on measurements
                    create_vals['result'] = self._determine_aumann_result(create_vals)
                    _logger.debug(f"Determined result: {create_vals['result']} for {serial_number}")

                    # Create the record
                    new_record = self.env['manufacturing.aumann.measurement'].create(create_vals)
                    records_created += 1
                    _logger.debug(f"Successfully created Aumann record for Serial Number: {serial_number}")

                except Exception as e:
                    _logger.error(f"Failed to process Aumann row in {filename}: {e}")
                    continue
            
            _logger.debug(f"Processed {row_count} rows from {filename}, created {records_created} records")

        except Exception as e:
            _logger.error(f"Error processing Aumann CSV file {csv_path}: {e}")

        return records_created

    def _parse_multi_paths(self, raw_paths):
        """Parse multi-path string into a list of absolute directory paths.
        Accepts separators: newline, semicolon, pipe, comma. Trims quotes/spaces.
        """
        try:
            if not raw_paths:
                return []
            # Normalize separators
            seps = ['\n', ';', '|', ',']
            work = str(raw_paths)
            for s in seps:
                work = work.replace(s, '\n')
            # Split and clean
            parts = [p.strip().strip('"\'') for p in work.splitlines() if p and p.strip()]
            # Expand env vars and normalize
            cleaned = []
            for p in parts:
                expanded = os.path.expandvars(os.path.expanduser(p))
                cleaned.append(os.path.normpath(expanded))
            # De-duplicate while preserving order
            seen = set()
            result = []
            for p in cleaned:
                if p not in seen:
                    seen.add(p)
                    result.append(p)
            return result
        except Exception as e:
            _logger.error(f"Failed to parse multi paths '{raw_paths}': {e}")
            return []

    def _get_last_synced_files(self):
        """Get dictionary of last synced files with their modification times"""
        try:
            if hasattr(self, 'last_synced_files') and self.last_synced_files:
                return json.loads(self.last_synced_files)
            return {}
        except Exception:
            return {}

    def _update_synced_files(self, file_path, mod_time):
        """Update the synced files tracking"""
        if hasattr(self, 'last_synced_files'):
            synced_files = self._get_last_synced_files()
            synced_files[file_path] = mod_time
            self.last_synced_files = json.dumps(synced_files)

    def _should_process_file(self, file_path, force_full_sync=False):
        """Check if file should be processed based on modification time"""
        if force_full_sync:
            return True
        
        # If sync_mode field doesn't exist yet, process all files (backward compatibility)
        if not hasattr(self, 'sync_mode'):
            return True
        
        try:
            current_mod_time = os.path.getmtime(file_path)
            synced_files = self._get_last_synced_files()
            last_mod_time = synced_files.get(file_path, 0)
            
            return current_mod_time > last_mod_time
        except Exception as e:
            _logger.warning(f"Error checking file modification time for {file_path}: {e}")
            return True  # Process if we can't determine

    def _extract_serial_number_from_filename(self, csv_path, row):
        """Extract serial number from filename or row data"""
        # Try to get from Seriennummer field first
        if 'Seriennummer' in row and row['Seriennummer']:
            return str(row['Seriennummer']).strip()
        
        # Try to extract from filename
        filename = os.path.basename(csv_path)
        # Remove .csv extension
        name_without_ext = os.path.splitext(filename)[0]
        
        # If filename looks like a serial number, use it
        if len(name_without_ext) > 5:  # Assume serial numbers are longer than 5 characters
            return name_without_ext
        
        return None

    def _extract_timestamp_from_raw_data(self, raw_data_str):
        """Extract timestamp from raw data string as last resort"""
        import re
        
        # Common timestamp patterns in raw data
        timestamp_patterns = [
            r"'Timestamp':\s*'([^']+)'",           # 'Timestamp': '2025-03-18 21:20:37'
            r'"Timestamp":\s*"([^"]+)"',           # "Timestamp": "2025-03-18 21:20:37"
            r"'timestamp':\s*'([^']+)'",           # 'timestamp': '2025-03-18 21:20:37'
            r'"timestamp":\s*"([^"]+)"',           # "timestamp": "2025-03-18 21:20:37"
            r"'Date':\s*'([^']+)'",                # 'Date': '2025-03-18 21:20:37'
            r'"Date":\s*"([^"]+)"',                # "Date": "2025-03-18 21:20:37"
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',  # 2025-03-18 21:20:37
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',     # 2025-03-18T21:20:37
        ]
        
        for pattern in timestamp_patterns:
            matches = re.findall(pattern, raw_data_str)
            if matches:
                timestamp_str = matches[0]
                _logger.debug(f"Found timestamp in raw data: '{timestamp_str}'")
                return self._parse_aumann_timestamp(timestamp_str)
        
        _logger.debug("No timestamp found in raw data")
        return fields.Datetime.now()

    def _parse_aumann_timestamp(self, timestamp_str):
        """Parse Aumann timestamp string"""
        if not timestamp_str:
            _logger.warning("Empty timestamp string, using current time")
            return fields.Datetime.now()
        
        # Clean the timestamp string
        timestamp_str = str(timestamp_str).strip()
        _logger.debug(f"Parsing Aumann timestamp: '{timestamp_str}'")
        
        try:
            # Try different timestamp formats commonly used in Aumann data
            timestamp_formats = [
                '%Y-%m-%d %H:%M:%S',        # 2025-03-18 21:20:37
                '%Y-%m-%d %H:%M:%S.%f',     # 2025-03-18 21:20:37.123456
                '%Y-%m-%d %H:%M:%S.%fZ',    # 2025-03-18 21:20:37.123456Z
                '%Y-%m-%d %H:%M:%SZ',       # 2025-03-18 21:20:37Z
                '%d/%m/%Y %H:%M:%S',        # 18/03/2025 21:20:37
                '%m/%d/%Y %H:%M:%S',        # 03/18/2025 21:20:37
                '%d-%m-%Y %H:%M:%S',        # 18-03-2025 21:20:37
                '%Y-%m-%dT%H:%M:%S',        # 2025-03-18T21:20:37
                '%Y-%m-%dT%H:%M:%S.%f',    # 2025-03-18T21:20:37.123456
                '%Y-%m-%dT%H:%M:%S.%fZ',   # 2025-03-18T21:20:37.123456Z
                '%Y-%m-%dT%H:%M:%SZ',      # 2025-03-18T21:20:37Z
            ]
            
            for fmt in timestamp_formats:
                try:
                    # Parse the datetime string
                    parsed_dt = datetime.strptime(timestamp_str, fmt)
                    
                    # Since CSV contains IST time, we need to treat it as IST and convert to UTC
                    # for Odoo to store correctly, then it will display back as IST
                    import pytz
                    ist = pytz.timezone('Asia/Kolkata')
                    ist_dt = ist.localize(parsed_dt)
                    utc_dt = ist_dt.astimezone(pytz.UTC)
                    
                    # Return in UTC format for Odoo storage
                    result = utc_dt.strftime('%Y-%m-%d %H:%M:%S')
                    _logger.debug(f"Successfully parsed timestamp '{timestamp_str}' using format '{fmt}' -> {result}")
                    return result
                except ValueError:
                    continue
            
            # If all formats failed, log the issue and use current time
            _logger.warning(f"Could not parse timestamp '{timestamp_str}' with any known format, using current time")
            _logger.debug(f"Available formats tried: {timestamp_formats}")
            return fields.Datetime.now()
            
        except Exception as e:
            _logger.warning(f"Error parsing timestamp '{timestamp_str}': {e}")
            return fields.Datetime.now()

    def _get_aumann_field_mapping(self):
        """Get mapping from CSV field names to universal model field names
        Both A-lobes (Intake) and E-lobes (Exhaust) map to the same universal fields
        """
        return {
            # Wheel Angle Measurements - Intake variant
            'Wheel Angle Left 150 - CTF 41.5': 'wheel_angle_left_150',
            'Wheel Angle Left 30 - CTF 41.4': 'wheel_angle_left_30',
            'Wheel Angle Right 30 - CTF 41.3': 'wheel_angle_right_30',
            'Wheel Angle Right 60 - CTF 41.2': 'wheel_angle_right_60',
            'Wheel Angle Right 90 - CTF 41.1': 'wheel_angle_right_90',

            # Wheel Angle Measurements - Exhaust variant
            'Wheel Angle Left 120 - CTF 41.3': 'wheel_angle_left_120',
            'Wheel Angle Left 150 - CTF 41.2': 'wheel_angle_left_150',
            'Wheel Angle Left 180 - CTF 41.1': 'wheel_angle_left_180',
            'Wheel Angle Right 120 - CTF 41.5': 'wheel_angle_right_120',
            'Wheel Angle Right 150 - CTF 41.4': 'wheel_angle_right_150',

            'Wheel Angle to Reference - CTF 42': 'wheel_angle_to_reference',

            # Angle Lobe Measurements - Both E and A variants map to universal fields
            'Angle Lobe E11 to Ref. - CTF 29': 'angle_lobe_11_to_ref',
            'Angle Lobe E12 to Ref. - CTF 29': 'angle_lobe_12_to_ref',
            'Angle Lobe E21 to Ref. - CTF 29': 'angle_lobe_21_to_ref',
            'Angle Lobe E22 to Ref. - CTF 29': 'angle_lobe_22_to_ref',
            'Angle Lobe E31 to Ref. - CTF 29': 'angle_lobe_31_to_ref',
            'Angle Lobe E32 to Ref. - CTF 29': 'angle_lobe_32_to_ref',
            'Angle Lobe A11 to Ref. - CTF 29': 'angle_lobe_11_to_ref',
            'Angle Lobe A12 to Ref. - CTF 29': 'angle_lobe_12_to_ref',
            'Angle Lobe A21 to Ref. - CTF 29': 'angle_lobe_21_to_ref',
            'Angle Lobe A22 to Ref. - CTF 29': 'angle_lobe_22_to_ref',
            'Angle Lobe A31 to Ref. - CTF 29': 'angle_lobe_31_to_ref',
            'Angle Lobe A32 to Ref. - CTF 29': 'angle_lobe_32_to_ref',

            # Angle Pump Lobe - Intake only
            'Angle PumpLobe to Ref. - CTF 92': 'angle_pumplobe_to_ref',

            # Base Circle Radius - Both variants map to universal fields
            'Base Circle Radius Lobe E11 - CTF 54': 'base_circle_radius_lobe_11',
            'Base Circle Radius Lobe E12 - CTF 54': 'base_circle_radius_lobe_12',
            'Base Circle Radius Lobe E21 - CTF 54': 'base_circle_radius_lobe_21',
            'Base Circle Radius Lobe E22 - CTF 54': 'base_circle_radius_lobe_22',
            'Base Circle Radius Lobe E31 - CTF 54': 'base_circle_radius_lobe_31',
            'Base Circle Radius Lobe E32 - CTF 54': 'base_circle_radius_lobe_32',
            'Base Circle Radius Lobe A11 - CTF 54': 'base_circle_radius_lobe_11',
            'Base Circle Radius Lobe A12 - CTF 54': 'base_circle_radius_lobe_12',
            'Base Circle Radius Lobe A21 - CTF 54': 'base_circle_radius_lobe_21',
            'Base Circle Radius Lobe A22 - CTF 54': 'base_circle_radius_lobe_22',
            'Base Circle Radius Lobe A31 - CTF 54': 'base_circle_radius_lobe_31',
            'Base Circle Radius Lobe A32 - CTF 54': 'base_circle_radius_lobe_32',
            'Base Circle Radius Pump Lobe - 239': 'base_circle_radius_pump_lobe',

            # Base Circle Runout - Both variants map to universal fields
            'Base Circle Runout Lobe E11 adj. - CTF  15': 'base_circle_runout_lobe_11_adj',
            'Base Circle Runout Lobe E12 adj. - CTF  15': 'base_circle_runout_lobe_12_adj',
            'Base Circle Runout Lobe E21 adj. - CTF  15': 'base_circle_runout_lobe_21_adj',
            'Base Circle Runout Lobe E22 adj. - CTF  15': 'base_circle_runout_lobe_22_adj',
            'Base Circle Runout Lobe E31 adj. - CTF  15': 'base_circle_runout_lobe_31_adj',
            'Base Circle Runout Lobe E32 adj. - CTF  15': 'base_circle_runout_lobe_32_adj',
            'Base Circle Runout Lobe A11 adj. - CTF 15': 'base_circle_runout_lobe_11_adj',
            'Base Circle Runout Lobe A12 adj. - CTF 15': 'base_circle_runout_lobe_12_adj',
            'Base Circle Runout Lobe A21 adj. - CTF 15': 'base_circle_runout_lobe_21_adj',
            'Base Circle Runout Lobe A22 adj. - CTF 15': 'base_circle_runout_lobe_22_adj',
            'Base Circle Runout Lobe A31 adj. - CTF 15': 'base_circle_runout_lobe_31_adj',
            'Base Circle Runout Lobe A32 adj. - CTF 15': 'base_circle_runout_lobe_32_adj',

            # Bearing and Width Measurements
            'Bearing Width - CTF 55': 'bearing_width',
            'Cam Angle12': 'cam_angle12',
            'Cam Angle34': 'cam_angle34',
            'Cam Angle56 ': 'cam_angle56',

            # Concentricity Measurements - Handle both naming conventions
            'Concentricity Front Bearing H - CTF 63': 'concentricity_front_bearing_h',
            'Concentricity IO -M- Front End - CTF 59': 'concentricity_io_front_end_dia_39',
            'Concentricity IO -M- Front End Dia 39 - CTF 59': 'concentricity_io_front_end_dia_39',
            'Concentricity IO -M- Front end major - CTF 61': 'concentricity_io_front_end_major_dia_40',
            'Concentricity IO -M- Front end major Dia 40 - CTF 61': 'concentricity_io_front_end_major_dia_40',
            'Concentricity IO -M- Step Diameter - CTF 25': 'concentricity_io_step_diameter_32_5',
            'Concentricity IO -M- Step Diameter 32.5 - CTF 25': 'concentricity_io_step_diameter_32_5',

            # Concentricity Results
            'Concentricity result Front End - CTF 59': 'concentricity_result_front_end_dia_39',
            'Concentricity result Front End Dia 39 - CTF 59': 'concentricity_result_front_end_dia_39',
            'Concentricity result Front end major - CTF 61': 'concentricity_result_front_end_major_dia_40',
            'Concentricity result Front end major Dia 40 - CTF 61': 'concentricity_result_front_end_major_dia_40',
            'Concentricity result Step Diameter - CTF 25': 'concentricity_result_step_diameter_32_5',
            'Concentricity result Step Diameter 32.5 - CTF 25': 'concentricity_result_step_diameter_32_5',

            # Diameter Measurements
            'Diameter Front Bearing H - CTF 62': 'diameter_front_bearing_h',
            'Diameter Front End - CTF 58': 'diameter_front_end',
            'Diameter Front end major - CTF 60': 'diameter_front_end_major',
            'Diameter Journal A1 - CTF 1': 'diameter_journal_a1',
            'Diameter Journal A2 - CTF 1': 'diameter_journal_a2',
            'Diameter Journal A3 - CTF 1': 'diameter_journal_a3',
            'Diameter Journal B1 - CTF 7': 'diameter_journal_b1',
            'Diameter Journal B2 - CTF 7': 'diameter_journal_b2',
            'Diameter Step Diameter tpc - CTF 24': 'diameter_step_diameter_tpc',

            # Distance Measurements - Both variants map to universal fields
            'Distance Lobe E11 - CTF 52.1': 'distance_lobe_11',
            'Distance Lobe E12 - CTF 52.2': 'distance_lobe_12',
            'Distance Lobe E21 - CTF 52.3': 'distance_lobe_21',
            'Distance Lobe E22 - CTF 52.4': 'distance_lobe_22',
            'Distance Lobe E31 - CTF 52.5': 'distance_lobe_31',
            'Distance Lobe E32 - CTF 52.6': 'distance_lobe_32',
            'Distance Lobe A11 - CTF 52.1': 'distance_lobe_11',
            'Distance Lobe A12 - CTF 52.2': 'distance_lobe_12',
            'Distance Lobe A21 - CTF 52.3': 'distance_lobe_21',
            'Distance Lobe A22 - CTF 52.4': 'distance_lobe_22',
            'Distance Lobe A31 - CTF 52.5': 'distance_lobe_31',
            'Distance Lobe A32 - CTF 52.6': 'distance_lobe_32',
            'Distance Pump Lobe - CTF 81': 'distance_pump_lobe',
            'Distance Rear End - CTF 214': 'distance_rear_end',
            'Distance Step length front face - CTF 66': 'distance_step_length_front_face',
            'Distance Trigger Length - CTF 220': 'distance_trigger_length',  # Intake
            'Distance Trigger Length - CTF 213': 'distance_trigger_length',  # Exhaust
            'Distance from front end face - CTF 65': 'distance_from_front_end_face',

            # Face Measurements
            'Face total runout of bearing face - 0 - CTF 56': 'face_total_runout_bearing_face_0',
            'Face total runout of bearing face - 25 - CTF 56': 'face_total_runout_bearing_face_25',
            'Front face flatness Concav - CTF 68': 'front_face_flatness_concav',
            'Front face flatness Convex - CTF 68': 'front_face_flatness_convex',
            'Front face runout - CTF 67': 'front_face_runout',

            # Profile Measurements
            'Max. Profile 30 for trigger wheel diameter - CTF 39': 'max_profile_30_trigger_wheel_diameter',
            'Max. Profile 42 for trigger wheel diameter - CTF 39': 'max_profile_42_trigger_wheel_diameter',
            'Min. Profile 30 for trigger wheel diameter - CTF 39': 'min_profile_30_trigger_wheel_diameter',
            'Min. Profile 42 for trigger wheel diameter - CTF 39': 'min_profile_42_trigger_wheel_diameter',

            # Temperature Measurements
            'Temperature Machine': 'temperature_machine',
            'Temperature Sensor': 'temperature_sensor',

            # Trigger Wheel Measurements - Both CTF variants
            'Trigger wheel diameter - CTF 247': 'trigger_wheel_diameter',  # Intake
            'Trigger wheel diameter - CTF 248': 'trigger_wheel_diameter',  # Exhaust
            'Trigger wheel width - CTF 223': 'trigger_wheel_width',  # Intake
            'Trigger wheel width - CTF 218': 'trigger_wheel_width',  # Exhaust

            # Two Flat Measurements
            'Two Flat Size - CTF 20': 'two_flat_size',
            'Two Flat Symmetry - CTF 21': 'two_flat_symmetry',

            # Rear End Length
            'Rear end length- CTF 211': 'rear_end_length',

            # Roundness Measurements
            'Roundness Journal A1 - CTF 2': 'roundness_journal_a1',
            'Roundness Journal A2 - CTF 2': 'roundness_journal_a2',
            'Roundness Journal A3 - CTF 2': 'roundness_journal_a3',
            'Roundness Journal B1 - CTF 8': 'roundness_journal_b1',
            'Roundness Journal B2 - CTF 8': 'roundness_journal_b2',

            # Runout Measurements
            'Runout Journal A1 A1-B1 - CTF 4': 'runout_journal_a1_a1_b1',
            'Runout Journal A2 A1-B1 - CTF 4': 'runout_journal_a2_a1_b1',
            'Runout Journal A3 A1-B1 - CTF 4': 'runout_journal_a3_a1_b1',
            'Runout Journal B1 A1-A3 - CTF 10': 'runout_journal_b1_a1_a3',
            'Runout Journal B2 A1-A3 - CTF 10': 'runout_journal_b2_a1_a3',

            # Straightness Journal Measurements
            'Straightness Journal A1 - CTF 3': 'straightness_journal_a1',
            'Straightness Journal A2 - CTF 3': 'straightness_journal_a2',
            'Straightness Journal A3 - CTF 3': 'straightness_journal_a3',
            'Straightness Journal B1 - CTF 9': 'straightness_journal_b1',
            'Straightness Journal B2 - CTF 9': 'straightness_journal_b2',

            # Profile Error Measurements - Both variants map to universal fields
            'Profile Error Lobe E11  Zone 1 - CTF 12': 'profile_error_lobe_11_zone_1',
            'Profile Error Lobe E11  Zone 2 - CTF 13': 'profile_error_lobe_11_zone_2',
            'Profile Error Lobe E11 Zone 3 - CTF 13': 'profile_error_lobe_11_zone_3',
            'Profile Error Lobe E11 Zone 4 - CTF 12': 'profile_error_lobe_11_zone_4',
            'Profile Error Lobe E12  Zone 1 - CTF 12': 'profile_error_lobe_12_zone_1',
            'Profile Error Lobe E12  Zone 2 - CTF 13': 'profile_error_lobe_12_zone_2',
            'Profile Error Lobe E12 Zone 3 - CTF 13': 'profile_error_lobe_12_zone_3',
            'Profile Error Lobe E12 Zone 4 - CTF 12': 'profile_error_lobe_12_zone_4',
            'Profile Error Lobe E21  Zone 1 - CTF 12': 'profile_error_lobe_21_zone_1',
            'Profile Error Lobe E21  Zone 2 - CTF 13': 'profile_error_lobe_21_zone_2',
            'Profile Error Lobe E21 Zone 3 - CTF 13': 'profile_error_lobe_21_zone_3',
            'Profile Error Lobe E21 Zone 4 - CTF 12': 'profile_error_lobe_21_zone_4',
            'Profile Error Lobe E22  Zone 1 - CTF 12': 'profile_error_lobe_22_zone_1',
            'Profile Error Lobe E22  Zone 2 - CTF 13': 'profile_error_lobe_22_zone_2',
            'Profile Error Lobe E22 Zone 3 - CTF 13': 'profile_error_lobe_22_zone_3',
            'Profile Error Lobe E22 Zone 4 - CTF 12': 'profile_error_lobe_22_zone_4',
            'Profile Error Lobe E31  Zone 1 - CTF 12': 'profile_error_lobe_31_zone_1',
            'Profile Error Lobe E31  Zone 2 - CTF 13': 'profile_error_lobe_31_zone_2',
            'Profile Error Lobe E31 Zone 3 - CTF 13': 'profile_error_lobe_31_zone_3',
            'Profile Error Lobe E31 Zone 4 - CTF 12': 'profile_error_lobe_31_zone_4',
            'Profile Error Lobe E32  Zone 1 - CTF 12': 'profile_error_lobe_32_zone_1',
            'Profile Error Lobe E32  Zone 2 - CTF 13': 'profile_error_lobe_32_zone_2',
            'Profile Error Lobe E32 Zone 3 - CTF 13': 'profile_error_lobe_32_zone_3',
            'Profile Error Lobe E32 Zone 4 - CTF 12': 'profile_error_lobe_32_zone_4',
            'Profile Error Lobe A11  Zone 1 - CTF 12': 'profile_error_lobe_11_zone_1',
            'Profile Error Lobe A11  Zone 2 - CTF 13': 'profile_error_lobe_11_zone_2',
            'Profile Error Lobe A11 Zone 3 - CTF 13': 'profile_error_lobe_11_zone_3',
            'Profile Error Lobe A11 Zone 4 - CTF 12': 'profile_error_lobe_11_zone_4',
            'Profile Error Lobe A12  Zone 1 - CTF 12': 'profile_error_lobe_12_zone_1',
            'Profile Error Lobe A12  Zone 2 - CTF 13': 'profile_error_lobe_12_zone_2',
            'Profile Error Lobe A12 Zone 3 - CTF 13': 'profile_error_lobe_12_zone_3',
            'Profile Error Lobe A12 Zone 4 - CTF 12': 'profile_error_lobe_12_zone_4',
            'Profile Error Lobe A21  Zone 1 - CTF 12': 'profile_error_lobe_21_zone_1',
            'Profile Error Lobe A21  Zone 2 - CTF 13': 'profile_error_lobe_21_zone_2',
            'Profile Error Lobe A21 Zone 3 - CTF 13': 'profile_error_lobe_21_zone_3',
            'Profile Error Lobe A21 Zone 4 - CTF 12': 'profile_error_lobe_21_zone_4',
            'Profile Error Lobe A22  Zone 1 - CTF 12': 'profile_error_lobe_22_zone_1',
            'Profile Error Lobe A22  Zone 2 - CTF 13': 'profile_error_lobe_22_zone_2',
            'Profile Error Lobe A22 Zone 3 - CTF 13': 'profile_error_lobe_22_zone_3',
            'Profile Error Lobe A22 Zone 4 - CTF 12': 'profile_error_lobe_22_zone_4',
            'Profile Error Lobe A31  Zone 1 - CTF 12': 'profile_error_lobe_31_zone_1',
            'Profile Error Lobe A31  Zone 2 - CTF 13': 'profile_error_lobe_31_zone_2',
            'Profile Error Lobe A31 Zone 3 - CTF 13': 'profile_error_lobe_31_zone_3',
            'Profile Error Lobe A31 Zone 4 - CTF 12': 'profile_error_lobe_31_zone_4',
            'Profile Error Lobe A32  Zone 1 - CTF 12': 'profile_error_lobe_32_zone_1',
            'Profile Error Lobe A32  Zone 2 - CTF 13': 'profile_error_lobe_32_zone_2',
            'Profile Error Lobe A32 Zone 3 - CTF 13': 'profile_error_lobe_32_zone_3',
            'Profile Error Lobe A32 Zone 4 - CTF 12': 'profile_error_lobe_32_zone_4',
            'Profile Error PumpLobe closing side - CTF 45.2': 'profile_error_pumplobe_closing_side',
            'Profile Error PumpLobe closing side - CTF 45.2 ': 'profile_error_pumplobe_closing_side',
            'Profile Error PumpLobe rising side - CTF 45.1': 'profile_error_pumplobe_rising_side',
            'Profile Error PumpLobe rising side - CTF 45.1 ': 'profile_error_pumplobe_rising_side',

            # Velocity Error Measurements - Both variants map to universal fields
            'Velocity Error Lobe E11 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_11_zone_1',
            'Velocity Error Lobe E11 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_11_zone_2',
            'Velocity Error Lobe E11 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_11_zone_3',
            'Velocity Error Lobe E11 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_11_zone_4',
            'Velocity Error Lobe E12 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_12_zone_1',
            'Velocity Error Lobe E12 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_12_zone_2',
            'Velocity Error Lobe E12 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_12_zone_3',
            'Velocity Error Lobe E12 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_12_zone_4',
            'Velocity Error Lobe E21 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_21_zone_1',
            'Velocity Error Lobe E21 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_21_zone_2',
            'Velocity Error Lobe E21 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_21_zone_3',
            'Velocity Error Lobe E21 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_21_zone_4',
            'Velocity Error Lobe E22 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_22_zone_1',
            'Velocity Error Lobe E22 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_22_zone_2',
            'Velocity Error Lobe E22 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_22_zone_3',
            'Velocity Error Lobe E22 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_22_zone_4',
            'Velocity Error Lobe E31 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_31_zone_1',
            'Velocity Error Lobe E31 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_31_zone_2',
            'Velocity Error Lobe E31 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_31_zone_3',
            'Velocity Error Lobe E31 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_31_zone_4',
            'Velocity Error Lobe E32 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_32_zone_1',
            'Velocity Error Lobe E32 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_32_zone_2',
            'Velocity Error Lobe E32 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_32_zone_3',
            'Velocity Error Lobe E32 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_32_zone_4',
            'Velocity Error Lobe A11 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_11_zone_1',
            'Velocity Error Lobe A11 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_11_zone_2',
            'Velocity Error Lobe A11 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_11_zone_3',
            'Velocity Error Lobe A11 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_11_zone_4',
            'Velocity Error Lobe A12 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_12_zone_1',
            'Velocity Error Lobe A12 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_12_zone_2',
            'Velocity Error Lobe A12 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_12_zone_3',
            'Velocity Error Lobe A12 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_12_zone_4',
            'Velocity Error Lobe A21 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_21_zone_1',
            'Velocity Error Lobe A21 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_21_zone_2',
            'Velocity Error Lobe A21 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_21_zone_3',
            'Velocity Error Lobe A21 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_21_zone_4',
            'Velocity Error Lobe A22 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_22_zone_1',
            'Velocity Error Lobe A22 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_22_zone_2',
            'Velocity Error Lobe A22 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_22_zone_3',
            'Velocity Error Lobe A22 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_22_zone_4',
            'Velocity Error Lobe A31 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_31_zone_1',
            'Velocity Error Lobe A31 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_31_zone_2',
            'Velocity Error Lobe A31 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_31_zone_3',
            'Velocity Error Lobe A31 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_31_zone_4',
            'Velocity Error Lobe A32 Zone 1 (1°) - CTF 14': 'velocity_error_lobe_32_zone_1',
            'Velocity Error Lobe A32 Zone 2 (1°) - CTF 14': 'velocity_error_lobe_32_zone_2',
            'Velocity Error Lobe A32 Zone 3 (1°) - CTF 14': 'velocity_error_lobe_32_zone_3',
            'Velocity Error Lobe A32 Zone 4 (1°) - CTF 14': 'velocity_error_lobe_32_zone_4',
            'Velocity Error PumpLobe 1° closing side - CTF 46.2': 'velocity_error_pumplobe_1_deg_closing_side',
            'Velocity Error PumpLobe 1° rising side - CTF 46.1': 'velocity_error_pumplobe_1_deg_rising_side',

            # Width Measurements - Both variants map to universal fields
            'Width Lobe E11 - CTF 207': 'width_lobe_11',
            'Width Lobe E12 - CTF 207': 'width_lobe_12',
            'Width Lobe E21 - CTF 207': 'width_lobe_21',
            'Width Lobe E22 - CTF 207': 'width_lobe_22',
            'Width Lobe E31 - CTF 207': 'width_lobe_31',
            'Width Lobe E32 - CTF 207': 'width_lobe_32',
            'Width Lobe A11 - CTF 206': 'width_lobe_11',
            'Width Lobe A12 - CTF 206': 'width_lobe_12',
            'Width Lobe A21 - CTF 206': 'width_lobe_21',
            'Width Lobe A22 - CTF 206': 'width_lobe_22',
            'Width Lobe A31 - CTF 206': 'width_lobe_31',
            'Width Lobe A32 - CTF 206': 'width_lobe_32',
            'Width Pump Lobe - CTF 80': 'width_pump_lobe',

            # Straightness Lobe - Both variants map to universal fields
            'Straightness Lobe E11 - CTF 88': 'straightness_lobe_11',
            'Straightness Lobe E12 - CTF 88': 'straightness_lobe_12',
            'Straightness Lobe E21 - CTF 88': 'straightness_lobe_21',
            'Straightness Lobe E22 - CTF 88': 'straightness_lobe_22',
            'Straightness Lobe E31 - CTF 88': 'straightness_lobe_31',
            'Straightness Lobe E32 - CTF 88': 'straightness_lobe_32',
            'Straightness Lobe A11 - CTF 88': 'straightness_lobe_11',
            'Straightness Lobe A12 - CTF 88': 'straightness_lobe_12',
            'Straightness Lobe A21 - CTF 88': 'straightness_lobe_21',
            'Straightness Lobe A22 - CTF 88': 'straightness_lobe_22',
            'Straightness Lobe A31 - CTF 88': 'straightness_lobe_31',
            'Straightness Lobe A32 - CTF 88': 'straightness_lobe_32',
            'Straightness Pump Lobe - CTF 88': 'straightness_pump_lobe',

            # Parallelism - Both variants map to universal fields
            'Parallelism Lobe E11 A1-B1 - CTF 89': 'parallelism_lobe_11_a1_b1',
            'Parallelism Lobe E12 A1-B1 - CTF 89': 'parallelism_lobe_12_a1_b1',
            'Parallelism Lobe E21 A1-B1 - CTF 89': 'parallelism_lobe_21_a1_b1',
            'Parallelism Lobe E22 A1-B1 - CTF 89': 'parallelism_lobe_22_a1_b1',
            'Parallelism Lobe E31 A1-B1 - CTF 89': 'parallelism_lobe_31_a1_b1',
            'Parallelism Lobe E32 A1-B1 - CTF 89': 'parallelism_lobe_32_a1_b1',
            'Parallelism Lobe A11 A1-B1 - CTF 89': 'parallelism_lobe_11_a1_b1',
            'Parallelism Lobe A12 A1-B1 - CTF 89': 'parallelism_lobe_12_a1_b1',
            'Parallelism Lobe A21 A1-B1 - CTF 89': 'parallelism_lobe_21_a1_b1',
            'Parallelism Lobe A22 A1-B1 - CTF 89': 'parallelism_lobe_22_a1_b1',
            'Parallelism Lobe A31 A1-B1 - CTF 89': 'parallelism_lobe_31_a1_b1',
            'Parallelism Lobe A32 A1-B1 - CTF 89': 'parallelism_lobe_32_a1_b1',
            'Parallelism Pump Lobe A1-B1 - CTF 89': 'parallelism_pump_lobe_a1_b1',

            # M (PSA lobing notation) - Both variants map to universal fields
            'M (PSA lobing notation)  Lobe E11 ': 'm_psa_lobing_notation_lobe_11',
            'M (PSA lobing notation)  Lobe E12 ': 'm_psa_lobing_notation_lobe_12',
            'M (PSA lobing notation)  Lobe E21 ': 'm_psa_lobing_notation_lobe_21',
            'M (PSA lobing notation)  Lobe E22 ': 'm_psa_lobing_notation_lobe_22',
            'M (PSA lobing notation)  Lobe E31 ': 'm_psa_lobing_notation_lobe_31',
            'M (PSA lobing notation)  Lobe E32 ': 'm_psa_lobing_notation_lobe_32',
            'M (PSA lobing notation)  Lobe A11 ': 'm_psa_lobing_notation_lobe_11',
            'M (PSA lobing notation)  Lobe A12 ': 'm_psa_lobing_notation_lobe_12',
            'M (PSA lobing notation)  Lobe A21 ': 'm_psa_lobing_notation_lobe_21',
            'M (PSA lobing notation)  Lobe A22 ': 'm_psa_lobing_notation_lobe_22',
            'M (PSA lobing notation)  Lobe A31 ': 'm_psa_lobing_notation_lobe_31',
            'M (PSA lobing notation)  Lobe A32 ': 'm_psa_lobing_notation_lobe_32',
            'M (PSA lobing notation)  PumpLobe ': 'm_psa_lobing_notation_pumplobe',
        }

    def _load_aumann_tolerances(self, variant):
        """Load JSON tolerance file for the specified variant (480 or 980)"""
        try:
            import json
            import os
            
            # Determine variant from serial number prefix
            if variant == '480':
                tolerance_file = '480.json'
            elif variant == '980':
                tolerance_file = '980.json'
            else:
                _logger.warning(f"Unknown variant: {variant}, using default tolerances")
                return {}
            
            # Try to load from module data directory first
            try:
                from odoo.modules import get_module_resource
                tolerance_path = get_module_resource('manufacturing_dashboard', 'data', 'aumann_tolerances', tolerance_file)
                if tolerance_path and os.path.exists(tolerance_path):
                    with open(tolerance_path, 'r') as f:
                        tolerances = json.load(f)
                        _logger.info(f"Loaded tolerances for variant {variant} from module data")
                        return tolerances
            except Exception as e:
                _logger.debug(f"Could not load tolerances from module data: {e}")
            
            # Fallback: try to load from configured tolerance directory
            if hasattr(self, 'aumann_tolerance_dirs') and self.aumann_tolerance_dirs:
                tolerance_dirs = self._parse_multi_paths(self.aumann_tolerance_dirs)
                for tolerance_dir in tolerance_dirs:
                    tolerance_path = os.path.join(tolerance_dir, tolerance_file)
                    if os.path.exists(tolerance_path):
                        with open(tolerance_path, 'r') as f:
                            tolerances = json.load(f)
                            _logger.info(f"Loaded tolerances for variant {variant} from {tolerance_path}")
                            return tolerances
            
            _logger.warning(f"Could not find tolerance file for variant {variant}")
            return {}
            
        except Exception as e:
            _logger.error(f"Error loading tolerances for variant {variant}: {e}")
            return {}

    def _determine_aumann_result(self, create_vals):
        """Determine pass/reject result based on Aumann measurements using JSON tolerances"""
        try:
            # Extract serial number to determine variant
            serial_number = create_vals.get('serial_number', '')
            if not serial_number:
                _logger.warning("No serial number found in create_vals, using default tolerances")
                return self._determine_aumann_result_fallback(create_vals)
            
            # Determine variant from serial prefix
            if serial_number.startswith('480'):
                variant = '480'
            elif serial_number.startswith('980'):
                variant = '980'
            else:
                _logger.warning(f"Unknown serial prefix: {serial_number[:3]}, using default tolerances")
                return self._determine_aumann_result_fallback(create_vals)
            
            # Load tolerances for this variant
            tolerances = self._load_aumann_tolerances(variant)
            if not tolerances:
                _logger.warning(f"No tolerances loaded for variant {variant}, using default tolerances")
                return self._determine_aumann_result_fallback(create_vals)
            
            # Check each tolerance
            for field_name, (min_val, max_val) in tolerances.items():
                if field_name in create_vals and create_vals[field_name] is not None:
                    try:
                        measured_value = float(create_vals[field_name])
                        if not (min_val <= measured_value <= max_val):
                            _logger.info(f"Measurement {field_name}={measured_value} out of tolerance [{min_val}, {max_val}] for {serial_number}")
                            return 'reject'
                    except (ValueError, TypeError) as e:
                        _logger.warning(f"Could not compare {field_name}={create_vals[field_name]} with tolerance: {e}")
                        continue
            
            _logger.debug(f"All measurements within tolerance for {serial_number}")
            return 'pass'
            
        except Exception as e:
            _logger.error(f"Error in tolerance evaluation for {serial_number}: {e}")
            return self._determine_aumann_result_fallback(create_vals)

    def _determine_aumann_result_fallback(self, create_vals):
        """Fallback result determination using hardcoded tolerances"""
        # Define critical measurement tolerances (fallback)
        critical_tolerances = {
            'diameter_journal_a1': (23.959, 23.980),
            'diameter_journal_a2': (23.959, 23.980),
            'diameter_journal_a3': (23.959, 23.980),
            'diameter_journal_b1': (28.959, 28.980),
            'diameter_journal_b2': (28.959, 28.980),
        }
        
        # Check critical measurements
        for field, (min_val, max_val) in critical_tolerances.items():
            if field in create_vals and create_vals[field] is not None:
                if not (min_val <= create_vals[field] <= max_val):
                    return 'reject'
        
        return 'pass'

    def _sync_gauging_data(self):
        """Sync Gauging system data from CSV file"""
        _logger.info(f"Starting Gauging data sync for machine: {self.machine_name} from {self.csv_file_path}")
        
        try:
            # Check file existence and readability
            if not os.path.exists(self.csv_file_path):
                _logger.error(f"Gauging CSV file not found: {self.csv_file_path}")
                self.status = 'error'
                return
            if not os.access(self.csv_file_path, os.R_OK):
                _logger.error(f"Gauging CSV file not readable: {self.csv_file_path}. Check permissions.")
                self.status = 'error'
                return

            # Try to import required libraries
            try:
                import csv
                from datetime import datetime
            except ImportError:
                _logger.error("csv module is required for CSV file processing.")
                self.status = 'error'
                return

            records_created = 0
            
            # Read CSV file
            try:
                with open(self.csv_file_path, 'r', encoding='utf-8') as csvfile:
                    # Detect delimiter
                    sample = csvfile.read(1024)
                    csvfile.seek(0)
                    sniffer = csv.Sniffer()
                    delimiter = sniffer.sniff(sample).delimiter
                    
                    reader = csv.DictReader(csvfile, delimiter=delimiter)
                    _logger.info(f"Gauging CSV file loaded successfully with delimiter: '{delimiter}'")
                    
                    for row_index, row in enumerate(reader):
                        try:
                            # Extract data from CSV row
                            component_name = row.get('COMPONENT_NAME', '').strip()
                            serial_number = row.get('SERIAL_NUMBER', '').strip()
                            date_time_str = row.get('DATE_TIME', '').strip()
                            result_str = row.get('RESULT', '').strip()
                            
                            # Skip empty rows, calibration master entries, or invalid serial numbers
                            if not serial_number or serial_number.lower() == 'calibration master':
                                continue
                            
                            # Only process serial numbers that start with 480 or 980
                            if not (serial_number.startswith('480') or serial_number.startswith('980')):
                                _logger.debug(f"Skipping serial number {serial_number} - does not start with 480 or 980")
                                continue
                            
                            # Check if record already exists to prevent duplicates
                            existing = self.env['manufacturing.gauging.measurement'].search([
                                ('serial_number', '=', serial_number),
                                ('machine_id', '=', self.id),
                                ('test_date', '=', self._parse_csv_datetime(date_time_str))
                            ], limit=1)
                            
                            if existing:
                                _logger.debug(f"Gauging record for Serial Number {serial_number} already exists. Skipping.")
                                continue
                            
                            # Parse test date
                            test_date = self._parse_csv_datetime(date_time_str)
                            
                            # Parse angle measurement and determine status
                            angle_measurement = result_str
                            status_mapped, angle_within_tolerance, rejection_reason = self._evaluate_gauging_result(result_str)
                            
                            # Prepare data for creation
                            create_vals = {
                                'machine_id': self.id,
                                'test_date': test_date,
                                'component_name': component_name,
                                'serial_number': serial_number,
                                'job_number': serial_number,  # Using serial number as job number
                                'angle_measurement': angle_measurement,
                                'status': status_mapped,
                                'within_tolerance': angle_within_tolerance,
                                'raw_data': str(row)[:2000]  # Limit raw data size
                            }
                            
                            if rejection_reason:
                                create_vals['rejection_reason'] = rejection_reason
                            
                            # Add tolerance data from machine config
                            if self.gauging_upper_tolerance is not None and self.gauging_lower_tolerance is not None:
                                create_vals.update({
                                    'upper_tolerance': self.gauging_upper_tolerance,
                                    'lower_tolerance': self.gauging_lower_tolerance,
                                    'nominal_value': self.gauging_nominal_value or 0.0
                                })
                            
                            # Create the record
                            new_record = self.env['manufacturing.gauging.measurement'].create(create_vals)
                            records_created += 1
                            _logger.debug(f"Successfully created Gauging record for Serial Number: {serial_number}")
                            
                        except Exception as e:
                            _logger.error(f"Failed to process Gauging row {row_index}: {e}")
                            continue
                    
            except Exception as e:
                _logger.error(f"Failed to read CSV file: {str(e)}")
                self.status = 'error'
                return
            
            _logger.info(f"Gauging data sync completed. Total records created: {records_created}")
            
        except FileNotFoundError:
            _logger.error(f"Gauging CSV file not found at {self.csv_file_path}. Please check the path.")
            self.status = 'error'
        except Exception as e:
            _logger.error(f"An unexpected error occurred during Gauging data sync: {e}", exc_info=True)
            self.status = 'error'

    def _parse_csv_datetime(self, date_time_str):
        """Parse datetime from CSV format like '10/06/2025 01:21:09 PM' and preserve exact time"""
        if not date_time_str:
            return fields.Datetime.now()
            
        try:
            from datetime import datetime
            import pytz
            
            # Try different date formats for US format with AM/PM
            date_formats = [
                '%m/%d/%Y %I:%M:%S %p',  # US format with AM/PM
                '%d/%m/%Y %H:%M:%S',     # European format 24h
                '%Y-%m-%d %H:%M:%S',     # ISO format
                '%m/%d/%Y %H:%M:%S',     # US format 24h
            ]
            
            for fmt in date_formats:
                try:
                    # Parse the datetime string
                    parsed_dt = datetime.strptime(date_time_str.strip(), fmt)
                    
                    # Since CSV contains IST time, we need to treat it as IST and convert to UTC
                    # for Odoo to store correctly, then it will display back as IST
                    ist = pytz.timezone('Asia/Kolkata')
                    ist_dt = ist.localize(parsed_dt)
                    utc_dt = ist_dt.astimezone(pytz.UTC)
                    
                    # Return in UTC format for Odoo storage
                    return utc_dt.strftime('%Y-%m-%d %H:%M:%S')
                    
                except ValueError:
                    continue
            
            # If all formats failed, log and use current time
            _logger.warning(f"Could not parse date '{date_time_str}' with any known format. Using current time.")
            return fields.Datetime.now()
            
        except Exception as e:
            _logger.warning(f"Could not parse date '{date_time_str}': {e}. Using current time.")
            return fields.Datetime.now()
    
    def _evaluate_gauging_result(self, result_str):
        """Evaluate gauging result and determine status, tolerance, and rejection reason"""
        if not result_str:
            return 'accept', True, None
            
        try:
            # Parse angle to decimal degrees
            decimal_degrees = self._parse_angle_to_decimal(result_str)
            
            # Check against machine tolerance settings
            if (self.gauging_upper_tolerance is not None and 
                self.gauging_lower_tolerance is not None):
                
                if not (self.gauging_lower_tolerance <= decimal_degrees <= self.gauging_upper_tolerance):
                    rejection_reason = (f"Angle {decimal_degrees:.4f}° out of tolerance "
                                      f"({self.gauging_lower_tolerance:.4f}° - {self.gauging_upper_tolerance:.4f}°)")
                    return 'reject', False, rejection_reason
            
            # Default to accept if within tolerance or no tolerance set
            return 'accept', True, None
            
        except Exception as e:
            _logger.warning(f"Failed to evaluate gauging result '{result_str}': {e}")
            return 'accept', True, None

    def _safe_float(self, value):
        """Safely convert value to float"""
        try:
            import pandas as pd
            if pd.isna(value) or value == '' or str(value).lower() == 'nan':
                return None
            return float(value)
        except:
            return None

    def _parse_angle_to_decimal(self, angle_str):
        """Parse angle measurement from format like "1°30'0"" to decimal degrees"""
        if not angle_str:
            return 0.0
            
        try:
            # Remove any extra quotes or spaces
            angle_str = str(angle_str).strip().strip('"')
            
            # Pattern to match degrees°minutes'seconds" format
            import re
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
                    
                return decimal_degrees
            else:
                # Try to parse as simple decimal
                try:
                    return float(angle_str)
                except:
                    return 0.0
                    
        except Exception as e:
            _logger.warning(f"Failed to parse angle measurement '{angle_str}': {e}")
            return 0.0

    def get_sync_progress(self):
        """Get current sync progress information"""
        return {
            'machine_name': self.machine_name,
            'status': self.status,
            'sync_progress': self.sync_progress,
            'sync_stage': self.sync_stage,
            'sync_processed_records': self.sync_processed_records,
            'sync_total_records': self.sync_total_records,
            'sync_start_time': self.sync_start_time.isoformat() if self.sync_start_time else None,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'estimated_completion': self.sync_estimated_completion.isoformat() if self.sync_estimated_completion else None,
        }

    @api.model
    def get_dashboard_data(self):
        """Get dashboard data for frontend"""
        machines = self.search([('is_active', '=', True)])

        # Get today's statistics
        today = fields.Date.today()
        today_parts = self.env['manufacturing.part.quality'].search([
            ('test_date', '>=', today)
        ])

        dashboard_data = {
            'machines': [],
            'statistics': {
                'total_parts': len(today_parts),
                'passed_parts': len(today_parts.filtered(lambda p: p.final_result == 'pass')),
                'rejected_parts': len(today_parts.filtered(lambda p: p.final_result == 'reject')),
                'pending_parts': len(today_parts.filtered(lambda p: p.final_result == 'pending')),
            },
            'last_updated': fields.Datetime.now().isoformat()
        }

        for machine in machines:
            machine_data = {
                'id': machine.id,
                'name': machine.machine_name,
                'machine_type': machine.machine_type,
                'status': machine.status,
                'parts_today': machine.parts_processed_today,
                'rejection_rate': round(machine.rejection_rate, 2),
                'last_sync': machine.last_sync.isoformat() if machine.last_sync else None,
            }
            dashboard_data['machines'].append(machine_data)

        return dashboard_data

    # Add these enhanced methods to your machine_config.py file

    @api.model
    def get_enhanced_dashboard_data(self, filter_type='today'):
        """Enhanced dashboard data with analytics support for selected window"""
        machines = self.search([('is_active', '=', True)])
        # Determine date window
        today = fields.Date.today()
        if filter_type == 'today':
            start_date = today
            end_date = today
        elif filter_type == 'week':
            start_date = today - timedelta(days=7)
            end_date = today
        elif filter_type == 'month':
            start_date = today - timedelta(days=30)
            end_date = today
        elif filter_type == 'year':
            start_date = today - timedelta(days=365)
            end_date = today
        else:
            start_date = today
            end_date = today

        dashboard_data = {
            'machines': [],
            'statistics': {
                'total_parts': 0,
                'passed_parts': 0,
                'rejected_parts': 0,
                'pending_parts': 0,
            },
            'last_updated': fields.Datetime.now().isoformat(),
            'analytics': {
                'hourly_production': [],
                'daily_trends': [],
                'machine_efficiency': {}
            }
        }

        total_parts = 0
        total_passed = 0
        total_rejected = 0

        for machine in machines:
            # Get filtered window stats for this machine
            machine_stats = self._get_machine_stats_for_period(machine.id, start_date, end_date)

            machine_info = {
                'id': machine.id,
                'name': machine.machine_name,
                'machine_type': machine.machine_type,
                'status': machine.status,
                'parts_today': machine_stats['total_count'],
                'ok_count': machine_stats['ok_count'],
                'reject_count': machine_stats['reject_count'],
                'rejection_rate': machine_stats['rejection_rate'],
                'last_sync': machine.last_sync.isoformat() if machine.last_sync else None,
                'efficiency': max(0, 100 - machine_stats['rejection_rate']),
            }

            dashboard_data['machines'].append(machine_info)

            # Aggregate totals
            total_parts += machine_stats['total_count']
            total_passed += machine_stats['ok_count']
            total_rejected += machine_stats['reject_count']

        dashboard_data['statistics'] = {
            'total_parts': total_parts,
            'passed_parts': total_passed,
            'rejected_parts': total_rejected,
            'pending_parts': 0,  # Calculate if you have pending logic
        }

        dashboard_data['window'] = {
            'filter_type': filter_type,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
        }

        return dashboard_data

    def _get_machine_today_stats(self, machine_id):
        """Get today's statistics for a specific machine"""
        today = fields.Date.today()
        machine = self.browse(machine_id)

        stats = {
            'total_count': 0,
            'ok_count': 0,
            'reject_count': 0,
            'rejection_rate': 0.0
        }

        if machine.machine_type == 'vici_vision':
            records = self.env['manufacturing.vici.vision'].search([
                ('machine_id', '=', machine_id),
                ('test_date', '>=', today)
            ])
            stats['total_count'] = len(records)
            stats['ok_count'] = len(records.filtered(lambda r: r.result == 'pass'))
            stats['reject_count'] = len(records.filtered(lambda r: r.result == 'reject'))

        elif machine.machine_type == 'ruhlamat':
            records = self.env['manufacturing.ruhlamat.press'].search([
                ('machine_id', '=', machine_id),
                ('test_date', '>=', today)
            ])
            stats['total_count'] = len(records)
            stats['ok_count'] = len(records.filtered(lambda r: r.result == 'pass'))
            stats['reject_count'] = len(records.filtered(lambda r: r.result == 'reject'))

        elif machine.machine_type == 'aumann':
            records = self.env['manufacturing.aumann.measurement'].search([
                ('machine_id', '=', machine_id),
                ('test_date', '>=', today)
            ])
            stats['total_count'] = len(records)
            stats['ok_count'] = len(records.filtered(lambda r: r.result == 'pass'))
            stats['reject_count'] = len(records.filtered(lambda r: r.result == 'reject'))

        elif machine.machine_type == 'gauging':
            records = self.env['manufacturing.gauging.measurement'].search([
                ('machine_id', '=', machine_id),
                ('test_date', '>=', today)
            ])
            stats['total_count'] = len(records)
            stats['ok_count'] = len(records.filtered(lambda r: r.result == 'pass'))
            stats['reject_count'] = len(records.filtered(lambda r: r.result == 'reject'))

        # Calculate rejection rate
        if stats['total_count'] > 0:
            stats['rejection_rate'] = round((stats['reject_count'] / stats['total_count']) * 100, 2)

        return stats

    def _get_machine_stats_for_period(self, machine_id, start_date, end_date):
        """Get statistics for a specific machine within a date range"""
        machine = self.browse(machine_id)

        stats = {
            'total_count': 0,
            'ok_count': 0,
            'reject_count': 0,
            'rejection_rate': 0.0
        }

        if machine.machine_type == 'vici_vision':
            records = self.env['manufacturing.vici.vision'].search([
                ('machine_id', '=', machine_id),
                ('test_date', '>=', start_date),
                ('test_date', '<=', end_date)
            ])
            stats['total_count'] = len(records)
            stats['ok_count'] = len(records.filtered(lambda r: r.result == 'pass'))
            stats['reject_count'] = len(records.filtered(lambda r: r.result == 'reject'))

        elif machine.machine_type == 'ruhlamat':
            records = self.env['manufacturing.ruhlamat.press'].search([
                ('machine_id', '=', machine_id),
                ('test_date', '>=', start_date),
                ('test_date', '<=', end_date)
            ])
            stats['total_count'] = len(records)
            stats['ok_count'] = len(records.filtered(lambda r: r.result == 'pass'))
            stats['reject_count'] = len(records.filtered(lambda r: r.result == 'reject'))

        elif machine.machine_type == 'aumann':
            records = self.env['manufacturing.aumann.measurement'].search([
                ('machine_id', '=', machine_id),
                ('test_date', '>=', start_date),
                ('test_date', '<=', end_date)
            ])
            stats['total_count'] = len(records)
            stats['ok_count'] = len(records.filtered(lambda r: r.result == 'pass'))
            stats['reject_count'] = len(records.filtered(lambda r: r.result == 'reject'))

        elif machine.machine_type == 'gauging':
            records = self.env['manufacturing.gauging.measurement'].search([
                ('machine_id', '=', machine_id),
                ('test_date', '>=', start_date),
                ('test_date', '<=', end_date)
            ])
            stats['total_count'] = len(records)
            stats['ok_count'] = len(records.filtered(lambda r: r.result == 'pass'))
            stats['reject_count'] = len(records.filtered(lambda r: r.result == 'reject'))

        # Calculate rejection rate
        if stats['total_count'] > 0:
            stats['rejection_rate'] = round((stats['reject_count'] / stats['total_count']) * 100, 2)

        return stats

    @api.model
    def get_machine_detail_data(self, machine_id, filter_type='today'):
        """Enhanced machine detail data with analytics"""
        try:
            machine = self.browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}

            # Validate parameters
            filter_type = str(filter_type) if filter_type else 'today'

            # Calculate date range based on filter_type
            today = fields.Date.today()
            if filter_type == 'today':
                start_date = today
                end_date = today
            elif filter_type == 'week':
                start_date = today - timedelta(days=7)
                end_date = today
            elif filter_type == 'month':
                start_date = today - timedelta(days=30)
                end_date = today
            elif filter_type == 'year':
                start_date = today - timedelta(days=365)
                end_date = today
            else:
                start_date = today
                end_date = today

            # Get basic stats for the filtered period
            stats = self._get_machine_stats_for_period(machine_id, start_date, end_date)

            # Initialize response data
            machine_data = {
                'machine_info': {
                    'id': machine.id,
                    'name': machine.machine_name,
                    'machine_type': machine.machine_type,
                    'status': machine.status,
                    'last_sync': machine.last_sync.isoformat() if machine.last_sync else None,
                },
                'summary': {
                    'total_count': stats['total_count'],
                    'ok_count': stats['ok_count'],
                    'reject_count': stats['reject_count'],
                },
                'analytics': self._build_analytics(machine_id, start_date, end_date)
            }


            return machine_data

        except Exception as e:
            _logger.error(f"Error in get_machine_detail_data: {str(e)}")
            return {'error': f'Failed to load machine detail data: {str(e)}'}

    def _get_hourly_production(self, machine_id, date):
        """Get hourly production data for charts"""
        machine = self.browse(machine_id)
        hourly_data = []

        # Generate 24 hours of data
        for hour in range(24):
            start_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=hour)
            end_time = start_time + timedelta(hours=1)

            if machine.machine_type == 'vici_vision':
                count = self.env['manufacturing.vici.vision'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', start_time),
                    ('test_date', '<', end_time)
                ])
            elif machine.machine_type == 'ruhlamat':
                count = self.env['manufacturing.ruhlamat.press'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', start_time),
                    ('test_date', '<', end_time)
                ])
            elif machine.machine_type == 'aumann':
                count = self.env['manufacturing.aumann.measurement'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', start_time),
                    ('test_date', '<', end_time)
                ])
            elif machine.machine_type == 'gauging':
                count = self.env['manufacturing.gauging.measurement'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', start_time),
                    ('test_date', '<', end_time)
                ])
            else:
                count = 0

            hourly_data.append({
                'hour': f"{hour:02d}:00",
                'count': count
            })

        return hourly_data

    def _build_analytics(self, machine_id, start_date, end_date):
        """Build analytics payload based on the selected date range"""
        machine = self.browse(machine_id)

        # Normalize to datetimes (inclusive start, exclusive end)
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        total_days = (end_dt - start_dt).days

        # Decide interval based on date range
        if total_days <= 1:
            interval = 'hour'
        elif total_days <= 31:
            interval = 'day'
        else:
            interval = 'month'

        production_series = self._get_production_series(machine, start_dt, end_dt, interval)
        rejection_series = self._get_rejection_rate_series(machine, start_dt, end_dt, interval)
        measurement_avg = self._get_measurement_average(machine, start_dt, end_dt)

        return {
            'production_series': production_series,  # {labels:[], values:[]}
            'rejection_series': rejection_series,    # {labels:[], values:[]}
            'measurement_avg': measurement_avg      # {labels:[], values:[]}
        }

    def _get_model_for_machine(self, machine):
        if machine.machine_type == 'vici_vision':
            return self.env['manufacturing.vici.vision']
        if machine.machine_type == 'ruhlamat':
            return self.env['manufacturing.ruhlamat.press']
        if machine.machine_type == 'aumann':
            return self.env['manufacturing.aumann.measurement']
        if machine.machine_type == 'gauging':
            return self.env['manufacturing.gauging.measurement']
        return None

    def _iter_intervals(self, start_dt, end_dt, interval):
        current = start_dt
        while current < end_dt:
            if interval == 'hour':
                nxt = current + timedelta(hours=1)
                label = current.strftime('%H:00')
            elif interval == 'day':
                nxt = current + timedelta(days=1)
                label = current.strftime('%Y-%m-%d')
            elif interval == 'month':
                year = current.year
                month = current.month
                if month == 12:
                    nxt = datetime(year + 1, 1, 1)
                else:
                    nxt = datetime(year, month + 1, 1)
                label = current.strftime('%Y-%m')
            else:  # year
                year = current.year
                nxt = datetime(year + 1, 1, 1)
                label = current.strftime('%Y')
            yield (current, min(nxt, end_dt), label)
            current = nxt

    def _get_production_series(self, machine, start_dt, end_dt, interval):
        model = self._get_model_for_machine(machine)
        labels, values = [], []
        if not model:
            return {'labels': labels, 'values': values}

        for begin, finish, label in self._iter_intervals(start_dt, end_dt, interval):
            count = model.search_count([
                ('machine_id', '=', machine.id),
                ('test_date', '>=', begin),
                ('test_date', '<', finish),
            ])
            labels.append(label)
            values.append(count)

        return {'labels': labels, 'values': values}

    def _get_rejection_rate_series(self, machine, start_dt, end_dt, interval):
        model = self._get_model_for_machine(machine)
        labels, values = [], []
        if not model:
            return {'labels': labels, 'values': values}

        for begin, finish, label in self._iter_intervals(start_dt, end_dt, interval):
            total = model.search_count([
                ('machine_id', '=', machine.id),
                ('test_date', '>=', begin),
                ('test_date', '<', finish),
            ])
            rejected = model.search_count([
                ('machine_id', '=', machine.id),
                ('test_date', '>=', begin),
                ('test_date', '<', finish),
                ('result', '=', 'reject'),
            ])
            rate = round((rejected / total) * 100, 2) if total else 0.0
            labels.append(label)
            values.append(rate)

        return {'labels': labels, 'values': values}

    def _get_measurement_average(self, machine, start_dt, end_dt):
        model = self._get_model_for_machine(machine)
        if not model:
            return {'labels': [], 'values': []}

        domain = [
            ('machine_id', '=', machine.id),
            ('test_date', '>=', start_dt),
            ('test_date', '<', end_dt),
        ]
        records = model.search(domain, limit=500)  # reasonable cap

        labels, values = [], []
        if machine.machine_type == 'vici_vision':
            fields_list = ['l_64_8', 'l_35_4', 'l_46_6', 'l_82', 'l_128_6', 'l_164']
            labels = ['L 64.8', 'L 35.4', 'L 46.6', 'L 82', 'L 128.6', 'L 164']
        elif machine.machine_type == 'aumann':
            fields_list = ['diameter_journal_a1', 'diameter_journal_a2', 'diameter_journal_b1', 'diameter_journal_b2']
            labels = ['Diameter A1', 'Diameter A2', 'Diameter B1', 'Diameter B2']
        elif machine.machine_type == 'gauging':
            fields_list = ['angle_degrees', 'measurement_value']
            labels = ['Angle (Degrees)', 'Measurement Value']
        else:
            fields_list = []

        for idx, f in enumerate(fields_list):
            vals = []
            for r in records:
                v = getattr(r, f, 0) or 0
                try:
                    vals.append(float(v))
                except Exception:
                    continue
            avg = round(sum(vals) / len(vals), 3) if vals else 0.0
            values.append(avg)

        return {'labels': labels, 'values': values}

    def _get_measurement_trends(self, machine_id, date):
        """Get measurement trends for radar charts"""
        machine = self.browse(machine_id)
        trends = {}

        if machine.machine_type == 'vici_vision':
            # Get latest records for trend analysis
            records = self.env['manufacturing.vici.vision'].search([
                ('machine_id', '=', machine_id),
                ('test_date', '>=', date),
                ('result', '=', 'pass')  # Only include passed parts for trend
            ], limit=10, order='test_date desc')

            if records:
                # Calculate average values for key measurements
                measurements = ['l_64_8', 'l_35_4', 'l_46_6', 'l_82', 'l_128_6', 'l_164']
                for measurement in measurements:
                    values = [getattr(r, measurement, 0) or 0 for r in records]
                    if values:
                        trends[measurement] = sum(values) / len(values)

        elif machine.machine_type == 'aumann':
            records = self.env['manufacturing.aumann.measurement'].search([
                ('machine_id', '=', machine_id),
                ('test_date', '>=', date),
                ('result', '=', 'pass')
            ], limit=10, order='test_date desc')

            if records:
                measurements = ['diameter_journal_a1', 'diameter_journal_a2', 'diameter_journal_b1']
                for measurement in measurements:
                    values = [getattr(r, measurement, 0) or 0 for r in records]
                    if values:
                        trends[measurement] = sum(values) / len(values)

        return trends

    def _get_quality_metrics(self, machine_id, date):
        """Get quality metrics for analysis"""
        machine = self.browse(machine_id)

        # Get data for the last 7 days
        start_date = date - timedelta(days=6)
        daily_metrics = []

        for i in range(7):
            current_date = start_date + timedelta(days=i)
            next_date = current_date + timedelta(days=1)

            if machine.machine_type == 'vici_vision':
                total = self.env['manufacturing.vici.vision'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', current_date),
                    ('test_date', '<', next_date)
                ])
                passed = self.env['manufacturing.vici.vision'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', current_date),
                    ('test_date', '<', next_date),
                    ('result', '=', 'pass')
                ])
            elif machine.machine_type == 'ruhlamat':
                total = self.env['manufacturing.ruhlamat.press'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', current_date),
                    ('test_date', '<', next_date)
                ])
                passed = self.env['manufacturing.ruhlamat.press'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', current_date),
                    ('test_date', '<', next_date),
                    ('result', '=', 'pass')
                ])
            elif machine.machine_type == 'aumann':
                total = self.env['manufacturing.aumann.measurement'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', current_date),
                    ('test_date', '<', next_date)
                ])
                passed = self.env['manufacturing.aumann.measurement'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', current_date),
                    ('test_date', '<', next_date),
                    ('result', '=', 'pass')
                ])
            else:
                total = passed = 0

            rejection_rate = 0
            if total > 0:
                rejection_rate = ((total - passed) / total) * 100

            daily_metrics.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'total_parts': total,
                'passed_parts': passed,
                'rejected_parts': total - passed,
                'rejection_rate': round(rejection_rate, 2)
            })

        return daily_metrics

    # Final Station Methods
    def test_plc_connection(self):
        """Test PLC connection for final station and read D0-D9 values"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return {'success': False, 'message': 'Not a final station'}
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        result = service.test_plc_connection()
        
        if result['success']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'PLC Connection Successful',
                    'message': result['message'],
                    'type': 'success',
                    'sticky': True,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'PLC Connection Failed',
                    'message': result['message'],
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def toggle_operation_mode(self):
        """Toggle operation mode for final station"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return False
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        try:
            success = service.toggle_operation_mode()
            if success:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Mode Toggled',
                        'message': f"Mode set to {self.operation_mode.upper()}",
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Mode Toggle Failed',
                        'message': 'Could not update PLC D2 register',
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except Exception as e:
            _logger.error(f"Toggle mode error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Mode Toggle Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def manual_trigger_camera(self):
        """Manual camera trigger for final station"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return False
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        try:
            success = service.manual_trigger_camera()
            if success:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Camera Triggered',
                        'message': f"Manual camera trigger successful for {self.machine_name}",
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Camera Trigger Failed',
                        'message': 'Failed to trigger camera or get QR code',
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except Exception as e:
            _logger.error(f"Manual camera trigger error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Camera Trigger Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def check_part_presence(self):
        """Check for part presence via PLC sensor"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return False
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        try:
            part_detected = service.check_part_presence()
            if part_detected:
                _logger.info(f"Part detected at {self.machine_name}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Part Detected',
                        'message': f"Part present at {self.machine_name}",
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                _logger.info(f"No part detected at {self.machine_name}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'No Part',
                        'message': f"No part present at {self.machine_name}",
                        'type': 'info',
                        'sticky': False,
                    }
                }
        except Exception as e:
            _logger.error(f"Part presence check error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Part Check Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def _read_plc_sensor(self):
        """Read PLC sensor for part presence (D0 register)"""
        try:
            import socket
            import struct
            
            # Connect to PLC and read D0 register
            with socket.create_connection((self.plc_ip_address, self.plc_port), timeout=5) as sock:
                # Create Modbus TCP read holding registers request for D0
                transaction_id = 1
                protocol_id = 0
                length = 6
                unit_id = 1
                function_code = 0x03  # Read Holding Registers
                starting_address = 0  # D0 register
                quantity = 1
                
                # Build Modbus TCP frame
                frame = struct.pack('>HHHBBHH', 
                                  transaction_id, 
                                  protocol_id, 
                                  length, 
                                  unit_id, 
                                  function_code, 
                                  starting_address, 
                                  quantity)
                
                # Send request
                sock.sendall(frame)
                import time
                time.sleep(0.1)
                
                # Receive response
                response = sock.recv(1024)
                
                if len(response) >= 9:
                    # Parse response
                    transaction_id_resp, protocol_id_resp, length_resp, unit_id_resp, function_code_resp, byte_count = struct.unpack('>HHHBBB', response[:9])
                    
                    if function_code_resp == 0x03 and byte_count >= 2:
                        # Extract D0 value
                        d0_value = struct.unpack('>H', response[9:11])[0]
                        part_present = (d0_value == 1)
                        _logger.info(f"PLC D0 (part_present) = {d0_value} -> {part_present}")
                        return part_present
                    else:
                        _logger.warning(f"Invalid PLC response for D0")
                        return False
                else:
                    _logger.warning(f"Short PLC response for D0: {len(response)} bytes")
                    return False
                    
        except Exception as e:
            _logger.error(f"Error reading PLC D0 sensor: {str(e)}")
            return False

    def _write_plc_result(self, result_value):
        """Write result to PLC D1 register (0=OK, 1=NOK)"""
        try:
            import socket
            import struct
            
            # Connect to PLC and write D1 register
            with socket.create_connection((self.plc_ip_address, self.plc_port), timeout=5) as sock:
                # Create Modbus TCP write single register request for D1
                transaction_id = 1
                protocol_id = 0
                length = 6
                unit_id = 1
                function_code = 0x06  # Write Single Register
                starting_address = 1  # D1 register
                value = result_value  # 0=OK, 1=NOK
                
                # Build Modbus TCP frame
                frame = struct.pack('>HHHBBHH', 
                                  transaction_id, 
                                  protocol_id, 
                                  length, 
                                  unit_id, 
                                  function_code, 
                                  starting_address, 
                                  value)
                
                # Send request
                sock.sendall(frame)
                import time
                time.sleep(0.1)
                
                # Receive response
                response = sock.recv(1024)
                
                if len(response) >= 12:
                    # Parse response - Write Single Register response format
                    transaction_id_resp, protocol_id_resp, length_resp, unit_id_resp, function_code_resp, address_resp, value_resp = struct.unpack('>HHHBBHH', response[:12])
                    
                    if function_code_resp == 0x06 and address_resp == 1 and value_resp == result_value:
                        _logger.info(f"PLC D1 (result) written successfully: {result_value} ({'NOK' if result_value == 1 else 'OK'})")
                        return True
                    else:
                        _logger.warning(f"Invalid PLC write response for D1: FC={function_code_resp}, Addr={address_resp}, Val={value_resp}")
                        return False
                else:
                    _logger.warning(f"Short PLC write response for D1: {len(response)} bytes")
                    return False
                    
        except Exception as e:
            _logger.error(f"Error writing PLC D1 result: {str(e)}")
            return False

    def _reset_plc_result(self):
        """Reset PLC D1 register to 0 when part is removed"""
        try:
            import socket
            import struct
            
            # Connect to PLC and write D1=0
            with socket.create_connection((self.plc_ip_address, self.plc_port), timeout=5) as sock:
                # Create Modbus TCP write single register request for D1=0
                transaction_id = 1
                protocol_id = 0
                length = 6
                unit_id = 1
                function_code = 0x06  # Write Single Register
                starting_address = 1  # D1 register
                value = 0  # Reset to 0
                
                # Build Modbus TCP frame
                frame = struct.pack('>HHHBBHH', 
                                  transaction_id, 
                                  protocol_id, 
                                  length, 
                                  unit_id, 
                                  function_code, 
                                  starting_address, 
                                  value)
                
                # Send request
                sock.sendall(frame)
                import time
                time.sleep(0.1)
                
                # Receive response
                response = sock.recv(1024)
                
                if len(response) >= 12:
                    # Parse response
                    transaction_id_resp, protocol_id_resp, length_resp, unit_id_resp, function_code_resp, address_resp, value_resp = struct.unpack('>HHHBBHH', response[:12])
                    
                    if function_code_resp == 0x06 and address_resp == 1 and value_resp == 0:
                        _logger.info(f"PLC D1 reset to 0 (part removed)")
                        return True
                    else:
                        _logger.warning(f"Invalid PLC reset response for D1: FC={function_code_resp}, Addr={address_resp}, Val={value_resp}")
                        return False
                else:
                    _logger.warning(f"Short PLC reset response for D1: {len(response)} bytes")
                    return False
                    
        except Exception as e:
            _logger.error(f"Error resetting PLC D1: {str(e)}")
            return False

    def _write_plc_register(self, register, value):
        """Write value to any PLC register (D0-D9)"""
        try:
            import socket
            import struct
            
            # Connect to PLC and write to specified register
            with socket.create_connection((self.plc_ip_address, self.plc_port), timeout=5) as sock:
                # Create Modbus TCP write single register request
                transaction_id = 1
                protocol_id = 0
                length = 6
                unit_id = 1
                function_code = 0x06  # Write Single Register
                starting_address = register  # D register number
                register_value = value  # Value to write
                
                # Build Modbus TCP frame
                frame = struct.pack('>HHHBBHH', 
                                  transaction_id, 
                                  protocol_id, 
                                  length, 
                                  unit_id, 
                                  function_code, 
                                  starting_address, 
                                  register_value)
                
                # Send request
                sock.sendall(frame)
                import time
                time.sleep(0.1)
                
                # Receive response
                response = sock.recv(1024)
                
                if len(response) >= 12:
                    # Parse response
                    transaction_id_resp, protocol_id_resp, length_resp, unit_id_resp, function_code_resp, address_resp, value_resp = struct.unpack('>HHHBBHH', response[:12])
                    
                    if function_code_resp == 0x06 and address_resp == register and value_resp == value:
                        _logger.info(f"PLC D{register} written successfully: {value}")
                        return True
                    else:
                        _logger.warning(f"Invalid PLC write response for D{register}: FC={function_code_resp}, Addr={address_resp}, Val={value_resp}")
                        return False
                else:
                    _logger.warning(f"Short PLC write response for D{register}: {len(response)} bytes")
                    return False
                    
        except Exception as e:
            _logger.error(f"Error writing PLC D{register}: {str(e)}")
            return False

    def auto_trigger_camera(self):
        """Auto camera trigger when part is detected (D0=1)"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return False
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        try:
            success = service.auto_trigger_camera()
            if success:
                _logger.info(f"Auto camera trigger successful for {self.machine_name}")
                return True
            else:
                _logger.warning(f"Auto camera trigger failed for {self.machine_name}")
                return False
        except Exception as e:
            _logger.error(f"Auto camera trigger error: {str(e)}")
            return False

    def _trigger_camera_and_get_data(self):
        """Trigger camera and get QR code data from Keyence camera"""
        try:
            import socket
            import time
            
            _logger.info(f"Connecting to Keyence camera at {self.camera_ip_address}:{self.camera_port}")
            
            # Connect to Keyence camera
            with socket.create_connection((self.camera_ip_address, self.camera_port), timeout=10) as sock:
                _logger.info("✅ Connected to Keyence camera!")
                
                # Send LON command to get serial number
                lon_response = self._send_camera_command(sock, "LON")
                _logger.info(f"LON response: {lon_response}")
                
                # Extract serial number from LON response
                serial_number = self._extract_serial_from_lon(lon_response)
                
                if serial_number:
                    # Trigger camera read
                    trg_response = self._send_camera_command(sock, "TRG")
                    _logger.info(f"TRG response: {trg_response}")
                    
                    # Wait for processing
                    time.sleep(0.5)
                    
                    # Read result
                    rd_response = self._send_camera_command(sock, "RD")
                    _logger.info(f"RD response: {rd_response}")
                    
                    # Unlock communication
                    self._send_camera_command(sock, "LOFF")
                    
                    # Prepare camera data
                    camera_data = {
                        'serial_number': serial_number,
                        'raw_data': f"Keyence camera data from {self.camera_ip_address} at {datetime.now().isoformat()}",
                        'qr_code_data': {
                            'scanned_text': serial_number,
                            'lon_response': lon_response,
                            'trg_response': trg_response,
                            'rd_response': rd_response,
                            'scan_time': datetime.now().isoformat()
                        }
                    }
                    
                    _logger.info(f"Camera data received: {camera_data}")
                    return camera_data
                else:
                    _logger.error("Failed to extract serial number from LON response")
                    return None
                    
        except Exception as e:
            _logger.error(f"Camera trigger error: {str(e)}")
            return None

    def _send_camera_command(self, sock, cmd):
        """Send a command to Keyence camera and return response"""
        try:
            import time
            sock.sendall((cmd + '\r\n').encode('ascii'))
            time.sleep(0.1)
            data = sock.recv(1024).decode('ascii').strip()
            return data
        except Exception as e:
            _logger.error(f"Error sending camera command {cmd}: {str(e)}")
            return None

    def _extract_serial_from_lon(self, lon_response):
        """Extract serial number from LON response"""
        import time, re

        try:
            _logger.info(f"Raw LON response: '{lon_response}' (type: {type(lon_response)})")

            # Clean the response - remove any whitespace and quotes
            if lon_response:
                lon_response = lon_response.strip().strip("'\"")
                _logger.info(f"Cleaned LON response: '{lon_response}'")

            # Case 1: Response is numeric → use directly
            if lon_response and lon_response.isdigit():
                serial_number = lon_response
                _logger.info(f"Extracted serial number: {serial_number}")
                return serial_number

            # Case 2: Heartbeat mode → try fetching serial for up to 5 seconds
            elif lon_response and lon_response.lower() == "heartbeat":
                _logger.info("Camera in heartbeat mode, attempting to fetch serial for up to 5 seconds...")

                start_time = time.time()
                serial_number = None

                while (time.time() - start_time) < 5:
                    # Try to get a valid LON response again
                    new_response = self._get_lon_response_safe()  # <-- replace this with your actual method call
                    if not new_response:
                        time.sleep(0.5)
                        continue

                    new_response = new_response.strip().strip("'\"")
                    if new_response.isdigit():
                        serial_number = new_response
                        _logger.info(f"Successfully fetched serial number after heartbeat: {serial_number}")
                        break
                    else:
                        _logger.debug(f"Retrying... received: {new_response}")
                        time.sleep(0.5)

                if not serial_number:
                    _logger.error("Failed to fetch serial number within 5 seconds (heartbeat mode).")
                    return None

                return serial_number

            # Case 3: Try to extract any numeric part
            else:
                numbers = re.findall(r'\d+', lon_response)
                if numbers:
                    serial_number = max(numbers, key=len)
                    _logger.info(f"Extracted numeric serial from response: {serial_number}")
                    return serial_number
                else:
                    _logger.warning(f"Invalid LON response format: '{lon_response}' "
                                    f"(isdigit: {lon_response.isdigit() if lon_response else 'None'})")
                    return None

        except Exception as e:
            _logger.error(f"Error extracting serial from LON: {str(e)}")
            return None

    def _check_all_stations_result(self, serial_number):
        """Check result from all previous stations for a given serial number"""
        try:
            _logger.info(f"Checking all stations result for serial: {serial_number}")
            
            # Check VICI Vision results
            vici_result = self._check_vici_vision_result(serial_number)
            
            # Check Ruhlamat Press results
            ruhlamat_result = self._check_ruhlamat_result(serial_number)
            
            # Check Aumann Measurement results
            aumann_result = self._check_aumann_result(serial_number)
            
            # Check Gauging results
            gauging_result = self._check_gauging_result(serial_number)
            
            # Aggregate results
            all_results = {
                'vici_vision': vici_result,
                'ruhlamat_press': ruhlamat_result,
                'aumann_measurement': aumann_result,
                'gauging': gauging_result
            }
            
            # Determine final result - OK only if ALL stations are OK
            final_result = 'ok' if all(result == 'ok' for result in all_results.values() if result is not None) else 'nok'
            
            _logger.info(f"All stations results: {all_results}")
            _logger.info(f"Final result: {final_result}")
            
            return {
                'final_result': final_result,
                'station_results': all_results,
                'serial_number': serial_number
            }
            
        except Exception as e:
            _logger.error(f"Error checking all stations result: {str(e)}")
            return {
                'final_result': 'nok',
                'station_results': {},
                'serial_number': serial_number
            }

    def get_station_results_summary(self, serial_number):
        """Get detailed summary of all station results for a serial number"""
        try:
            station_results = self._check_all_stations_result(serial_number)
            
            summary = {
                'serial_number': serial_number,
                'final_result': station_results.get('final_result', 'nok'),
                'stations': []
            }
            
            # Add detailed station information
            for station_name, result in station_results.get('station_results', {}).items():
                station_info = {
                    'name': station_name.replace('_', ' ').title(),
                    'result': result or 'Not Found',
                    'status': 'ok' if result == 'ok' else 'nok' if result == 'nok' else 'unknown'
                }
                summary['stations'].append(station_info)
            
            return summary
            
        except Exception as e:
            _logger.error(f"Error getting station results summary: {str(e)}")
            return {
                'serial_number': serial_number,
                'final_result': 'nok',
                'stations': []
            }

    def _check_vici_vision_result(self, serial_number):
        """Check VICI Vision result for serial number"""
        try:
            vici_record = self.env['manufacturing.vici.vision'].search([
                ('serial_number', '=', serial_number)
            ], limit=1, order='test_date desc')
            
            if vici_record:
                return vici_record.result
            return None
        except Exception as e:
            _logger.error(f"Error checking VICI Vision result: {str(e)}")
            return None

    def _check_ruhlamat_result(self, serial_number):
        """Check Ruhlamat Press result for serial number"""
        try:
            ruhlamat_record = self.env['manufacturing.ruhlamat.press'].search([
                ('serial_number', '=', serial_number)
            ], limit=1, order='test_date desc')
            
            if ruhlamat_record:
                return ruhlamat_record.result
            return None
        except Exception as e:
            _logger.error(f"Error checking Ruhlamat result: {str(e)}")
            return None

    def _check_aumann_result(self, serial_number):
        """Check Aumann Measurement result for serial number"""
        try:
            aumann_record = self.env['manufacturing.aumann.measurement'].search([
                ('serial_number', '=', serial_number)
            ], limit=1, order='test_date desc')
            
            if aumann_record:
                return aumann_record.result
            return None
        except Exception as e:
            _logger.error(f"Error checking Aumann result: {str(e)}")
            return None

    def _check_gauging_result(self, serial_number):
        """Check Gauging result for serial number"""
        try:
            gauging_record = self.env['manufacturing.gauging.measurement'].search([
                ('serial_number', '=', serial_number)
            ], limit=1, order='test_date desc')
            
            if gauging_record:
                return gauging_record.result
            return None
        except Exception as e:
            _logger.error(f"Error checking Gauging result: {str(e)}")
            return None

    def start_auto_monitoring(self):
        """Start automatic monitoring for part presence and camera triggering"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return False
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        try:
            _logger.info(f"Starting auto monitoring for {self.machine_name}")
            
            # Check for part presence
            part_detected = service.check_part_presence()
            
            if part_detected:
                # Part detected, trigger camera
                return service.auto_trigger_camera()
            else:
                # No part present - check if we need to reset D1
                if self.part_present:  # Part was present before, now removed
                    _logger.info("Part removed, resetting PLC D1 to 0")
                    service.reset_plc_result()
                    self.part_present = False
                    self.processing_part = False  # Reset processing flag
                else:
                    _logger.info("No part present, monitoring continues")
                return True
                
        except Exception as e:
            _logger.error(f"Auto monitoring error: {str(e)}")
            return False

    def manual_cylinder_forward_action(self):
        """Manual cylinder forward for final station (D3=1)"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return False
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        try:
            success = service.cylinder_forward_pulse()
            if success:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Cylinder Forward',
                        'message': 'Cylinder forward pulse sent (D3: 1 -> 0)',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Cylinder Forward Failed',
                        'message': 'Failed to control cylinder forward',
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except Exception as e:
            _logger.error(f"Cylinder forward error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cylinder Forward Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def manual_cylinder_reverse_action(self):
        """Manual cylinder reverse for final station (D4=1)"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return False
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        try:
            success = service.cylinder_reverse_pulse()
            if success:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Cylinder Reverse',
                        'message': 'Cylinder reverse pulse sent (D4: 1 -> 0)',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Cylinder Reverse Failed',
                        'message': 'Failed to control cylinder reverse',
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except Exception as e:
            _logger.error(f"Cylinder reverse error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cylinder Reverse Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def start_plc_monitoring_service(self):
        """Start continuous PLC monitoring service for this machine"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            _logger.warning(f"Cannot start PLC monitoring for non-final station: {self.machine_name}")
            return False
            
        if not self.plc_ip_address:
            _logger.error(f"Cannot start PLC monitoring - no IP address configured for {self.machine_name}")
            return False
            
        try:
            # Get the PLC monitor service
            plc_service = get_plc_monitor_service()
            
            # Create thread-safe callback function for part presence changes
            def part_presence_callback(machine_id, part_present, previous_state):
                """Direct callback function - immediately start auto monitoring"""
                try:
                    _logger.info(f"PLC Callback triggered: Machine {machine_id}, Part present: {previous_state} -> {part_present}")
                    if part_present:
                        _logger.info(f"Part detected on machine {machine_id} - starting direct auto monitoring")
                        # Use a new database cursor for thread safety
                        with self.env.registry.cursor() as new_cr:
                            new_env = api.Environment(new_cr, self.env.uid, self.env.context)
                            machine = new_env['manufacturing.machine.config'].browse(machine_id)
                            if machine.exists():
                                # Import FinalStationService in the callback scope
                                from .final_station_service import FinalStationService
                                service = FinalStationService(machine)
                                service.direct_auto_start_monitoring()
                                new_cr.commit()
                    else:
                        _logger.info(f"Part removed from machine {machine_id}")
                        # Reset processing flag when part is removed
                        with self.env.registry.cursor() as new_cr:
                            new_env = api.Environment(new_cr, self.env.uid, self.env.context)
                            machine = new_env['manufacturing.machine.config'].browse(machine_id)
                            if machine.exists():
                                machine.processing_part = False
                                _logger.info(f"Reset processing_part flag for machine {machine_id}")
                                new_cr.commit()
                except Exception as e:
                    _logger.error(f"Error in PLC callback for machine {machine_id}: {str(e)}")
            
            # Create thread-safe callback function for connection status changes
            def connection_status_callback(machine_id, is_connected):
                """Update PLC connection status in real-time"""
                try:
                    _logger.info(f"PLC Connection status changed: Machine {machine_id}, Connected: {is_connected}")
                    # Use a new database cursor for thread safety
                    with self.env.registry.cursor() as new_cr:
                        new_env = api.Environment(new_cr, self.env.uid, self.env.context)
                        machine = new_env['manufacturing.machine.config'].browse(machine_id)
                        if machine.exists():
                            machine.plc_online = is_connected
                            if is_connected:
                                machine.last_plc_communication = fields.Datetime.now()
                                machine.status = 'running'
                                _logger.info(f"PLC connection restored for machine {machine_id}")
                            else:
                                machine.status = 'error'
                                _logger.warning(f"PLC connection lost for machine {machine_id}")
                            new_cr.commit()
                except Exception as e:
                    _logger.error(f"Error in connection status callback for machine {machine_id}: {str(e)}")
            
            # Configure monitoring
            config = {
                'plc_ip': self.plc_ip_address,
                'plc_port': self.plc_port,
                'scan_rate': self.plc_scan_rate,
                'callback': part_presence_callback,
                'connection_callback': connection_status_callback
            }
            
            # Start monitoring
            success = plc_service.start_monitoring(self.id, config)
            
            if success:
                self.plc_monitoring_active = True
                self.plc_monitoring_errors = 0
                _logger.info(f"Started PLC monitoring service for {self.machine_name}")
                return True
            else:
                _logger.error(f"Failed to start PLC monitoring service for {self.machine_name}")
                return False
                
        except Exception as e:
            _logger.error(f"Error starting PLC monitoring service for {self.machine_name}: {str(e)}")
            return False
    
    def stop_plc_monitoring_service(self):
        """Stop continuous PLC monitoring service for this machine"""
        self.ensure_one()
        
        try:
            plc_service = get_plc_monitor_service()
            success = plc_service.stop_monitoring(self.id)
            
            if success:
                self.plc_monitoring_active = False
                _logger.info(f"Stopped PLC monitoring service for {self.machine_name}")
                return True
            else:
                _logger.warning(f"PLC monitoring service was not running for {self.machine_name}")
                return False
                
        except Exception as e:
            _logger.error(f"Error stopping PLC monitoring service for {self.machine_name}: {str(e)}")
            return False
    
    def get_plc_monitoring_status(self):
        """Get the current status of PLC monitoring service"""
        self.ensure_one()
        
        try:
            plc_service = get_plc_monitor_service()
            status = plc_service.get_monitor_status(self.id)
            
            return {
                'monitoring': status.get('monitoring', False),
                'thread_name': status.get('thread_name', ''),
                'machine_id': self.id,
                'machine_name': self.machine_name,
                'plc_ip': self.plc_ip_address,
                'plc_port': self.plc_port,
                'scan_rate': self.plc_scan_rate,
                'last_scan': self.last_plc_scan,
                'errors': self.plc_monitoring_errors
            }
        except Exception as e:
            _logger.error(f"Error getting PLC monitoring status for {self.machine_name}: {str(e)}")
            return {
                'monitoring': False,
                'error': str(e)
            }
    
    def start_all_plc_monitoring(self):
        """Start PLC monitoring for all active final stations"""
        _logger.info("Starting PLC monitoring for all final stations")
        
        final_stations = self.search([
            ('machine_type', '=', 'final_station'),
            ('is_active', '=', True),
            ('plc_ip_address', '!=', False)
        ])
        
        started_count = 0
        for station in final_stations:
            if station.start_plc_monitoring_service():
                started_count += 1
        
        _logger.info(f"Started PLC monitoring for {started_count}/{len(final_stations)} final stations")
        return started_count
    
    def stop_all_plc_monitoring(self):
        """Stop PLC monitoring for all final stations"""
        _logger.info("Stopping all PLC monitoring")
        
        try:
            plc_service = get_plc_monitor_service()
            plc_service.stop_all()
            
            # Update all final stations to reflect stopped state
            final_stations = self.search([
                ('machine_type', '=', 'final_station'),
                ('plc_monitoring_active', '=', True)
            ])
            final_stations.write({'plc_monitoring_active': False})
            
            _logger.info("Stopped all PLC monitoring services")
            return True
            
        except Exception as e:
            _logger.error(f"Error stopping all PLC monitoring: {str(e)}")
            return False

    def continuous_final_station_monitoring(self):
        """Continuous monitoring method for final stations - called by cron jobs"""
        _logger.info("Starting continuous final station monitoring")
        
        # Get all active final station machines
        final_stations = self.search([
            ('machine_type', '=', 'final_station'),
            ('is_active', '=', True),
            ('status', 'in', ['running', 'stopped'])
        ])
        
        if not final_stations:
            _logger.info("No active final stations found for monitoring")
            return True
            
        _logger.info(f"Monitoring {len(final_stations)} final station(s)")
        
        # Start PLC monitoring service for all stations that don't have it running
        plc_service = get_plc_monitor_service()
        monitoring_started = 0
        
        for station in final_stations:
            try:
                _logger.info(f"Checking final station: {station.machine_name}")
                
                # Check if PLC monitoring is already active
                if not station.plc_monitoring_active and station.plc_ip_address:
                    _logger.info(f"Starting PLC monitoring service for {station.machine_name}")
                    if station.start_plc_monitoring_service():
                        monitoring_started += 1
                elif station.plc_monitoring_active:
                    _logger.info(f"PLC monitoring already active for {station.machine_name}")
                    
                    # Check PLC directly for part presence and trigger auto monitoring
                    if station.operation_mode == 'auto' and not station.processing_part:
                        try:
                            part_detected = station.check_part_presence()
                            if part_detected:
                                _logger.info(f"Part detected on {station.machine_name}, starting auto monitoring")
                                station.start_auto_monitoring()
                        except Exception as plc_error:
                            _logger.error(f"Error checking part presence for {station.machine_name}: {str(plc_error)}")
                else:
                    _logger.warning(f"No PLC IP configured for {station.machine_name}, using fallback monitoring")
                    # Fallback to original monitoring method if no PLC service
                    if station.operation_mode == 'auto':
                        result = station.start_auto_monitoring()
                        if result:
                            _logger.info(f"Fallback monitoring completed for {station.machine_name}")
                        else:
                            _logger.warning(f"Fallback monitoring failed for {station.machine_name}")
                    
            except Exception as e:
                _logger.error(f"Error monitoring final station {station.machine_name}: {str(e)}")
                # Continue with other stations even if one fails
                continue
        
        _logger.info(f"Continuous final station monitoring completed - started {monitoring_started} PLC monitoring services")
        return True

    def final_station_status_update(self):
        """Update status for all final stations - called by cron jobs"""
        _logger.info("Starting final station status update")
        
        # Get all final station machines
        final_stations = self.search([
            ('machine_type', '=', 'final_station'),
            ('is_active', '=', True)
        ])
        
        if not final_stations:
            _logger.info("No active final stations found for status update")
            return True
            
        _logger.info(f"Updating status for {len(final_stations)} final station(s)")
        
        for station in final_stations:
            try:
                _logger.info(f"Updating status for final station: {station.machine_name}")
                
                # Test PLC connection to update online status
                plc_online = station.test_plc_connection()
                
                if plc_online:
                    station.status = 'running'
                    _logger.info(f"Station {station.machine_name} is online and running")
                else:
                    station.status = 'error'
                    _logger.warning(f"Station {station.machine_name} is offline or has connection issues")
                    
            except Exception as e:
                _logger.error(f"Error updating status for final station {station.machine_name}: {str(e)}")
                station.status = 'error'
                continue
        
        _logger.info("Final station status update completed")
        return True

    def initialize_plc_monitoring_on_startup(self):
        """Initialize PLC monitoring for all final stations on module startup"""
        _logger.info("Initializing PLC monitoring on startup")
        
        final_stations = self.search([
            ('machine_type', '=', 'final_station'),
            ('is_active', '=', True),
            ('plc_ip_address', '!=', False),
            ('operation_mode', '=', 'auto')
        ])
        
        initialized_count = 0
        for station in final_stations:
            try:
                if station.start_plc_monitoring_service():
                    initialized_count += 1
                    _logger.info(f"Initialized PLC monitoring for {station.machine_name}")
            except Exception as e:
                _logger.error(f"Failed to initialize PLC monitoring for {station.machine_name}: {str(e)}")
        
        _logger.info(f"Initialized PLC monitoring for {initialized_count}/{len(final_stations)} final stations")
        return initialized_count

    def get_plc_monitoring_summary(self):
        """Get a summary of all PLC monitoring statuses"""
        final_stations = self.search([
            ('machine_type', '=', 'final_station'),
            ('is_active', '=', True)
        ])
        
        summary = {
            'total_stations': len(final_stations),
            'monitoring_active': 0,
            'monitoring_inactive': 0,
            'no_plc_config': 0,
            'stations': []
        }
        
        for station in final_stations:
            status = station.get_plc_monitoring_status()
            station_info = {
                'id': station.id,
                'name': station.machine_name,
                'plc_ip': station.plc_ip_address,
                'monitoring': status.get('monitoring', False),
                'last_scan': station.last_plc_scan,
                'errors': station.plc_monitoring_errors
            }
            summary['stations'].append(station_info)
            
            if station.plc_ip_address:
                if status.get('monitoring', False):
                    summary['monitoring_active'] += 1
                else:
                    summary['monitoring_inactive'] += 1
            else:
                summary['no_plc_config'] += 1
        
        return summary

    def get_final_station_dashboard_data(self):
        """Get dashboard data for final station"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return {}
            
        try:
            # Get today's statistics from measurement records
            stats = self.env['manufacturing.final.station.measurement'].get_today_statistics(self.id)
            
            # Get recent measurements
            recent_measurements = self.env['manufacturing.final.station.measurement'].get_recent_measurements(self.id, limit=5)
            
            return {
                'station_name': self.machine_name,
                'status': 'online' if self.plc_online else 'offline',
                'operation_mode': self.operation_mode,
                'plc_ip_address': self.plc_ip_address,
                'camera_ip_address': self.camera_ip_address,
                'statistics': {
                    'total_parts': stats['total_measurements'],
                    'ok_parts': stats['ok_measurements'],
                    'nok_parts': stats['nok_measurements'],
                    'pass_rate': stats['pass_rate']
                },
                'last_measurement': {
                    'serial_number': self.last_serial_number,
                    'capture_time': self.last_capture_time.isoformat() if self.last_capture_time else None,
                    'result': self.last_result
                },
                'recent_measurements': recent_measurements
            }
            
        except Exception as e:
            _logger.error(f"Dashboard data error: {str(e)}")
            return {}

    def get_final_station_live_data(self):
        """Get live data for final station dashboard"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return {}
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        # Auto-start PLC monitoring service if not already running
        _logger.info(f"Checking PLC monitoring status for {self.machine_name}: active={self.plc_monitoring_active}, ip={self.plc_ip_address}")
        if not self.plc_monitoring_active and self.plc_ip_address:
            _logger.info(f"Auto-starting PLC monitoring service for {self.machine_name}")
            if self.start_plc_monitoring_service():
                _logger.info(f"PLC monitoring service started successfully for {self.machine_name}")
            else:
                _logger.warning(f"Failed to start PLC monitoring service for {self.machine_name}")
        elif self.plc_monitoring_active:
            _logger.info(f"PLC monitoring service already active for {self.machine_name}")
        else:
            _logger.warning(f"Cannot start PLC monitoring - no IP address configured for {self.machine_name}")
        
        try:
            # Get current PLC register values
            registers = service.read_all_plc_registers()
            
            # Get recent measurements
            recent_measurements = self.env['manufacturing.final.station.measurement'].search_read(
                [['machine_id', '=', self.id]],
                ['serial_number', 'capture_date', 'result', 'operation_mode', 'trigger_type'],
                limit=10,
                order='capture_date desc'
            )
            
            # Get station results if we have a serial number
            station_results = None
            if self.last_serial_number:
                station_results = service.get_station_results_for_dashboard(self.last_serial_number)
            
            return {
                'machine_id': self.id,
                'machine_name': self.machine_name,
                'status': self.status,
                'operation_mode': self.operation_mode,
                'plc_online': self.plc_online,
                'plc_ip_address': self.plc_ip_address,
                'plc_port': self.plc_port,
                'last_plc_communication': self.last_plc_communication.isoformat() if self.last_plc_communication else None,
                'camera_ip_address': self.camera_ip_address,
                'camera_port': self.camera_port,
                'camera_triggered': self.camera_triggered,
                'last_capture_time': self.last_capture_time.isoformat() if self.last_capture_time else None,
                'part_present': self.part_present,
                'processing_part': self.processing_part,
                'last_serial_number': self.last_serial_number,
                'last_result': self.last_result,
                'plc_monitoring_active': self.plc_monitoring_active,
                'plc_scan_rate': self.plc_scan_rate,
                'last_plc_scan': self.last_plc_scan.isoformat() if self.last_plc_scan else None,
                'plc_monitoring_errors': self.plc_monitoring_errors,
                'plc_registers': registers,
                'recent_measurements': recent_measurements,
                'station_results': station_results,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            _logger.error(f"Error getting live data: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_station_results_by_serial(self, serial_number):
        """Get station results for a specific serial number"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return {}
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        try:
            return service.get_station_results_for_dashboard(serial_number)
        except Exception as e:
            _logger.error(f"Error getting station results for serial {serial_number}: {str(e)}")
            return {
                'error': str(e),
                'serial_number': serial_number
            }
    
    def update_station_result(self, serial_number, station_type, result):
        """Update a specific station result for a serial number"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return False
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        try:
            return service.update_station_result(serial_number, station_type, result)
        except Exception as e:
            _logger.error(f"Error updating station result for serial {serial_number}: {str(e)}")
            return False
    
    def get_or_create_part_quality(self, serial_number):
        """Get existing part quality record or create new one"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return None
        
        from .final_station_service import FinalStationService
        service = FinalStationService(self)
        
        try:
            return service.get_or_create_part_quality(serial_number)
        except Exception as e:
            _logger.error(f"Error getting or creating part quality for serial {serial_number}: {str(e)}")
            return None
    
    def get_final_station_statistics(self):
        """Get statistics for final station (total parts, passed, rejected, rates)"""
        self.ensure_one()
        if self.machine_type != 'final_station':
            return {
                'error': 'This method is only available for final stations',
                'total_parts': 0,
                'passed_parts': 0,
                'rejected_parts': 0,
                'pass_rate': 0,
                'reject_rate': 0,
                'last_updated': 'Never'
            }
        
        try:
            # Get all final station measurement records for this machine
            measurement_records = self.env['manufacturing.final.station.measurement'].search([
                ('machine_id', '=', self.id)
            ])
            
            total_parts = len(measurement_records)
            passed_parts = len(measurement_records.filtered(lambda r: r.result == 'ok'))
            rejected_parts = len(measurement_records.filtered(lambda r: r.result == 'nok'))
            
            # Calculate rates
            pass_rate = round((passed_parts / total_parts * 100), 1) if total_parts > 0 else 0
            reject_rate = round((rejected_parts / total_parts * 100), 1) if total_parts > 0 else 0
            
            # Get last updated timestamp
            last_updated = 'Never'
            if measurement_records:
                latest_record = measurement_records.sorted('capture_date', reverse=True)[0]
                if latest_record.capture_date:
                    last_updated = latest_record.capture_date.strftime('%Y-%m-%d %H:%M:%S')
            
            _logger.info(f"Final station statistics from measurements - Total: {total_parts}, Passed: {passed_parts}, Rejected: {rejected_parts}")
            
            return {
                'total_parts': total_parts,
                'passed_parts': passed_parts,
                'rejected_parts': rejected_parts,
                'pass_rate': pass_rate,
                'reject_rate': reject_rate,
                'last_updated': last_updated
            }
            
        except Exception as e:
            _logger.error(f"Error getting final station statistics: {str(e)}")
            return {
                'error': str(e),
                'total_parts': 0,
                'passed_parts': 0,
                'rejected_parts': 0,
                'pass_rate': 0,
                'reject_rate': 0,
                'last_updated': 'Never'
            }
