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
                    # ('test_date', '>=', today)
                ])
                for ruhlamat_part in ruhlamat_parts:
                    part_quality = self.env['manufacturing.part.quality'].search([
                        ('serial_number', '=', ruhlamat_part.part_id1)
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

        try:
            # Check if file exists
            if not os.path.exists(
                    self.csv_file_path):  # Note: You should rename this field to 'file_path' since it's not CSV anymore
                _logger.error(f"MDB file not found: {self.csv_file_path}")
                self.status = 'error'
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
                conn = pyodbc.connect(conn_str)
                cursor = conn.cursor()

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

                created_cycles = 0
                created_gaugings = 0

                for cycle_row in cycles:
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

                        for gauging_row in gaugings:
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

                _logger.info(
                    f"Ruhlamat MDB sync completed. Created {created_cycles} cycles and {created_gaugings} gaugings.")
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

            # Read tables into pandas DataFrames
            cycles_df = pd.read_sql("SELECT * FROM Cycles", conn)
            gaugings_df = pd.read_sql("SELECT * FROM Gaugings", conn)

            created_cycles = 0
            created_gaugings = 0

            # Process cycles
            for _, cycle_row in cycles_df.iterrows():
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

            _logger.info(
                f"Ruhlamat MDB sync (alternative method) completed. Created {created_cycles} cycles and {created_gaugings} gaugings.")
            self.last_sync = fields.Datetime.now()
            self.status = 'running'

        except Exception as e:
            _logger.error(f"Alternative MDB sync method failed: {str(e)}")
            self.status = 'error'
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

    # Add these enhanced methods to your machine_config.py file

    @api.model
    def get_enhanced_dashboard_data(self):
        """Enhanced dashboard data with analytics support"""
        machines = self.search([('is_active', '=', True)])
        today = fields.Date.today()

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

        total_parts_today = 0
        total_passed = 0
        total_rejected = 0

        for machine in machines:
            # Get today's data for this machine
            machine_stats = self._get_machine_today_stats(machine.id)

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
            total_parts_today += machine_stats['total_count']
            total_passed += machine_stats['ok_count']
            total_rejected += machine_stats['reject_count']

        dashboard_data['statistics'] = {
            'total_parts': total_parts_today,
            'passed_parts': total_passed,
            'rejected_parts': total_rejected,
            'pending_parts': 0,  # Calculate if you have pending logic
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

        # Calculate rejection rate
        if stats['total_count'] > 0:
            stats['rejection_rate'] = round((stats['reject_count'] / stats['total_count']) * 100, 2)

        return stats

    @api.model
    def get_machine_detail_data(self, machine_id, filter_type='today', page=1, records_per_page=20):
        """Enhanced machine detail data with analytics"""
        try:
            machine = self.browse(machine_id)
            if not machine.exists():
                return {'error': 'Machine not found'}

            # Validate parameters
            page = max(1, int(page)) if page else 1
            records_per_page = max(1, min(100, int(records_per_page))) if records_per_page else 20
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
                'records': [],
                'analytics': {
                    'hourly_production': self._get_hourly_production(machine_id, today),
                    'measurement_trends': self._get_measurement_trends(machine_id, today),
                    'quality_metrics': self._get_quality_metrics(machine_id, today)
                }
            }

            # Get detailed records with pagination
            offset = (page - 1) * records_per_page
            
            if machine.machine_type == 'vici_vision':
                # Get total count for pagination
                total_records = self.env['manufacturing.vici.vision'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', start_date),
                    ('test_date', '<=', end_date)
                ])
                
                records = self.env['manufacturing.vici.vision'].search([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', start_date),
                    ('test_date', '<=', end_date)
                ], order='test_date desc', limit=records_per_page, offset=offset)

                for record in records:
                    machine_data['records'].append({
                        'serial_number': record.serial_number,
                        'machine_name': record.machine_id.machine_name if record.machine_id else 'N/A',
                        'test_date': record.test_date.strftime('%Y-%m-%d %H:%M:%S'),
                        'log_date': record.log_date.strftime('%Y-%m-%d') if record.log_date else '',
                        'log_time': record.log_time.strftime('%H:%M:%S') if record.log_time else '',
                        'operator': record.operator_name or 'Auto',
                        'measure_number': record.measure_number or 'N/A',
                        'within_tolerance': record.within_tolerance,
                        'result': record.result,
                        'failed_fields': record.failed_fields or '',
                        'rejection_reason': record.rejection_reason or '',
                        'measurements': {
                            'L 64.8': record.l_64_8,
                            'L 35.4': record.l_35_4,
                            'L 46.6': record.l_46_6,
                            'L 82': record.l_82,
                            'L 128.6': record.l_128_6,
                            'L 164': record.l_164,
                        }
                    })

            elif machine.machine_type == 'ruhlamat':
                # Get total count for pagination
                total_records = self.env['manufacturing.ruhlamat.press'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', start_date),
                    ('test_date', '<=', end_date)
                ])
                
                records = self.env['manufacturing.ruhlamat.press'].search([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', start_date),
                    ('test_date', '<=', end_date)
                ], order='test_date desc', limit=records_per_page, offset=offset)

                for record in records:
                    machine_data['records'].append({
                        'serial_number': record.serial_number,
                        'test_date': record.test_date.strftime('%Y-%m-%d %H:%M:%S'),
                        'operator': 'Auto',
                        'result': record.result,
                        'rejection_reason': getattr(record, 'rejection_reason', '') or '',
                        'measurements': {
                            'Press Force': record.press_force,
                            'Press Distance': record.press_distance,
                            'Crack Test': 'Pass' if record.crack_test_result else 'Fail',
                        }
                    })

            elif machine.machine_type == 'aumann':
                # Get total count for pagination
                total_records = self.env['manufacturing.aumann.measurement'].search_count([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', start_date),
                    ('test_date', '<=', end_date)
                ])
                
                records = self.env['manufacturing.aumann.measurement'].search([
                    ('machine_id', '=', machine_id),
                    ('test_date', '>=', start_date),
                    ('test_date', '<=', end_date)
                ], order='test_date desc', limit=records_per_page, offset=offset)

                for record in records:
                    machine_data['records'].append({
                        'serial_number': record.serial_number,
                        'test_date': record.test_date.strftime('%Y-%m-%d %H:%M:%S'),
                        'operator': 'Auto',
                        'result': record.result,
                        'rejection_reason': '',
                        'measurements': {
                            'Diameter A1': getattr(record, 'diameter_journal_a1', 0) or 0,
                            'Diameter A2': getattr(record, 'diameter_journal_a2', 0) or 0,
                            'Diameter B1': getattr(record, 'diameter_journal_b1', 0) or 0,
                            'Diameter B2': getattr(record, 'diameter_journal_b2', 0) or 0,
                            'Runout E31-E22': getattr(record, 'runout_e31_e22', 0) or 0,
                        }
                    })
            else:
                # No matching machine type
                total_records = 0

            # Add pagination information
            total_pages = (total_records + records_per_page - 1) // records_per_page if total_records > 0 else 1
            
            machine_data['pagination'] = {
                'current_page': page,
                'total_pages': total_pages,
                'total_records': total_records,
                'records_per_page': records_per_page,
                'has_next': page < total_pages,
                'has_previous': page > 1
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
            else:
                count = 0

            hourly_data.append({
                'hour': f"{hour:02d}:00",
                'count': count
            })

        return hourly_data

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
