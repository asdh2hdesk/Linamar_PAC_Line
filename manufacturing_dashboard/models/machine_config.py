# -*- coding: utf-8 -*-

from odoo import models, fields, api
import os
import csv
import logging
import pyodbc  # or pypyodbc
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
        ('gauging', 'Gauging System'),
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

    # Progress tracking fields
    sync_progress = fields.Float('Sync Progress %', default=0.0, help='Current sync progress percentage')
    sync_stage = fields.Char('Current Sync Stage', help='Current stage of sync process')
    sync_total_records = fields.Integer('Total Records to Process', default=0)
    sync_processed_records = fields.Integer('Processed Records', default=0)
    sync_start_time = fields.Datetime('Sync Start Time')
    sync_estimated_completion = fields.Datetime('Estimated Completion Time')

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
            elif self.machine_type == 'gauging':
                self._sync_gauging_data()
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
        """Sync Aumann Measurement system data from folder of CSV files (one per serial number)"""
        _logger.info(f"Starting Aumann data sync for machine: {self.machine_name} from folder: {self.csv_file_path}")
        
        # Initialize progress tracking
        self.sync_start_time = fields.Datetime.now()
        self.sync_progress = 0.0
        self.sync_stage = "Initializing Aumann sync process"
        self.sync_processed_records = 0
        self.sync_total_records = 0
        self.env.cr.commit()
        
        try:
            # Check if the path is a directory (folder-based approach)
            if not os.path.exists(self.csv_file_path):
                _logger.error(f"Aumann CSV folder not found: {self.csv_file_path}")
                self.status = 'error'
                self.sync_stage = "Error: Folder not found"
                return
            
            if not os.path.isdir(self.csv_file_path):
                _logger.error(f"Aumann path is not a directory: {self.csv_file_path}")
                self.status = 'error'
                self.sync_stage = "Error: Path is not a directory"
                return

            # Update progress: Scanning folder
            self.sync_stage = "Scanning folder for CSV files"
            self.sync_progress = 10.0
            self.env.cr.commit()
            _logger.info("Scanning folder for CSV files...")

            # Get all CSV files in the directory
            csv_files = [f for f in os.listdir(self.csv_file_path) if f.lower().endswith('.csv')]
            total_files = len(csv_files)
            self.sync_total_records = total_files
            self.sync_stage = f"Found {total_files} CSV files to process"
            self.sync_progress = 15.0
            self.env.cr.commit()
            _logger.info(f"Found {total_files} CSV files in Aumann folder")
            
            records_created = 0
            
            for file_index, csv_file in enumerate(csv_files):
                # Update progress for file processing
                file_progress = 15.0 + (file_index / total_files) * 80.0  # 15-95% for files
                self.sync_progress = file_progress
                self.sync_processed_records = file_index + 1
                self.sync_stage = f"Processing file {file_index + 1} of {total_files}: {csv_file}"
                
                # Commit progress every 10 files or at the end
                if file_index % 10 == 0 or file_index == total_files - 1:
                    self.env.cr.commit()
                    _logger.info(f"Progress: {file_progress:.1f}% - Processing file {file_index + 1}/{total_files}")
                
                csv_path = os.path.join(self.csv_file_path, csv_file)
                try:
                    file_records = self._process_aumann_csv_file(csv_path)
                    records_created += file_records
                    
                    if file_records > 0:
                        _logger.debug(f"Created {file_records} records from {csv_file}")
                        
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
                    test_date = self._parse_aumann_timestamp(row.get('Timestamp', ''))
                    _logger.debug(f"Parsed test date: {test_date} for {serial_number}")

                    # Create measurement record with all fields
                    create_vals = {
                        'serial_number': serial_number,
                        'machine_id': self.id,
                        'test_date': test_date,
                        'part_type': row.get('Type', ''),
                        'raw_data': str(row)[:2000],  # Limit raw data size
                    }

                    # Map all measurement fields from CSV to model fields
                    field_mapping = self._get_aumann_field_mapping()
                    mapped_fields = 0
                    for csv_field, model_field in field_mapping.items():
                        if csv_field in row and row[csv_field]:
                            try:
                                create_vals[model_field] = float(row[csv_field])
                                mapped_fields += 1
                            except (ValueError, TypeError):
                                _logger.warning(f"Could not parse {csv_field} value: {row[csv_field]} in {filename}")

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

    def _parse_aumann_timestamp(self, timestamp_str):
        """Parse Aumann timestamp string"""
        if not timestamp_str:
            return fields.Datetime.now()
        
        try:
            # Try different timestamp formats
            timestamp_formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f',
                '%d/%m/%Y %H:%M:%S',
                '%m/%d/%Y %H:%M:%S',
            ]
            
            for fmt in timestamp_formats:
                try:
                    return datetime.strptime(timestamp_str.strip(), fmt)
                except ValueError:
                    continue
            
            # If all formats failed, use current time
            _logger.warning(f"Could not parse timestamp '{timestamp_str}', using current time")
            return fields.Datetime.now()
            
        except Exception as e:
            _logger.warning(f"Error parsing timestamp '{timestamp_str}': {e}")
            return fields.Datetime.now()

    def _get_aumann_field_mapping(self):
        """Get mapping from CSV field names to model field names"""
        return {
            # Wheel Angle Measurements
            'Wheel Angle Left 120 - CTF 41.3': 'wheel_angle_left_120',
            'Wheel Angle Left 150 - CTF 41.2': 'wheel_angle_left_150',
            'Wheel Angle Left 180 - CTF 41.1': 'wheel_angle_left_180',
            'Wheel Angle Right 120 - CTF 41.5': 'wheel_angle_right_120',
            'Wheel Angle Right 150 - CTF 41.4': 'wheel_angle_right_150',
            'Wheel Angle to Reference - CTF 42': 'wheel_angle_to_reference',
            
            # Angle Lobe Measurements
            'Angle Lobe E11 to Ref. - CTF 29': 'angle_lobe_e11_to_ref',
            'Angle Lobe E12 to Ref. - CTF 29': 'angle_lobe_e12_to_ref',
            'Angle Lobe E21 to Ref. - CTF 29': 'angle_lobe_e21_to_ref',
            'Angle Lobe E22 to Ref. - CTF 29': 'angle_lobe_e22_to_ref',
            'Angle Lobe E31 to Ref. - CTF 29': 'angle_lobe_e31_to_ref',
            'Angle Lobe E32 to Ref. - CTF 29': 'angle_lobe_e32_to_ref',
            
            # Base Circle Radius Measurements
            'Base Circle Radius Lobe E11 - CTF 54': 'base_circle_radius_lobe_e11',
            'Base Circle Radius Lobe E12 - CTF 54': 'base_circle_radius_lobe_e12',
            'Base Circle Radius Lobe E21 - CTF 54': 'base_circle_radius_lobe_e21',
            'Base Circle Radius Lobe E22 - CTF 54': 'base_circle_radius_lobe_e22',
            'Base Circle Radius Lobe E31 - CTF 54': 'base_circle_radius_lobe_e31',
            'Base Circle Radius Lobe E32 - CTF 54': 'base_circle_radius_lobe_e32',
            
            # Base Circle Runout Measurements
            'Base Circle Runout Lobe E11 adj. - CTF 15': 'base_circle_runout_lobe_e11_adj',
            'Base Circle Runout Lobe E12 adj. - CTF 15': 'base_circle_runout_lobe_e12_adj',
            'Base Circle Runout Lobe E21 adj. - CTF 15': 'base_circle_runout_lobe_e21_adj',
            'Base Circle Runout Lobe E22 adj. - CTF 15': 'base_circle_runout_lobe_e22_adj',
            'Base Circle Runout Lobe E31 adj. - CTF 15': 'base_circle_runout_lobe_e31_adj',
            'Base Circle Runout Lobe E32 adj. - CTF 15': 'base_circle_runout_lobe_e32_adj',
            
            # Bearing and Width Measurements
            'Bearing Width - CTF 55': 'bearing_width',
            'Cam Angle12': 'cam_angle12',
            'Cam Angle34': 'cam_angle34',
            'Cam Angle56 ': 'cam_angle56',
            
            # Concentricity Measurements
            'Concentricity Front Bearing H - CTF 63': 'concentricity_front_bearing_h',
            'Concentricity IO -M- Front End Dia 39 - CTF 59': 'concentricity_io_front_end_dia_39',
            'Concentricity IO -M- Front end major Dia 40 - CTF 61': 'concentricity_io_front_end_major_dia_40',
            'Concentricity IO -M- Step Diameter 32.5 - CTF 25': 'concentricity_io_step_diameter_32_5',
            
            # Concentricity Results
            'Concentricity result Front End Dia 39 - CTF 59': 'concentricity_result_front_end_dia_39',
            'Concentricity result Front end major Dia 40 - CTF 61': 'concentricity_result_front_end_major_dia_40',
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
            
            # Distance Measurements
            'Distance Lobe E11 - CTF 52.1': 'distance_lobe_e11',
            'Distance Lobe E12 - CTF 52.2': 'distance_lobe_e12',
            'Distance Lobe E21 - CTF 52.3': 'distance_lobe_e21',
            'Distance Lobe E22 - CTF 52.4': 'distance_lobe_e22',
            'Distance Lobe E31 - CTF 52.5': 'distance_lobe_e31',
            'Distance Lobe E32 - CTF 52.6': 'distance_lobe_e32',
            'Distance Rear End - CTF 214': 'distance_rear_end',
            'Distance Step length front face - CTF 66': 'distance_step_length_front_face',
            'Distance Trigger Length - CTF 213': 'distance_trigger_length',
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
            
            # Trigger Wheel Measurements
            'Trigger wheel diameter - CTF 248': 'trigger_wheel_diameter',
            'Trigger wheel width - CTF 218': 'trigger_wheel_width',
            
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
        }

    def _determine_aumann_result(self, create_vals):
        """Determine pass/reject result based on Aumann measurements"""
        # Define critical measurement tolerances
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
        """Sync Gauging system data from Excel file"""
        _logger.info(f"Starting Gauging data sync for machine: {self.machine_name} from {self.csv_file_path}")
        
        try:
            # Check file existence and readability
            if not os.path.exists(self.csv_file_path):
                _logger.error(f"Gauging Excel file not found: {self.csv_file_path}")
                self.status = 'error'
                return
            if not os.access(self.csv_file_path, os.R_OK):
                _logger.error(f"Gauging Excel file not readable: {self.csv_file_path}. Check permissions.")
                self.status = 'error'
                return

            # Try to import required libraries
            try:
                import pandas as pd
                from datetime import datetime
            except ImportError:
                _logger.error("pandas is required for Excel file processing. Please install it: pip install pandas openpyxl")
                self.status = 'error'
                return

            # Read Excel file without header to preserve all rows
            try:
                df = pd.read_excel(self.csv_file_path, engine='openpyxl', header=None)
                _logger.info(f"Gauging Excel file loaded successfully. Shape: {df.shape}")
            except Exception as e:
                _logger.error(f"Failed to read Excel file: {str(e)}")
                self.status = 'error'
                return

            if df.empty:
                _logger.warning("Gauging Excel file is empty")
                return

            records_created = 0
            
            # Find the header row that contains "Sr No."
            header_row_index = None
            column_mapping = {}  # Map column indices to names
            
            for i in range(len(df)):
                row = df.iloc[i]
                # Check if this row contains "Sr No." in any column
                if any('Sr No' in str(val) for val in row.values if pd.notna(val)):
                    header_row_index = i
                    _logger.info(f"Found header row at index {i}")
                    
                    # Create column mapping from this header row
                    for col_idx, col_name in enumerate(row.values):
                        if pd.notna(col_name):
                            column_mapping[col_idx] = str(col_name).strip()
                    
                    _logger.info(f"Column mapping: {column_mapping}")
                    break
            
            if header_row_index is None:
                _logger.error("Could not find header row containing 'Sr No.' in the Excel file")
                return
            
            # Check if we have enough rows after header for tolerance data and actual data
            if len(df) < header_row_index + 6:  # header + 4 tolerance rows + at least 1 data row
                _logger.warning(f"Gauging Excel file has insufficient rows after header row {header_row_index}")
                return

            # Get the rows based on header position
            header_row = df.iloc[header_row_index]
            utl_row = df.iloc[header_row_index + 1]  # Upper Tolerance Limit
            ucl_row = df.iloc[header_row_index + 2]  # Upper Control Limit  
            lcl_row = df.iloc[header_row_index + 3]  # Lower Control Limit
            ltl_row = df.iloc[header_row_index + 4]  # Lower Tolerance Limit
            
            # Log the structure for debugging
            _logger.info(f"Header row (index {header_row_index}): {header_row.values}")
            
            # Build tolerance dictionaries by column index and name
            tolerance_data = {}
            for col_idx, col_name in column_mapping.items():
                if col_name not in ['Sr No.', 'Job Number', 'Date/Time', 'Machine', 'Status']:
                    # For angle measurements, convert from degrees/minutes/seconds to decimal
                    utl_val = utl_row.iloc[col_idx] if col_idx < len(utl_row) else None
                    ucl_val = ucl_row.iloc[col_idx] if col_idx < len(ucl_row) else None
                    lcl_val = lcl_row.iloc[col_idx] if col_idx < len(lcl_row) else None
                    ltl_val = ltl_row.iloc[col_idx] if col_idx < len(ltl_row) else None
                    
                    # Convert angle values to decimal degrees if they are in DMS format
                    if 'ANGIE' in col_name.upper():
                        utl_val = self._parse_angle_to_decimal(utl_val) if pd.notna(utl_val) else None
                        ucl_val = self._parse_angle_to_decimal(ucl_val) if pd.notna(ucl_val) else None
                        lcl_val = self._parse_angle_to_decimal(lcl_val) if pd.notna(lcl_val) else None
                        ltl_val = self._parse_angle_to_decimal(ltl_val) if pd.notna(ltl_val) else None
                    else:
                        utl_val = self._safe_float(utl_val)
                        ucl_val = self._safe_float(ucl_val)
                        lcl_val = self._safe_float(lcl_val)
                        ltl_val = self._safe_float(ltl_val)
                    
                    tolerance_data[col_name] = {
                        'utl': utl_val,
                        'ucl': ucl_val,
                        'lcl': lcl_val,
                        'ltl': ltl_val
                    }
            
            # Log parsed tolerance data
            _logger.info(f"Parsed tolerance data: {tolerance_data}")
            
            # Process actual data rows (starting 5 rows after header)
            data_start_index = header_row_index + 5
            for index in range(data_start_index, len(df)):
                try:
                    row = df.iloc[index]
                    
                    # Helper function to get value by column name
                    def get_value_by_column_name(column_name, default=''):
                        for col_idx, col_name in column_mapping.items():
                            if column_name.lower() in col_name.lower() or col_name.lower() in column_name.lower():
                                return row.iloc[col_idx] if col_idx < len(row) else default
                        return default
                    
                    # Extract data based on the Excel structure using column mapping
                    sr_no = str(get_value_by_column_name('Sr No')).strip()
                    job_number = str(get_value_by_column_name('Job Number')).strip()
                    date_time = get_value_by_column_name('Date/Time')
                    machine_code = str(get_value_by_column_name('Machine')).strip()
                    angle_measurement = str(get_value_by_column_name('1-ANGIE')).strip()
                    status = str(get_value_by_column_name('Status', 'ACCEPT')).strip().upper()
                    
                    # Skip empty rows
                    if not job_number or job_number == 'nan':
                        continue
                    
                    serial_number = job_number
                    
                    # Check if record already exists to prevent duplicates
                    existing = self.env['manufacturing.gauging.measurement'].search([
                        ('serial_number', '=', serial_number),
                        ('machine_id', '=', self.id)
                    ], limit=1)
                    
                    if existing:
                        _logger.debug(f"Gauging record for Serial Number {serial_number} already exists. Skipping.")
                        continue
                    
                    # Parse test date
                    test_date = fields.Datetime.now()
                    if pd.notna(date_time):
                        try:
                            if isinstance(date_time, str):
                                # Try different date formats for US format with AM/PM
                                date_formats = [
                                    '%m/%d/%Y %I:%M:%S %p',  # US format with AM/PM
                                    '%d/%m/%Y %H:%M:%S',     # European format 24h
                                    '%Y-%m-%d %H:%M:%S',     # ISO format
                                    '%m/%d/%Y %H:%M:%S',     # US format 24h
                                ]
                                
                                for fmt in date_formats:
                                    try:
                                        test_date = datetime.strptime(date_time.strip(), fmt)
                                        break
                                    except ValueError:
                                        continue
                                else:
                                    # If all formats failed, log and use current time
                                    _logger.warning(f"Could not parse date '{date_time}' with any known format. Using current time.")
                            else:
                                test_date = pd.to_datetime(date_time)
                        except Exception as e:
                            _logger.warning(f"Could not parse date '{date_time}': {e}. Using current time.")
                    
                    # Map status
                    if status in ['ACCEPT', 'ACCEPTED']:
                        status_mapped = 'accept'
                    elif status in ['REJECT', 'REJECTED']:
                        status_mapped = 'reject'
                    else:
                        status_mapped = 'accept'  # Default
                    
                    # Check tolerance for angle measurement
                    angle_within_tolerance = True
                    rejection_reason = None
                    
                    if angle_measurement and angle_measurement != 'nan':
                        # Get tolerance data for 1-ANGIE column
                        angie_tolerance = tolerance_data.get('1-ANGIE', {})
                        if angie_tolerance:
                            # Parse angle to decimal degrees for tolerance checking
                            try:
                                decimal_degrees = self._parse_angle_to_decimal(angle_measurement)
                                utl = angie_tolerance.get('utl')
                                ltl = angie_tolerance.get('ltl')
                                
                                if utl is not None and ltl is not None:
                                    if not (ltl <= decimal_degrees <= utl):
                                        angle_within_tolerance = False
                                        status_mapped = 'reject'  # Override status if out of tolerance
                                        rejection_reason = f"Angle {decimal_degrees:.4f}° out of tolerance ({ltl:.4f}° - {utl:.4f}°)"
                            except Exception as e:
                                _logger.warning(f"Failed to check tolerance for angle '{angle_measurement}': {e}")
                    
                    # Prepare data for creation
                    create_vals = {
                        # 'sr_no': sr_no,
                        'machine_id': self.id,
                        'test_date': test_date,
                        'job_number': job_number if job_number != 'nan' else '',
                        'serial_number': job_number if job_number != 'nan' else '',
                        'machine_code': machine_code if machine_code != 'nan' else '',
                        'angle_measurement': angle_measurement if angle_measurement != 'nan' else '',
                        'status': status_mapped,
                        'within_tolerance': angle_within_tolerance,
                        'raw_data': str(row.to_dict())[:2000]  # Limit raw data size
                    }
                    
                    if rejection_reason:
                        create_vals['rejection_reason'] = rejection_reason
                    
                    # Add tolerance data if available
                    angie_tolerance = tolerance_data.get('1-ANGIE', {})
                    if angie_tolerance:
                        create_vals.update({
                            'upper_tolerance': angie_tolerance.get('utl'),
                            'lower_tolerance': angie_tolerance.get('ltl'),
                            'nominal_value': angie_tolerance.get('ucl')  # Using UCL as nominal
                        })
                    
                    # Create the record
                    new_record = self.env['manufacturing.gauging.measurement'].create(create_vals)
                    records_created += 1
                    _logger.debug(f"Successfully created Gauging record for Serial Number: {serial_number}")
                    
                except Exception as e:
                    _logger.error(f"Failed to process Gauging row {index}: {e}")
                    continue
            
            _logger.info(f"Gauging data sync completed. Total records created: {records_created}")
            
        except FileNotFoundError:
            _logger.error(f"Gauging Excel file not found at {self.csv_file_path}. Please check the path.")
            self.status = 'error'
        except Exception as e:
            _logger.error(f"An unexpected error occurred during Gauging data sync: {e}", exc_info=True)
            self.status = 'error'

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
                'type': machine.machine_type,
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
                'type': machine.machine_type,
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
                    'type': machine.machine_type,
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
