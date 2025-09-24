# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class RuhlamatPress(models.Model):
    _name = 'manufacturing.ruhlamat.press'
    _description = 'Ruhlamat Press System Data'
    _order = 'cycle_date desc'
    _rec_name = 'part_id1'

    # Primary fields from Cycles table
    cycle_id = fields.Integer('Cycle ID', required=True, index=True)
    program_name = fields.Char('Program Name')
    cycle_date = fields.Datetime('Cycle Date', required=True)
    program_id = fields.Integer('Program ID')
    station_id = fields.Char('Station ID')
    station_name = fields.Char('Station Name')
    station_label = fields.Char('Station Label')

    # Part IDs (serial numbers)
    part_id1 = fields.Char('Part ID 1 (Serial Number)', index=True)
    part_id2 = fields.Char('Part ID 2')
    part_id3 = fields.Char('Part ID 3')
    part_id4 = fields.Char('Part ID 4')
    part_id5 = fields.Char('Part ID 5')

    # Result fields
    ok_status = fields.Integer('OK Status')
    cycle_status = fields.Integer('Cycle Status')

    # Additional cycle info
    ufm_username = fields.Char('UFM Username')
    cycle_runtime_nc = fields.Float('Cycle Runtime NC', digits=(10, 3))
    cycle_runtime_pc = fields.Float('Cycle Runtime PC', digits=(10, 3))
    nc_runtime_cycle_no = fields.Integer('NC Runtime Cycle No')
    nc_total_cycle_no = fields.Integer('NC Total Cycle No')
    program_date = fields.Datetime('Program Date')
    ufm_version = fields.Integer('UFM Version')
    ufm_service_info = fields.Integer('UFM Service Info')

    # Custom fields
    custom_int1 = fields.Integer('Custom Int 1')
    custom_int2 = fields.Integer('Custom Int 2')
    custom_int3 = fields.Integer('Custom Int 3')
    custom_string1 = fields.Char('Custom String 1')
    custom_string2 = fields.Char('Custom String 2')
    custom_string3 = fields.Char('Custom String 3')
    custom_xml = fields.Text('Custom XML')

    # Related gaugings
    gauging_ids = fields.One2many('manufacturing.ruhlamat.gauging', 'cycle_id_ref', string='Gaugings')

    # Machine reference
    machine_id = fields.Many2one('manufacturing.machine.config', 'Machine', required=True)

    # Computed fields
    result = fields.Selection([
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], string='Result', compute='_compute_result', store=True)

    total_gaugings = fields.Integer('Total Gaugings', compute='_compute_gauging_stats', store=True)
    passed_gaugings = fields.Integer('Passed Gaugings', compute='_compute_gauging_stats', store=True)
    rejection_reason = fields.Text('Rejection Reason', compute='_compute_result', store=True)

    # Add this Many2one field to link to part quality
    part_quality_id = fields.Many2one(
        'manufacturing.part.quality',
        string='Part Quality Reference',
        ondelete='set null'
    )

    test_date = fields.Datetime(
        string='Test Date',
        related='cycle_date',
        store=True,
        readonly=False,  # If you want to allow editing it manually
    )

    @api.depends('gauging_ids', 'ok_status', 'cycle_status')
    def _compute_result(self):
        for record in self:
            # Check overall cycle status first
            if record.ok_status == -1 or record.cycle_status != 0:
                record.result = 'reject'
                record.rejection_reason = 'Cycle failed: '
                if record.ok_status == -1:
                    record.rejection_reason += 'OK status failed. '
                if record.cycle_status != 0:
                    record.rejection_reason += f'Cycle status error ({record.cycle_status}). '
            else:
                # Check individual gaugings
                failed_gaugings = record.gauging_ids.filtered(lambda g: g.ok_status == -1 or g.gauging_status != 0)
                if failed_gaugings:
                    record.result = 'reject'
                    failures = []
                    for g in failed_gaugings:
                        failure_msg = f"Gauging {g.gauging_no} ({g.gauging_alias})"
                        if g.actual_y and g.lower_limit and g.upper_limit:
                            if g.actual_y < g.lower_limit:
                                failure_msg += f" - Below lower limit ({g.actual_y:.2f} < {g.lower_limit:.2f})"
                            elif g.actual_y > g.upper_limit:
                                failure_msg += f" - Above upper limit ({g.actual_y:.2f} > {g.upper_limit:.2f})"
                        failures.append(failure_msg)
                    record.rejection_reason = 'Failed gaugings: ' + '; '.join(failures)
                else:
                    record.result = 'pass'
                    record.rejection_reason = False

    @api.depends('gauging_ids')
    def _compute_gauging_stats(self):
        for record in self:
            record.total_gaugings = len(record.gauging_ids)
            record.passed_gaugings = len(record.gauging_ids.filtered(
                lambda g: g.ok_status != -1 and g.gauging_status == 0
            ))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            # Update or create part quality record using part_id1 as serial number
            if record.part_id1:
                self._update_part_quality(record)
        return records

    def _update_part_quality(self, record):
        """Update the corresponding part quality record"""
        part_quality = self.env['manufacturing.part.quality'].search([
            ('serial_number', '=', record.part_id1)
        ], limit=1)

        if not part_quality:
            part_quality = self.env['manufacturing.part.quality'].create({
                'serial_number': record.part_id1,
                'test_date': record.cycle_date,
            })

        # Update the relationship
        record.part_quality_id = part_quality.id

        # Update the result
        part_quality.ruhlamat_result = record.result


