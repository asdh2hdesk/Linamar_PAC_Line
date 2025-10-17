# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.modules.module import get_module_resource
from datetime import datetime
import csv
import pytz


class ViciVision(models.Model):
    _name = 'manufacturing.vici.vision'
    _description = 'VICI Vision System Data'
    _order = 'log_date desc, log_time desc'
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
    log_date = fields.Date('Date', index=True)
    log_time = fields.Char('Hour')

    # Metadata from CSV
    operator_name = fields.Char('Operator')
    batch_serial_number = fields.Char('Batch Serial Number')
    measure_number = fields.Integer('Measure Number')
    measure_state = fields.Integer('Measure State')

    # Measurements
    l_64_8 = fields.Float('L 64.8', digits=(10, 4))
    l_35_4 = fields.Float('L 35.4', digits=(10, 4))
    l_46_6 = fields.Float('L 46.6', digits=(10, 4))
    l_82 = fields.Float('L 82', digits=(10, 4))
    l_128_6 = fields.Float('L 128.6', digits=(10, 4))
    l_164 = fields.Float('L 164', digits=(10, 4))
    runout_e31_e22 = fields.Float('Runout E31-E22', digits=(10, 4))
    runout_e21_e12 = fields.Float('Runout E21-E12', digits=(10, 4))
    runout_e11_tube_end = fields.Float('Runout E11 tube end', digits=(10, 4))
    ang_diff_e32_e12_pos_tool = fields.Float('Angular difference E32-E12 pos tool', digits=(10, 4))
    ang_diff_e31_e12_pos_tool = fields.Float('Angular difference E31-E12 pos tool', digits=(10, 4))
    ang_diff_e22_e12_pos_tool = fields.Float('Angular difference E22-E12 pos tool', digits=(10, 4))
    ang_diff_e21_e12_pos_tool = fields.Float('Angular difference E21-E12 pos tool', digits=(10, 4))
    ang_diff_e11_e12_pos_tool = fields.Float('Angular difference E11-E12 pos tool', digits=(10, 4))

    # Nominal and Tolerances (per measurement)
    l_64_8_nominal = fields.Float('L 64.8 Nominal', digits=(10, 4))
    l_64_8_tol_low = fields.Float('L 64.8 Lower Tol', digits=(10, 4))
    l_64_8_tol_high = fields.Float('L 64.8 Upper Tol', digits=(10, 4))

    l_35_4_nominal = fields.Float('L 35.4 Nominal', digits=(10, 4))
    l_35_4_tol_low = fields.Float('L 35.4 Lower Tol', digits=(10, 4))
    l_35_4_tol_high = fields.Float('L 35.4 Upper Tol', digits=(10, 4))

    l_46_6_nominal = fields.Float('L 46.6 Nominal', digits=(10, 4))
    l_46_6_tol_low = fields.Float('L 46.6 Lower Tol', digits=(10, 4))
    l_46_6_tol_high = fields.Float('L 46.6 Upper Tol', digits=(10, 4))

    l_82_nominal = fields.Float('L 82 Nominal', digits=(10, 4))
    l_82_tol_low = fields.Float('L 82 Lower Tol', digits=(10, 4))
    l_82_tol_high = fields.Float('L 82 Upper Tol', digits=(10, 4))

    l_128_6_nominal = fields.Float('L 128.6 Nominal', digits=(10, 4))
    l_128_6_tol_low = fields.Float('L 128.6 Lower Tol', digits=(10, 4))
    l_128_6_tol_high = fields.Float('L 128.6 Upper Tol', digits=(10, 4))

    l_164_nominal = fields.Float('L 164 Nominal', digits=(10, 4))
    l_164_tol_low = fields.Float('L 164 Lower Tol', digits=(10, 4))
    l_164_tol_high = fields.Float('L 164 Upper Tol', digits=(10, 4))

    runout_e31_e22_nominal = fields.Float('Runout E31-E22 Nominal', digits=(10, 4))
    runout_e31_e22_tol_low = fields.Float('Runout E31-E22 Lower Tol', digits=(10, 4))
    runout_e31_e22_tol_high = fields.Float('Runout E31-E22 Upper Tol', digits=(10, 4))

    runout_e21_e12_nominal = fields.Float('Runout E21-E12 Nominal', digits=(10, 4))
    runout_e21_e12_tol_low = fields.Float('Runout E21-E12 Lower Tol', digits=(10, 4))
    runout_e21_e12_tol_high = fields.Float('Runout E21-E12 Upper Tol', digits=(10, 4))

    runout_e11_tube_end_nominal = fields.Float('Runout E11 tube end Nominal', digits=(10, 4))
    runout_e11_tube_end_tol_low = fields.Float('Runout E11 tube end Lower Tol', digits=(10, 4))
    runout_e11_tube_end_tol_high = fields.Float('Runout E11 tube end Upper Tol', digits=(10, 4))

    ang_diff_e32_e12_pos_tool_nominal = fields.Float('Angular difference E32-E12 pos tool Nominal', digits=(10, 4))
    ang_diff_e32_e12_pos_tool_tol_low = fields.Float('Angular difference E32-E12 pos tool Lower Tol', digits=(10, 4))
    ang_diff_e32_e12_pos_tool_tol_high = fields.Float('Angular difference E32-E12 pos tool Upper Tol', digits=(10, 4))

    ang_diff_e31_e12_pos_tool_nominal = fields.Float('Angular difference E31-E12 pos tool Nominal', digits=(10, 4))
    ang_diff_e31_e12_pos_tool_tol_low = fields.Float('Angular difference E31-E12 pos tool Lower Tol', digits=(10, 4))
    ang_diff_e31_e12_pos_tool_tol_high = fields.Float('Angular difference E31-E12 pos tool Upper Tol', digits=(10, 4))

    ang_diff_e22_e12_pos_tool_nominal = fields.Float('Angular difference E22-E12 pos tool Nominal', digits=(10, 4))
    ang_diff_e22_e12_pos_tool_tol_low = fields.Float('Angular difference E22-E12 pos tool Lower Tol', digits=(10, 4))
    ang_diff_e22_e12_pos_tool_tol_high = fields.Float('Angular difference E22-E12 pos tool Upper Tol', digits=(10, 4))

    ang_diff_e21_e12_pos_tool_nominal = fields.Float('Angular difference E21-E12 pos tool Nominal', digits=(10, 4))
    ang_diff_e21_e12_pos_tool_tol_low = fields.Float('Angular difference E21-E12 pos tool Lower Tol', digits=(10, 4))
    ang_diff_e21_e12_pos_tool_tol_high = fields.Float('Angular difference E21-E12 pos tool Upper Tol', digits=(10, 4))

    ang_diff_e11_e12_pos_tool_nominal = fields.Float('Angular difference E11-E12 pos tool Nominal', digits=(10, 4))
    ang_diff_e11_e12_pos_tool_tol_low = fields.Float('Angular difference E11-E12 pos tool Lower Tol', digits=(10, 4))
    ang_diff_e11_e12_pos_tool_tol_high = fields.Float('Angular difference E11-E12 pos tool Upper Tol', digits=(10, 4))

    result = fields.Selection([
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], string='Result')

    rejection_reason = fields.Text('Rejection Reason')
    failed_fields = fields.Char('Failed Fields')
    raw_data = fields.Text('Raw Data')

    # Computed fields
    within_tolerance = fields.Boolean('Within Tolerance', compute='_compute_within_tolerance')

    @api.depends(
        'l_64_8', 'l_64_8_nominal', 'l_64_8_tol_low', 'l_64_8_tol_high',
        'l_35_4', 'l_35_4_nominal', 'l_35_4_tol_low', 'l_35_4_tol_high',
        'l_46_6', 'l_46_6_nominal', 'l_46_6_tol_low', 'l_46_6_tol_high',
        'l_82', 'l_82_nominal', 'l_82_tol_low', 'l_82_tol_high',
        'l_128_6', 'l_128_6_nominal', 'l_128_6_tol_low', 'l_128_6_tol_high',
        'l_164', 'l_164_nominal', 'l_164_tol_low', 'l_164_tol_high',
        'runout_e31_e22', 'runout_e31_e22_nominal', 'runout_e31_e22_tol_low', 'runout_e31_e22_tol_high',
        'runout_e21_e12', 'runout_e21_e12_nominal', 'runout_e21_e12_tol_low', 'runout_e21_e12_tol_high',
        'runout_e11_tube_end', 'runout_e11_tube_end_nominal', 'runout_e11_tube_end_tol_low', 'runout_e11_tube_end_tol_high',
        'ang_diff_e32_e12_pos_tool', 'ang_diff_e32_e12_pos_tool_nominal', 'ang_diff_e32_e12_pos_tool_tol_low', 'ang_diff_e32_e12_pos_tool_tol_high',
        'ang_diff_e31_e12_pos_tool', 'ang_diff_e31_e12_pos_tool_nominal', 'ang_diff_e31_e12_pos_tool_tol_low', 'ang_diff_e31_e12_pos_tool_tol_high',
        'ang_diff_e22_e12_pos_tool', 'ang_diff_e22_e12_pos_tool_nominal', 'ang_diff_e22_e12_pos_tool_tol_low', 'ang_diff_e22_e12_pos_tool_tol_high',
        'ang_diff_e21_e12_pos_tool', 'ang_diff_e21_e12_pos_tool_nominal', 'ang_diff_e21_e12_pos_tool_tol_low', 'ang_diff_e21_e12_pos_tool_tol_high',
        'ang_diff_e11_e12_pos_tool', 'ang_diff_e11_e12_pos_tool_nominal', 'ang_diff_e11_e12_pos_tool_tol_low', 'ang_diff_e11_e12_pos_tool_tol_high'
    )
    def _compute_within_tolerance(self):
        for record in self:
            checks = []
            def in_window(value, nominal, tol_low, tol_high):
                if value is None or nominal is None or tol_low is None or tol_high is None:
                    return True
                return (nominal + tol_low) <= value <= (nominal + tol_high)

            checks.append(in_window(record.l_64_8, record.l_64_8_nominal, record.l_64_8_tol_low, record.l_64_8_tol_high))
            checks.append(in_window(record.l_35_4, record.l_35_4_nominal, record.l_35_4_tol_low, record.l_35_4_tol_high))
            checks.append(in_window(record.l_46_6, record.l_46_6_nominal, record.l_46_6_tol_low, record.l_46_6_tol_high))
            checks.append(in_window(record.l_82, record.l_82_nominal, record.l_82_tol_low, record.l_82_tol_high))
            checks.append(in_window(record.l_128_6, record.l_128_6_nominal, record.l_128_6_tol_low, record.l_128_6_tol_high))
            checks.append(in_window(record.l_164, record.l_164_nominal, record.l_164_tol_low, record.l_164_tol_high))
            checks.append(in_window(record.runout_e31_e22, record.runout_e31_e22_nominal, record.runout_e31_e22_tol_low, record.runout_e31_e22_tol_high))
            checks.append(in_window(record.runout_e21_e12, record.runout_e21_e12_nominal, record.runout_e21_e12_tol_low, record.runout_e21_e12_tol_high))
            checks.append(in_window(record.runout_e11_tube_end, record.runout_e11_tube_end_nominal, record.runout_e11_tube_end_tol_low, record.runout_e11_tube_end_tol_high))
            checks.append(in_window(record.ang_diff_e32_e12_pos_tool, record.ang_diff_e32_e12_pos_tool_nominal, record.ang_diff_e32_e12_pos_tool_tol_low, record.ang_diff_e32_e12_pos_tool_tol_high))
            checks.append(in_window(record.ang_diff_e31_e12_pos_tool, record.ang_diff_e31_e12_pos_tool_nominal, record.ang_diff_e31_e12_pos_tool_tol_low, record.ang_diff_e31_e12_pos_tool_tol_high))
            checks.append(in_window(record.ang_diff_e22_e12_pos_tool, record.ang_diff_e22_e12_pos_tool_nominal, record.ang_diff_e22_e12_pos_tool_tol_low, record.ang_diff_e22_e12_pos_tool_tol_high))
            checks.append(in_window(record.ang_diff_e21_e12_pos_tool, record.ang_diff_e21_e12_pos_tool_nominal, record.ang_diff_e21_e12_pos_tool_tol_low, record.ang_diff_e21_e12_pos_tool_tol_high))
            checks.append(in_window(record.ang_diff_e11_e12_pos_tool, record.ang_diff_e11_e12_pos_tool_nominal, record.ang_diff_e11_e12_pos_tool_tol_low, record.ang_diff_e11_e12_pos_tool_tol_high))
            record.within_tolerance = all(checks) if checks else False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            # Update or create part quality record
            self._update_part_quality(record)
        return records

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

        part_quality.vici_result = record.result

    # CSV Import Logic
    def _parse_float(self, value):
        try:
            return float(value) if value not in (None, '',) else None
        except Exception:
            return None

    def _compute_result_and_reason(self, vals):
        failed = []
        def check(name, v, n, lo, hi):
            if v is None or n is None or lo is None or hi is None:
                return
            if not ((n + lo) <= v <= (n + hi)):
                failed.append(name)

        check('L 64.8', vals.get('l_64_8'), vals.get('l_64_8_nominal'), vals.get('l_64_8_tol_low'), vals.get('l_64_8_tol_high'))
        check('L 35.4', vals.get('l_35_4'), vals.get('l_35_4_nominal'), vals.get('l_35_4_tol_low'), vals.get('l_35_4_tol_high'))
        check('L 46.6', vals.get('l_46_6'), vals.get('l_46_6_nominal'), vals.get('l_46_6_tol_low'), vals.get('l_46_6_tol_high'))
        check('L 82', vals.get('l_82'), vals.get('l_82_nominal'), vals.get('l_82_tol_low'), vals.get('l_82_tol_high'))
        check('L 128.6', vals.get('l_128_6'), vals.get('l_128_6_nominal'), vals.get('l_128_6_tol_low'), vals.get('l_128_6_tol_high'))
        check('L 164', vals.get('l_164'), vals.get('l_164_nominal'), vals.get('l_164_tol_low'), vals.get('l_164_tol_high'))
        check('Runout E31-E22', vals.get('runout_e31_e22'), vals.get('runout_e31_e22_nominal'), vals.get('runout_e31_e22_tol_low'), vals.get('runout_e31_e22_tol_high'))
        check('Runout E21-E12', vals.get('runout_e21_e12'), vals.get('runout_e21_e12_nominal'), vals.get('runout_e21_e12_tol_low'), vals.get('runout_e21_e12_tol_high'))
        check('Runout E11 tube end', vals.get('runout_e11_tube_end'), vals.get('runout_e11_tube_end_nominal'), vals.get('runout_e11_tube_end_tol_low'), vals.get('runout_e11_tube_end_tol_high'))
        check('Angular difference E32-E12 pos tool', vals.get('ang_diff_e32_e12_pos_tool'), vals.get('ang_diff_e32_e12_pos_tool_nominal'), vals.get('ang_diff_e32_e12_pos_tool_tol_low'), vals.get('ang_diff_e32_e12_pos_tool_tol_high'))
        check('Angular difference E31-E12 pos tool', vals.get('ang_diff_e31_e12_pos_tool'), vals.get('ang_diff_e31_e12_pos_tool_nominal'), vals.get('ang_diff_e31_e12_pos_tool_tol_low'), vals.get('ang_diff_e31_e12_pos_tool_tol_high'))
        check('Angular difference E22-E12 pos tool', vals.get('ang_diff_e22_e12_pos_tool'), vals.get('ang_diff_e22_e12_pos_tool_nominal'), vals.get('ang_diff_e22_e12_pos_tool_tol_low'), vals.get('ang_diff_e22_e12_pos_tool_tol_high'))
        check('Angular difference E21-E12 pos tool', vals.get('ang_diff_e21_e12_pos_tool'), vals.get('ang_diff_e21_e12_pos_tool_nominal'), vals.get('ang_diff_e21_e12_pos_tool_tol_low'), vals.get('ang_diff_e21_e12_pos_tool_tol_high'))
        check('Angular difference E11-E12 pos tool', vals.get('ang_diff_e11_e12_pos_tool'), vals.get('ang_diff_e11_e12_pos_tool_nominal'), vals.get('ang_diff_e11_e12_pos_tool_tol_low'), vals.get('ang_diff_e11_e12_pos_tool_tol_high'))

        result = 'pass' if not failed else 'reject'
        reason = False if not failed else 'Out of tolerance: ' + ', '.join(failed)
        return result, reason, failed

    def import_vici_csv(self, machine_id, filename='vici_vision_data.csv'):
        """Import VICI Vision CSV located in this module's data/csv_data folder.
        :param machine_id: manufacturing.machine.config id
        :param filename: CSV filename inside module folder
        """
        self.ensure_one()
        # Resolve CSV file within this addon
        path = get_module_resource('manufacturing_dashboard', 'data', 'csv_data', filename)
        if not path:
            return False

        records_to_create = []
        with open(path, newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.reader(csvfile)
            rows = list(reader)
            if len(rows) < 7:
                return False

            header = rows[0]
            # rows[1] drawing ids, rows[2] description, rows[3] nominal, rows[4] lower tol, rows[5] upper tol
            nominal_row = rows[3]
            lower_row = rows[4]
            upper_row = rows[5]

            # Map CSV columns to our field names
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

            # Build tolerance dictionaries per column index
            col_to_nominal = {}
            col_to_tol_low = {}
            col_to_tol_high = {}
            for idx, name in enumerate(header):
                if name in field_map:
                    col_to_nominal[idx] = self._parse_float(nominal_row[idx])
                    col_to_tol_low[idx] = self._parse_float(lower_row[idx])
                    col_to_tol_high[idx] = self._parse_float(upper_row[idx])

            # Data rows start at index 6
            for row in rows[6:]:
                if not row or len(row) < 7:
                    continue
                date_str = row[0].strip() if len(row) > 0 else ''
                time_str = row[1].strip() if len(row) > 1 else ''
                operator = row[2].strip() if len(row) > 2 else ''
                batch_sn = row[3].strip() if len(row) > 3 else ''
                measure_number = int(row[4]) if len(row) > 4 and row[4].isdigit() else None
                try:
                    measure_state = int(row[5]) if len(row) > 5 and row[5] != '' else None
                except Exception:
                    measure_state = None
                serial = row[6].strip() if len(row) > 6 else ''

                # Combine date and time (accept DD-MM-YYYY or DD/MM/YYYY); skip if invalid
                if not date_str or not time_str:
                    continue
                parsed_dt = None
                for fmt in ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                    try:
                        parsed_dt = datetime.strptime(f"{date_str} {time_str}", fmt)
                        break
                    except Exception:
                        parsed_dt = None
                if not parsed_dt:
                    continue

                vals = {
                    'serial_number': serial,
                    'machine_id': machine_id,
                    'test_date': parsed_dt,
                    'operator_name': operator,
                    'log_date': parsed_dt.date(),
                    'log_time': time_str or parsed_dt.strftime("%H:%M:%S"),
                    'batch_serial_number': batch_sn,
                    'measure_number': measure_number,
                    'measure_state': measure_state,
                    'raw_data': ','.join(row),
                }

                # Populate measurement values and tolerances
                for idx, name in enumerate(header):
                    if name in field_map and idx < len(row):
                        field_name = field_map[name]
                        vals[field_name] = self._parse_float(row[idx])
                        # Tolerance & nominal to dedicated fields
                        vals[f'{field_name}_nominal'] = col_to_nominal.get(idx)
                        vals[f'{field_name}_tol_low'] = col_to_tol_low.get(idx)
                        vals[f'{field_name}_tol_high'] = col_to_tol_high.get(idx)

                result, reason, failed = self._compute_result_and_reason(vals)
                vals['result'] = result
                vals['rejection_reason'] = reason
                vals['failed_fields'] = False if result == 'pass' else ', '.join(failed)

                records_to_create.append(vals)

        if records_to_create:
            self.create(records_to_create)
            return len(records_to_create)
        return 0