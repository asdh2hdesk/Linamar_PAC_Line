# -*- coding: utf-8 -*-

from odoo import models, fields, api
import os
import csv
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class MachineConfig(models.Model):
    _name = 'manufacturing.machine.config'
    _description = 'Machine Configuration'
    _rec_name = 'machine_name'

    machine_name = fields.Char('Machine Name', required=True)
    machine_type = fields.Selection([
        ('vici_vision', 'VICI Vision System'),
        ('ruhlamat', 'Ruhlamat Press'),
        ('aumann', 'Aumann Measurement'),
    ], string='Machine Type', required=True)

    csv_file_path = fields.Char('CSV File Path', required=True,
                                help='Full path to the CSV file for this machine')
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

    parts_processed_today = fields.Integer('Parts Processed Today', compute='_compute_daily_stats')
    rejection_rate = fields.Float('Rejection Rate %', compute='_compute_daily_stats')

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
                        ('serial_number', '=', ruhlamat_part.serial_number)
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
        """Cron job method to sync all active machines"""
        machines = self.search([('is_active', '=', True)])
        now_dt = fields.Datetime.now()
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
                    machine.sync_machine_data()
                else:
                    _logger.debug(
                        f"Skipping sync for {machine.machine_name}; next in {(machine.sync_interval or 0) - int((now_dt - machine.last_sync).total_seconds())}s"
                    )
            except Exception as e:
                _logger.error(f"Error syncing machine {machine.machine_name}: {str(e)}")

    def sync_machine_data(self):
        """Sync data from CSV file based on machine type"""
        if not os.path.exists(self.csv_file_path):
            _logger.warning(f"CSV file not found: {self.csv_file_path}")
            self.status = 'error'
            return

        try:
            if self.machine_type == 'vici_vision':
                self._sync_vici_data()
            elif self.machine_type == 'ruhlamat':
                self._sync_ruhlamat_data()
            elif self.machine_type == 'aumann':
                self._sync_aumann_data()

            self.last_sync = fields.Datetime.now()
            self.status = 'running'
        except Exception as e:
            _logger.error(f"Error syncing {self.machine_name}: {str(e)}")
            self.status = 'error'

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
                    for fmt in ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                        try:
                            return datetime.strptime(f"{date_str_val} {time_str_val}", fmt)
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

                    try:
                        self.env['manufacturing.vici.vision'].create(vals)
                        created += 1
                    except Exception as e:
                        _logger.error(f"Failed to create VICI record for SN {serial}: {e}")

                _logger.info(f"VICI sync created {created} records for machine {self.machine_name}")
        except Exception as e:
            _logger.error(f"Error syncing VICI data: {str(e)}")
            raise

    def _sync_ruhlamat_data(self):
        """Sync Ruhlamat Press system data"""
        try:
            with open(self.csv_file_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    serial_number = row.get('SerialNumber', '').strip()
                    if not serial_number:
                        continue

                    existing = self.env['manufacturing.ruhlamat.press'].search([
                        ('serial_number', '=', serial_number),
                        ('machine_id', '=', self.id)
                    ])

                    if not existing:
                        press_ok = str(row.get('PressOK', 'False')).lower() == 'true'
                        crack_test = str(row.get('CrackTest', 'False')).lower() == 'true'

                        self.env['manufacturing.ruhlamat.press'].create({
                            'serial_number': serial_number,
                            'machine_id': self.id,
                            'test_date': fields.Datetime.now(),
                            'press_force': float(row.get('PressForce', 0) or 0),
                            'press_distance': float(row.get('PressDistance', 0) or 0),
                            'result': 'pass' if (press_ok and crack_test) else 'reject',
                            'crack_test_result': crack_test,
                            'raw_data': str(row)
                        })
        except Exception as e:
            _logger.error(f"Error syncing Ruhlamat data: {str(e)}")
            raise

    def _sync_aumann_data(self):
        """Sync Aumann Measurement system data"""
        _logger.info(f"Starting Aumann data sync for machine: {self.machine_name} from {self.csv_file_path}")
        try:
            # Check file existence and readability
            if not os.path.exists(self.csv_file_path):
                _logger.error(f"Aumann CSV file not found: {self.csv_file_path}")
                self.status = 'error'
                return
            if not os.access(self.csv_file_path, os.R_OK):
                _logger.error(f"Aumann CSV file not readable: {self.csv_file_path}. Check permissions.")
                self.status = 'error'
                return

            with open(self.csv_file_path, 'r', encoding='utf-8-sig') as file:
                # Skip the first 6 header rows
                for i in range(6):
                    try:
                        next(file)
                    except StopIteration:
                        _logger.warning(f"CSV file has fewer than 6 header rows. Stopped at row {i+1}.")
                        return # Exit if file is too short

                # Read the actual header row after skipping
                header_line = next(file)
                # Determine delimiter by checking if comma or semicolon is present
                delimiter = ',' if ',' in header_line else ';'
                _logger.info(f"Detected delimiter: '{delimiter}' for Aumann CSV.")

                # Rewind file to the beginning of the header line
                file.seek(0)
                for _ in range(6): # Skip again to get to the correct starting point for DictReader
                    next(file)

                reader = csv.DictReader(file, delimiter=delimiter)

                # Log the fieldnames to verify correct header parsing
                _logger.info(f"Aumann CSV Fieldnames: {reader.fieldnames}")

                # Define nominal values and tolerances (hardcoded for now, as they are static in the provided header)
                nominal_values = {
                    'L 64.8': 64.8000, 'L 35.4': 35.4000, 'L 46.6': 46.6000, 'L 82': 82.0000,
                    'L 128.6': 128.6000, 'L 164': 164.0000, 'Runout E31-E22': 0.0000,
                    'Runout E21-E12': 0.0000, 'Runout E11 tube end': 0.0000,
                    'Angular difference E32-E12 pos tool': 240.0000,
                    'Angular difference E31-E12 pos tool': 240.0000,
                    'Angular difference E22-E12 pos tool': 120.0000,
                    'Angular difference E21-E12 pos tool': 120.0000,
                    'Angular difference E11-E12 pos tool': 0.0000
                }
                lower_tolerances = {
                    'L 64.8': -0.5000, 'L 35.4': -0.2500, 'L 46.6': -0.2500, 'L 82': -0.2500,
                    'L 128.6': -0.2500, 'L 164': -0.2500, 'Runout E31-E22': -0.0000,
                    'Runout E21-E12': -0.0000, 'Runout E11 tube end': -0.0000,
                    'Angular difference E32-E12 pos tool': -2.0000,
                    'Angular difference E31-E12 pos tool': -2.0000,
                    'Angular difference E22-E12 pos tool': -2.0000,
                    'Angular difference E21-E12 pos tool': -2.0000,
                    'Angular difference E11-E12 pos tool': -2.0000
                }
                upper_tolerances = {
                    'L 64.8': 0.5000, 'L 35.4': 0.2500, 'L 46.6': 0.2500, 'L 82': 0.2500,
                    'L 128.6': 0.2500, 'L 164': 0.2500, 'Runout E31-E22': 0.1500,
                    'Runout E21-E12': 0.1500, 'Runout E11 tube end': 0.1500,
                    'Angular difference E32-E12 pos tool': 2.0000,
                    'Angular difference E31-E12 pos tool': 2.0000,
                    'Angular difference E22-E12 pos tool': 2.0000,
                    'Angular difference E21-E12 pos tool': 2.0000,
                    'Angular difference E11-E12 pos tool': 2.0000
                }
                measurement_keys = list(nominal_values.keys()) # Use keys from nominal_values for consistency

                records_created = 0
                for row_idx, row in enumerate(reader):
                    _logger.debug(f"Processing Aumann row {row_idx + 1}: {row}")

                    serial_number = row.get('Serial Number', '').strip()
                    if not serial_number:
                        _logger.warning(f"Skipping Aumann row {row_idx + 1} due to missing 'Serial Number'. Row data: {row}")
                        continue

                    # Check if record already exists to prevent duplicates
                    existing = self.env['manufacturing.aumann.measurement'].search([
                        ('serial_number', '=', serial_number),
                        ('machine_id', '=', self.id)
                    ], limit=1)

                    if existing:
                        _logger.info(f"Aumann record for Serial Number {serial_number} already exists. Skipping creation.")
                        continue

                    measurements = {}
                    measurements_passed = 0
                    total_measurements = 0
                    all_measurements_valid = True

                    for key in measurement_keys:
                        value = row.get(key)
                        if value is not None and str(value).strip():
                            try:
                                # Replace comma with dot for float conversion
                                float_value = float(str(value).replace(',', '.'))
                                measurements[key] = float_value
                                total_measurements += 1

                                # Perform tolerance check
                                nominal = nominal_values.get(key)
                                lower_tol = lower_tolerances.get(key)
                                upper_tol = upper_tolerances.get(key)

                                if nominal is None or lower_tol is None or upper_tol is None:
                                    _logger.warning(f"Missing nominal/tolerance for key '{key}'. Skipping tolerance check for this measurement.")
                                    # If nominal/tolerance is missing, we can't check, so assume it passes for this specific measurement
                                    measurements_passed += 1
                                    continue

                                # For 'L' dimensions, check if value is within nominal +/- tolerance
                                if 'L ' in key: # Check for 'L ' to distinguish from 'Angular difference E11-E12 pos tool'
                                    if (nominal + lower_tol) <= float_value <= (nominal + upper_tol):
                                        measurements_passed += 1
                                    else:
                                        all_measurements_valid = False
                                        _logger.debug(f"Measurement {key} ({float_value}) failed tolerance. Nominal: {nominal}, Lower: {nominal + lower_tol}, Upper: {nominal + upper_tol}")
                                # For Runout and Angular differences, nominal is 0, and tolerance defines the acceptable range from 0.
                                # The lower_tolerance for these is typically 0 or negative, and upper_tolerance is positive.
                                elif 'Runout' in key or 'Angular difference' in key:
                                    if lower_tol <= float_value <= upper_tol:
                                        measurements_passed += 1
                                    else:
                                        all_measurements_valid = False
                                        _logger.debug(f"Measurement {key} ({float_value}) failed tolerance. Lower: {lower_tol}, Upper: {upper_tol}")
                                else:
                                    _logger.warning(f"Unknown measurement key type: {key}. Skipping tolerance check.")
                                    measurements_passed += 1 # Assume pass if type is unknown

                            except (ValueError, TypeError) as e:
                                _logger.warning(f"Could not convert value '{value}' for key '{key}' to float for serial number {serial_number}: {e}. This measurement will not be counted as passed.")
                                all_measurements_valid = False # Mark as invalid if conversion fails
                                pass
                        else:
                            _logger.debug(f"Measurement key '{key}' has no value or is empty for serial number {serial_number}.")


                    # Determine overall result
                    result = 'pass' if all_measurements_valid and total_measurements > 0 else 'reject'
                    if total_measurements == 0:
                        result = 'reject' # If no valid measurements, it's a reject

                    # Extract test_date from 'Date' and 'Hour' columns
                    date_str = row.get('Date')
                    time_str = row.get('Hour')
                    test_datetime = fields.Datetime.now() # Default to now if parsing fails
                    if date_str and time_str:
                        try:
                            # Assuming date format is DD-MM-YYYY and time is HH:MM:SS
                            test_datetime = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M:%S")
                        except ValueError:
                            _logger.warning(f"Could not parse date/time '{date_str} {time_str}' for serial number {serial_number}. Using current time.")

                    # Prepare data for creation
                    create_vals = {
                        'serial_number': serial_number,
                        'machine_id': self.id,
                        'test_date': test_datetime,
                        'part_form': 'Exhaust CAMSHAFT', # Placeholder, adjust as needed
                        'product_id': 'Q50-11502-0056810', # Placeholder, adjust as needed
                        'assembly': 'MSA', # Placeholder, adjust as needed
                        'total_measurements': total_measurements,
                        'measurements_passed': measurements_passed,
                        'result': result,
                        'raw_data': str(row)[:2000]  # Limit raw data size
                    }

                    # Dynamically add measurement values to create_vals
                    # Ensure your Odoo model 'manufacturing.aumann.measurement' has these fields
                    # e.g., diameter_journal_a1 = fields.Float('Diameter Journal A1')
                    field_mapping = {
                        'L 64.8': 'diameter_journal_a1',
                        'L 35.4': 'diameter_journal_a2',
                        'L 46.6': 'diameter_journal_a3',
                        'L 82': 'diameter_journal_b1',
                        'L 128.6': 'diameter_journal_b2',
                        'L 164': 'diameter_journal_b3', # Assuming this maps to b3
                        'Runout E31-E22': 'runout_e31_e22',
                        'Runout E21-E12': 'runout_e21_e12',
                        'Runout E11 tube end': 'runout_e11_tube_end',
                        'Angular difference E32-E12 pos tool': 'angular_diff_e32_e12',
                        'Angular difference E31-E12 pos tool': 'angular_diff_e31_e12',
                        'Angular difference E22-E12 pos tool': 'angular_diff_e22_e12',
                        'Angular difference E21-E12 pos tool': 'angular_diff_e21_e12',
                        'Angular difference E11-E12 pos tool': 'angular_diff_e11_e12',
                    }

                    for csv_key, odoo_field in field_mapping.items():
                        if csv_key in measurements:
                            create_vals[odoo_field] = measurements[csv_key]
                        else:
                            # Set to 0.0 or None if measurement not found in CSV row
                            create_vals[odoo_field] = 0.0 # Or None, depending on field definition

                    try:
                        self.env['manufacturing.aumann.measurement'].create(create_vals)
                        records_created += 1
                        _logger.info(f"Successfully created Aumann record for Serial Number: {serial_number} with result: {result}")
                    except Exception as e:
                        _logger.error(f"Failed to create Aumann record for Serial Number {serial_number}: {e}. Data: {create_vals}")
                        # Continue to next record even if one fails

            _logger.info(f"Aumann data sync completed. Total records created: {records_created}")

        except FileNotFoundError:
            _logger.error(f"Aumann CSV file not found at {self.csv_file_path}. Please check the path.")
            self.status = 'error'
        except Exception as e:
            _logger.error(f"An unexpected error occurred during Aumann data sync: {e}", exc_info=True)
            self.status = 'error'

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
                'type': machine.machine_type,
                'status': machine.status,
                'parts_today': machine.parts_processed_today,
                'rejection_rate': round(machine.rejection_rate, 2),
                'last_sync': machine.last_sync.isoformat() if machine.last_sync else None,
            }
            dashboard_data['machines'].append(machine_data)

        return dashboard_data