class RuhlamatGauging(models.Model):
    _name = 'manufacturing.ruhlamat.gauging'
    _description = 'Ruhlamat Gauging Data'
    _order = 'gauging_id'
    _rec_name = 'gauging_alias'

    # Primary fields
    gauging_id = fields.Integer('Gauging ID', required=True, index=True)
    cycle_id = fields.Integer('Cycle ID', required=True, index=True)
    cycle_id_ref = fields.Many2one('manufacturing.ruhlamat.press',
                                   string='Cycle Reference',
                                   compute='_compute_cycle_ref',
                                   store=True)

    # Gauging details
    program_name = fields.Char('Program Name')
    cycle_date = fields.Datetime('Cycle Date')
    gauging_no = fields.Integer('Gauging No')
    gauging_type = fields.Char('Gauging Type')
    anchor = fields.Char('Anchor')
    ok_status = fields.Integer('OK Status')
    gauging_status = fields.Integer('Gauging Status')

    # Measurement values
    actual_x = fields.Float('Actual X', digits=(10, 4))
    signal_x_unit = fields.Char('Signal X Unit')
    actual_y = fields.Float('Actual Y', digits=(10, 6))
    signal_y_unit = fields.Char('Signal Y Unit')

    # Limits
    limit_testing = fields.Integer('Limit Testing')
    start_x = fields.Float('Start X', digits=(10, 2))
    end_x = fields.Float('End X', digits=(10, 2))
    upper_limit = fields.Float('Upper Limit', digits=(10, 2))
    lower_limit = fields.Float('Lower Limit', digits=(10, 2))

    # Additional info
    running_no = fields.Integer('Running No')
    gauging_alias = fields.Char('Gauging Alias')
    signal_x_name = fields.Char('Signal X Name')
    signal_y_name = fields.Char('Signal Y Name')
    signal_x_id = fields.Integer('Signal X ID')
    signal_y_id = fields.Integer('Signal Y ID')

    # Offsets and edge types
    abs_offset_x = fields.Float('Abs Offset X', digits=(10, 4))
    abs_offset_y = fields.Float('Abs Offset Y', digits=(10, 4))
    edge_type_bottom = fields.Char('Edge Type Bottom')
    edge_type_left = fields.Char('Edge Type Left')
    edge_type_right = fields.Char('Edge Type Right')
    edge_type_top = fields.Char('Edge Type Top')

    # Step data
    from_step_data = fields.Integer('From Step Data')
    step_no = fields.Integer('Step No')
    last_step = fields.Integer('Last Step')

    # Computed fields
    within_tolerance = fields.Boolean('Within Tolerance', compute='_compute_tolerance', store=True)
    tolerance_status = fields.Char('Tolerance Status', compute='_compute_tolerance', store=True)

    @api.depends('cycle_id')
    def _compute_cycle_ref(self):
        for record in self:
            cycle = self.env['manufacturing.ruhlamat.press'].search([
                ('cycle_id', '=', record.cycle_id)
            ], limit=1)
            record.cycle_id_ref = cycle.id if cycle else False

    @api.depends('actual_y', 'lower_limit', 'upper_limit', 'limit_testing')
    def _compute_tolerance(self):
        for record in self:
            if record.limit_testing == -1 and record.lower_limit and record.upper_limit:
                if record.lower_limit <= record.actual_y <= record.upper_limit:
                    record.within_tolerance = True
                    record.tolerance_status = 'Pass'
                else:
                    record.within_tolerance = False
                    if record.actual_y < record.lower_limit:
                        record.tolerance_status = f'Below limit ({record.actual_y:.2f} < {record.lower_limit:.2f})'
                    else:
                        record.tolerance_status = f'Above limit ({record.actual_y:.2f} > {record.upper_limit:.2f})'
            else:
                record.within_tolerance = True
                record.tolerance_status = 'No limit testing'