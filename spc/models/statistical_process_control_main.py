from odoo import models, fields, api, _, tools
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import math


########################################################################################################
################################ Creating masters model for SPC ########################################
########################################################################################################

class SpcPart(models.Model):
    _name = 'spc.part'
    _description = 'SPC Part'

    # name = fields.Char(string='Part Number', required=True)
    # part_name = fields.Char(string='Part Name', required=True )
    part_id = fields.Many2one('product.product', string='Part', tracking=True, store=True)
    part_number = fields.Char(string='Part Number', tracking=True, related='part_id.default_code', store=True)
    # Use a distinct field name to avoid ORM trying to apply translation JSON operators on plain varchar
    part_name_display = fields.Char(string='Part Name', tracking=True, related='part_id.name', store=True, translate=True)
    
class QualityCharacteristic(models.Model):
    _name = 'quality.characteristic'
    _description = 'Quality Characteristic'
    
    name = fields.Char(string='Quality Characteristic', required=True )
    

class QualityStandard(models.Model):
    _name = 'quality.standard'
    _description = 'Quality Standard'
    
    name = fields.Char(string='Standard', required=True )
    

class InstrumentName(models.Model):
    _name = 'instrument.name'
    _description = 'Instrument Name'
    
    name = fields.Char(string='Instrument Name', required=True )
    
    


class SpcMeasurementParameter(models.Model):
    _name = 'spc.measurement.parameter'
    _description = 'SPC Measurement Parameter'
    _order = 'sequence'
    _rec_name = 'name'

    name = fields.Char(string='Parameter Name', required=True )
    sequence = fields.Integer(string='Sequence', default=10)
    spc_id = fields.Many2one('statistical.process.control', string='SPC', ondelete='cascade')
    measurement_value_ids = fields.One2many('spc.measurement.value', 'parameter_id', string='Values')


class SpcMeasurementGroup(models.Model):
    _name = 'spc.measurement.group'
    _description = 'SPC Measurement Group'
    _order = 'group_no'
    _rec_name = 'group_no'

    group_no = fields.Integer(string='Group Number', required=True)
    date_of_measurement = fields.Datetime(string='Date/Time of Measurement', required=True, default=fields.Datetime.now)
    spc_id = fields.Many2one('statistical.process.control', string='SPC', ondelete='cascade')
    measurement_value_ids = fields.One2many('spc.measurement.value', 'group_id', string='Measured Values')
    
    @api.model
    def create(self, vals_list):
        single = isinstance(vals_list, dict)
        items = vals_list if not single else [vals_list]
        for vals in items:
            spc_id = vals.get('spc_id')
            if spc_id:
                max_group = self.search([('spc_id', '=', spc_id)], order='group_no desc', limit=1)
                vals['group_no'] = (max_group.group_no + 1) if max_group else 1
        records = super(SpcMeasurementGroup, self).create(items)
        return records[0] if single else records

    def unlink(self):
        # Store the deleted group numbers
        deleted_numbers = {rec.group_no: rec.spc_id.id for rec in self}
        res = super(SpcMeasurementGroup, self).unlink()
        
        # Renumber remaining groups
        for spc_id in set(deleted_numbers.values()):
            groups = self.search([('spc_id', '=', spc_id)], order='group_no')
            for index, group in enumerate(groups, start=1):
                if group.group_no != index:
                    group.write({'group_no': index})
        return res
    
class SpcMeasurementValue(models.Model):
    _name = 'spc.measurement.value'
    _description = 'SPC Measurement Value'

    value = fields.Float(string='Value')
    parameter_id = fields.Many2one('spc.measurement.parameter', string='Parameter', ondelete='cascade')
    group_id = fields.Many2one('spc.measurement.group', string='Group', ondelete='cascade')
    spc_id = fields.Many2one(related='group_id.spc_id', store=True)
    
    # Related fields for USL and LSL
    usl = fields.Float(related='spc_id.usl', string='Upper Specification Limit (USL)', store=True, digits=(16, 4))
    lsl = fields.Float(related='spc_id.lsl', string='Lower Specification Limit (LSL)', store=True, digits=(16, 4))

    _sql_constraints = [
        ('unique_parameter_group', 'unique(parameter_id, group_id)', 'A parameter can only have one value per group!')
    ]
    
    @api.model
    def create(self, vals_list):
        """Trigger statistics calculation when new values are created (supports batch)."""
        single = isinstance(vals_list, dict)
        items = vals_list if not single else [vals_list]
        records = super(SpcMeasurementValue, self).create(items)
        for rec in records:
            if rec.spc_id:
                rec.spc_id.action_calculate_statistics()
        return records[0] if single else records

    def write(self, vals):
        """Trigger statistics calculation when an existing value is updated."""
        result = super(SpcMeasurementValue, self).write(vals)
        if 'value' in vals:  # Only trigger if 'value' field is modified
            for record in self:
                if record.spc_id:
                    record.spc_id.action_calculate_statistics()
        return result

    def unlink(self):
        """Trigger statistics calculation when a measurement value is deleted."""
        spc_records = self.mapped('spc_id')
        result = super(SpcMeasurementValue, self).unlink()
        # Recalculate statistics for affected SPC records
        for spc in spc_records:
            if spc.exists():  # Check if SPC record still exists
                spc.action_calculate_statistics()
        return result

    @api.onchange('value')
    def _onchange_value_trigger_statistics(self):
        """Triggers statistics calculation when the value field is changed in the UI"""
        if self.spc_id and self.value is not None:
            # This will trigger when the user changes the value in the form view
            # The actual calculation will happen when the record is saved
            pass
    
class SpcGroupStatistics(models.Model):
    _name = 'spc.group.statistics'
    _description = 'SPC Group Statistics'
    # _auto = False  # This is a database view

    group_id = fields.Many2one('spc.measurement.group', string='Group')
    spc_id = fields.Many2one('statistical.process.control', string='SPC')
    stat_type = fields.Selection([
        ('large', 'LARGE'),
        ('small', 'SMALL'),
        ('range', 'RANGE'),
        ('avg', 'AVG')
    ], string='Statistic Type')
    value = fields.Float(string='Value', digits=(16, 3))
    

class ControlChartConstants(models.Model):
    _name = 'spc.control.chart.constants'
    _description = 'SPC Control Chart Constants'

    spc_id = fields.Many2one('statistical.process.control', string='SPC', ondelete='cascade')
    sample = fields.Integer(string='Sample Size', store=True)
    d2 = fields.Float(string='d2', digits=(16, 3), store=True)
    a2 = fields.Float(string='A2', digits=(16, 3), store=True)
    d3 = fields.Float(string='D3', digits=(16, 3), store=True)
    d4 = fields.Float(string='D4', digits=(16, 3), store=True)
    


class SpcInterval(models.Model):
    _name = 'spc.interval'
    _description = 'SPC Interval'
    _order = 'sequence'

    spc_id = fields.Many2one('statistical.process.control', string='SPC', ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10, store=True)
    interval1 = fields.Float(string='Interval Start', digits=(16, 4), store=True)
    interval2 = fields.Float(string='Interval End', digits=(16, 4), store=True)

    @api.model
    def create(self, vals_list):
        """Automatically set interval1 and interval2 based on previous intervals (batch-safe)."""
        single = isinstance(vals_list, dict)
        items = vals_list if not single else [vals_list]
        for vals in items:
            spc_id = vals.get('spc_id')
            if spc_id:
                spc = self.env['statistical.process.control'].browse(spc_id)
                if not spc.interval_c or spc.interval_c <= 0:
                    raise ValidationError(_("Interval (C) must be greater than zero."))
                last_interval = self.search([('spc_id', '=', spc_id)], order='sequence desc', limit=1)
                if last_interval:
                    vals['interval1'] = last_interval.interval2
                    vals['interval2'] = last_interval.interval2 + spc.interval_c
                    vals['sequence'] = last_interval.sequence + 1
                else:
                    vals['interval1'] = spc.lower_class_limit
                    vals['interval2'] = spc.lower_class_limit + spc.interval_c
                    vals['sequence'] = 1
        records = super(SpcInterval, self).create(items)
        return records[0] if single else records

        return super(SpcInterval, self).create(vals)


class SpcFrequency(models.Model):
    _name = 'spc.frequency'
    _description = 'SPC Frequency'
    _order = 'sequence'

    spc_id = fields.Many2one('statistical.process.control', string='SPC', ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10, store=True)
    frequency = fields.Integer(string='Frequency', store=True)
    current_frequency = fields.Integer(string='Cumulative Frequency', compute='_compute_current_frequency', store=True)
    
    @api.depends('frequency', 'sequence', 'spc_id')
    def _compute_current_frequency(self):
        for record in self:
            # Get all frequency records for this SPC up to current sequence
            prev_records = self.search([
                ('spc_id', '=', record.spc_id.id),
                ('sequence', '<=', record.sequence)
            ], order='sequence')
            
            # Sum frequencies
            total = 0
            for prev in prev_records:
                total += prev.frequency or 0
            
            record.current_frequency = total



class SpcControlLimitsLine(models.Model):
    _name = 'spc.control.limits.line'
    _description = 'SPC Control Limits Line'

    spc_id = fields.Many2one(
        'statistical.process.control',
        string='SPC',
        ondelete='cascade',
    )
    group_id = fields.Many2one(
        'spc.measurement.group',
        string='Group',
    )
    
    ucl_x = fields.Float(string='U.C.L. X', digits=(16, 4))
    lcl_x = fields.Float(string='L.C.L. X', digits=(16, 4))
    ucl_r = fields.Float(string='U.C.L. R', digits=(16, 4))
    lcl_r = fields.Float(string='L.C.L. R', digits=(16, 4))
    avg_range = fields.Float(string='R-BAR', digits=(16, 4))
    avg_of_avgs = fields.Float(string='X-BAR', digits=(16, 4))
    range_value = fields.Float(string='Range', digits=(16, 4))
    avg_value = fields.Float(string='Avg', digits=(16, 4))
    
    
    
########################################################################################################
################################ Main Statistical Process Control model ################################
########################################################################################################

class StatisticalProcessControl(models.Model):
    _name = 'statistical.process.control'
    _description = 'Statistical Process Control System'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    is_auto_created = fields.Boolean(
        string='Auto Created from Ruhlamat',
        default=False,
        help='Indicates this SPC was automatically created from Ruhlamat gauging data'
    )
    
    name = fields.Char(string='Name', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'), store=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.today, store=True)
    product_id = fields.Many2one('product.product', string='Product', store=True)
    product_qty = fields.Float(string='Product Quantity', store=True)
    
    part_no_id = fields.Many2one('product.product', string='Part No', store=True)
    # Removed translate=True to avoid JSONB translation operator issues when searching/spc.part listing
    part_name = fields.Char(string='Part Name', related='part_no_id.name', store=True, translate=True)
    # Mirror display field used in updated views (avoid translation JSON ops)
    part_name_display = fields.Char(string='Part Name', related='part_no_id.name', store=True, translate=True)
    
    quality_char_id = fields.Many2one('quality.characteristic' , string='Quality Characteristic', store=True)
    standard_id = fields.Many2one('quality.standard', string='Standard', store=True)
    instrument_id = fields.Many2one('instrument.name', string='Instrument Name', store=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier', store=True)
    doc_control_no = fields.Char(string='Document Control No', store=True)
    data_collection = fields.Text(string='Data Collection', store=True )
    operation = fields.Char(string='Operation', store=True )
    machine_name = fields.Char(string='Machine Name', store=True )
    least_count = fields.Float(string='Least Count', help="Measurement precision", digits=(16, 3))
    
    sampling_ratio = fields.Integer(
        string='Sampling Ratio', 
        compute='_compute_sampling_ratio', 
        store=True
    )
    
    ### SAMPLING RATIO (ALL DIMENSIONS ARE IN MM)  ###
    #### Upper Specification Limit (USL) ####
    
    usl = fields.Float(string='UTL', store=True, digits=(16, 4))
    #### Lower Specification Limit (LSL) ####
    lsl = fields.Float(string='LTL', store=True, digits=(16, 4))
    
    ###### MEASURED VALUE ########
    #### Parameters (X1, X2, etc.)
    parameter_ids = fields.One2many('spc.measurement.parameter', 'spc_id', string='Measurement Parameters')
    
    #### Groups (1, 2, 3, etc.)
    measurement_group_ids = fields.One2many('spc.measurement.group', 'spc_id', string='Measurement Groups')
    
    #### Measurement Matrix
    measurement_value_ids = fields.One2many('spc.measurement.value', 'spc_id', string='Measurements')
    
    
    
    #### Group Statistics
    group_stat_ids = fields.One2many('spc.group.statistics', 'spc_id', string='Group Statistics')
    
    max_large = fields.Float(string='Maximum Value', compute='_compute_summary_statistics', store=True, digits=(16, 3))
    min_small = fields.Float(string='Minimum Value', compute='_compute_summary_statistics', store=True, digits=(16, 3))
    avg_range = fields.Float(string='Average Range', compute='_compute_summary_statistics', store=True, digits=(16, 5))
    avg_of_avgs = fields.Float(string='Average of Averages', compute='_compute_summary_statistics', store=True, digits=(16, 4))
    
    statistics_calculated = fields.Boolean(string='Statistics Calculated', default=False)
    show_calculate_button = fields.Boolean(string='Show Calculate Button', default=False)
    
    measurement_html = fields.Html(string='Measurement Values Table', compute='_compute_measurement_display')
    group_statistics_html = fields.Html(string='Group Statistics Table', compute='_compute_group_statistics_display')
    
    control_chart_constants_ids = fields.One2many(
        'spc.control.chart.constants', 
        'spc_id',
        string='Control Chart Constants',
        copy=True
    )

    non_conforming_parts = fields.Integer(string='No. of Non Conforming Parts', store=True)
    values_above_ucl = fields.Integer(string='No. of Parts Above UCL', help="Number of parts with values above Upper Control Limit", store=True)
    values_below_lcl = fields.Integer(string='No. of Parts Below LCL', help="Number of parts with values below Lower Control Limit", store=True)
    
    
    process_width = fields.Float(string='Process Width (R)', compute='_compute_advanced_statistics', store=True,
                               help="Difference between maximum and minimum values", digits=(16, 4))
    design_centre = fields.Float(string='Design Centre (D)', compute='_compute_advanced_statistics', store=True,
                               help="Average of USL and LSL", digits=(16, 4))
    starting_point = fields.Float(string='Starting Point', compute='_compute_advanced_statistics', store=True,
                                help="Minimum value from all measurements", digits=(16, 4))
    specification_width = fields.Float(string='Specification Width (S)', compute='_compute_advanced_statistics', store=True,
                                     help="Difference between USL and LSL", digits=(16, 4))
    interval_c = fields.Float(string='Interval (C)', compute='_compute_advanced_statistics', store=True,
                            help="(Process Width + Least Count) / k", digits=(16, 4))
    num_readings = fields.Integer(string='No. of Readings (N)', compute='_compute_advanced_statistics', store=True,
                                help="Count of measurement values")
    num_class_intervals = fields.Float(string='No. of Class Intervals', compute='_compute_advanced_statistics', store=True,
                                     help="1 + 3.222 × log10(N)", digits=(16, 3))
    selected_classes_k = fields.Char(string='Selecting no. of Classes (k)', compute='_compute_advanced_statistics', store=True,
                                   help="Selected number of classes based on sample size")
    index_k = fields.Float(string='Index (K)', compute='_compute_advanced_statistics', store=True,
                         help="R × (D-R) / S", digits=(16, 3))
    shift_x_from_d = fields.Float(string='Shift Of X from D', compute='_compute_advanced_statistics', store=True,
                                help="Difference between average and design center", digits=(16, 4))
    lower_class_limit = fields.Float(string='Lower Class Limit', compute='_compute_advanced_statistics', store=True,
                                   help="Starting Point - (0.5 × Least Count)", digits=(16, 4))
    
    
    interval_ids = fields.One2many('spc.interval', 'spc_id', string='Intervals')
    frequency_ids = fields.One2many('spc.frequency', 'spc_id', string='Frequencies')
    
    # Control Limits and Process Capability Fields
    ucl_x = fields.Float(string='U.C.L.X', compute='_compute_control_limits', store=True,
                       help="Upper Control Limit for X = X̄ + A2×R̄", digits=(16, 4))
    lcl_x = fields.Float(string='L.C.L.X', compute='_compute_control_limits', store=True,
                       help="Lower Control Limit for X = X̄ - A2×R̄", digits=(16, 4))
    ucl_r = fields.Float(string='U.C.L.R', compute='_compute_control_limits', store=True,
                       help="Upper Control Limit for R = R̄ × D4", digits=(16, 4))
    lcl_r = fields.Float(string='L.C.L.R', compute='_compute_control_limits', store=True,
                       help="Lower Control Limit for R = R̄ × D3", digits=(16, 4))
    std_dev = fields.Float(string='Std.Dev.(σ)', compute='_compute_control_limits', store=True,
                         help="Standard Deviation = R̄ / d2", digits=(16, 4))
    cp = fields.Float(string='Cp', compute='_compute_process_capability', store=True,
                    help="Process Capability = (USL-LSL)/(6σ)")
    cpk_u = fields.Float(string='Cpk U', compute='_compute_process_capability', store=True,
                       help="Upper Process Capability = (USL-X̄)/(3σ)")
    cpk_l = fields.Float(string='Cpk L', compute='_compute_process_capability', store=True,
                       help="Lower Process Capability = (X̄-LSL)/(3σ)")
    cpk = fields.Float(string='Actual Cpk', compute='_compute_process_capability', store=True,
                     help="Actual Process Capability = MIN(Cpk U, Cpk L)")
    
    
    
    control_limits_lines = fields.One2many(
        'spc.control.limits.line',
        'spc_id',
        string='Control Limits Lines'
    )
    
    
    @api.model
    def create(self, vals_list):
        # Odoo 17+ passes a list of dicts to create; normalize to list
        is_dict = isinstance(vals_list, dict)
        records = self.env[self._name]
        for vals in (vals_list if not is_dict else [vals_list]):
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('statistical.process.control') or _('New')
        records = super(StatisticalProcessControl, self).create(vals_list)
        for record in records:
            # Automatically create first group when creating SPC record
            if not record.measurement_group_ids:
                self.env['spc.measurement.group'].create({
                    'spc_id': record.id,
                    'group_no': 1,
                    'date_of_measurement': fields.Datetime.now()
                })
            # Defer statistics calculation until user adds parameters & values
            record.statistics_calculated = False
            default_constants = self.env['spc.control.chart.constants'].search([
                ('spc_id', '=', False)
            ])
            for const in default_constants:
                const.copy({'spc_id': record.id})
        return records if not is_dict else records[0]
    
    @api.depends('measurement_value_ids')
    def _compute_sampling_ratio(self):
        """Computes the total number of measurement values."""
        for record in self:
            record.sampling_ratio = len(record.measurement_value_ids)
    
    @api.depends('group_stat_ids', 'group_stat_ids.value', 'group_stat_ids.stat_type', 'measurement_value_ids', 'measurement_value_ids.value', 'usl', 'lsl')
    def _compute_summary_statistics(self):
        for record in self:
            # Filter statistics by type
            large_values = record.group_stat_ids.filtered(lambda s: s.stat_type == 'large').mapped('value')
            small_values = record.group_stat_ids.filtered(lambda s: s.stat_type == 'small').mapped('value')
            range_values = record.group_stat_ids.filtered(lambda s: s.stat_type == 'range').mapped('value')
            avg_values = record.group_stat_ids.filtered(lambda s: s.stat_type == 'avg').mapped('value')
            
            # Calculate summary statistics
            record.max_large = max(large_values) if large_values else 0.0
            record.min_small = min(small_values) if small_values else 0.0
            record.avg_range = sum(range_values) / len(range_values) if range_values else 0.0
            record.avg_of_avgs = sum(avg_values) / len(avg_values) if avg_values else 0.0
            
            # Count values above UCL and below LCL
            all_measurement_values = record.measurement_value_ids.mapped('value')
            
            # Calculate UCL and LCL (if not directly defined)
            # For simple implementation, using specification limits directly
            ucl = record.usl if record.usl else 0.0
            lcl = record.lsl if record.lsl else 0.0
            
            # Count values outside control limits
            record.values_above_ucl = len([v for v in all_measurement_values if isinstance(v, (int, float)) and v > ucl]) if ucl else 0
            record.values_below_lcl = len([v for v in all_measurement_values if isinstance(v, (int, float)) and v < lcl]) if lcl else 0
            
            # Calculate non-conforming parts as the sum of parts above UCL and below LCL
            record.non_conforming_parts = record.values_above_ucl + record.values_below_lcl
            
    
                     
    @api.depends('avg_of_avgs', 'avg_range', 'control_chart_constants_ids', 'control_chart_constants_ids.sample')
    def _compute_control_limits(self):
        for record in self:
            # Get the constants for the largest sample size
            largest_sample_const = False
            if record.control_chart_constants_ids:
                largest_sample_const = record.control_chart_constants_ids.sorted(key=lambda r: r.sample, reverse=True)[0]
            
            if largest_sample_const and record.avg_range and record.avg_of_avgs:
                # Calculate control limits
                record.ucl_x = record.avg_of_avgs + (largest_sample_const.a2 * record.avg_range)
                record.lcl_x = record.avg_of_avgs - (largest_sample_const.a2 * record.avg_range)
                record.ucl_r = record.avg_range * largest_sample_const.d4
                record.lcl_r = record.avg_range * largest_sample_const.d3
                record.std_dev = record.avg_range / largest_sample_const.d2
            else:
                record.ucl_x = 0.0
                record.lcl_x = 0.0
                record.ucl_r = 0.0
                record.lcl_r = 0.0
                record.std_dev = 0.0
    
    @api.depends('std_dev', 'specification_width', 'usl', 'lsl', 'avg_of_avgs')
    def _compute_process_capability(self):
        for record in self:
            if record.std_dev and record.std_dev > 0:
                # Calculate process capability indices
                if record.specification_width:
                    record.cp = record.specification_width / (6 * record.std_dev)
                else:
                    record.cp = 0.0
                    
                if record.usl and record.avg_of_avgs is not None:
                    record.cpk_u = (record.usl - record.avg_of_avgs) / (3 * record.std_dev)
                else:
                    record.cpk_u = 0.0
                    
                if record.lsl and record.avg_of_avgs is not None:
                    record.cpk_l = (record.avg_of_avgs - record.lsl) / (3 * record.std_dev)
                else:
                    record.cpk_l = 0.0
                    
                # Actual Cpk is the minimum of Cpk_u and Cpk_l
                if record.cpk_u > 0 and record.cpk_l > 0:
                    record.cpk = min(record.cpk_u, record.cpk_l)
                else:
                    record.cpk = 0.0
            else:
                record.cp = 0.0
                record.cpk_u = 0.0
                record.cpk_l = 0.0
                record.cpk = 0.0
    
    def initialize_intervals(self):
        """Initialize the first interval record if none exists"""
        for record in self:
            if not record.interval_ids and record.lower_class_limit and record.interval_c:
                self.env['spc.interval'].create({
                    'spc_id': record.id,
                    'interval1': record.lower_class_limit,
                    'interval2': record.lower_class_limit + record.interval_c,
                })

    @api.depends('usl', 'lsl', 'max_large', 'min_small', 'avg_of_avgs', 'measurement_value_ids', 'measurement_value_ids.value', 'least_count')
    def _compute_advanced_statistics(self):
        for record in self:
            # Get all measurement values
            values = record.measurement_value_ids.mapped('value')
            num_values = len(values)

            # Calculate process width (R)
            record.process_width = record.max_large - record.min_small

            # Design center (D)
            record.design_centre = (record.usl + record.lsl) / 2 if record.usl and record.lsl else 0.0

            # Starting point (minimum value)
            record.starting_point = min(values) if values else 0.0

            # Specification width (S)
            record.specification_width = record.usl - record.lsl if record.usl and record.lsl else 0.0

            # Number of readings (N)
            record.num_readings = num_values

            # Number of class intervals
            if num_values > 0:
                import math
                record.num_class_intervals = 1 + 3.222 * math.log10(num_values)
            else:
                record.num_class_intervals = 0

            # Selecting number of classes (k) - UPDATED LOGIC
            if num_values == 50:
                record.selected_classes_k = "6"
                k_value = 6
            elif 51 <= num_values <= 99:  # Handle 51-99 readings
                record.selected_classes_k = "6"
                k_value = 6
            elif num_values == 100:
                record.selected_classes_k = "7"
                k_value = 7
            elif 101 <= num_values <= 199:  # Handle 101-199 readings
                record.selected_classes_k = "7"
                k_value = 7
            elif num_values == 200:
                record.selected_classes_k = "8"
                k_value = 8
            elif 201 <= num_values <= 499:  # Handle 201-499 readings
                record.selected_classes_k = "8"
                k_value = 8
            elif num_values == 500:
                record.selected_classes_k = "9"
                k_value = 9
            elif 501 <= num_values <= 999:  # Handle 501-999 readings
                record.selected_classes_k = "9"
                k_value = 9
            elif num_values >= 1000:
                record.selected_classes_k = "10"
                k_value = 10
            else:
                # For very small samples, use Sturges' formula result
                if record.num_class_intervals > 0:
                    k_value = round(record.num_class_intervals)
                    record.selected_classes_k = str(k_value)
                else:
                    record.selected_classes_k = "6"  # Default
                    k_value = 6
                record.show_calculate_button = True

            # Interval (C)
            if k_value > 0 and record.process_width and record.least_count:
                record.interval_c = (record.process_width + record.least_count) / k_value
            else:
                record.interval_c = 0

                # Index (K)
            if record.specification_width:
                record.index_k = record.process_width * (
                            record.design_centre - record.process_width) / record.specification_width
            else:
                record.index_k = 0

            # Shift of X from D
            record.shift_x_from_d = record.avg_of_avgs - record.design_centre if record.avg_of_avgs and record.design_centre else 0

            # Lower class limit
            record.lower_class_limit = record.starting_point - (
                        0.5 * record.least_count) if record.starting_point and record.least_count else 0

    def action_generate_intervals_and_frequencies(self):
        """Generate intervals and calculate frequencies based on measurement values"""
        self.ensure_one()

        # Validate required fields
        if not self.interval_c or self.interval_c <= 0:
            raise UserError(_("Interval (C) must be calculated first. Please ensure you have measurement values."))

        if not self.lower_class_limit:
            raise UserError(_("Lower Class Limit is not set. Please check your measurements."))

        if not self.selected_classes_k or not self.selected_classes_k.isdigit():
            raise UserError(_("Number of classes (k) is not properly set."))

        k_value = int(self.selected_classes_k)

        # Clear existing intervals and frequencies
        self.interval_ids.unlink()
        self.frequency_ids.unlink()

        # Generate intervals
        intervals = []
        for i in range(k_value):
            interval_start = self.lower_class_limit + (i * self.interval_c)
            interval_end = interval_start + self.interval_c

            interval = self.env['spc.interval'].create({
                'spc_id': self.id,
                'sequence': i + 1,
                'interval1': interval_start,
                'interval2': interval_end,
            })
            intervals.append(interval)

        # Get all measurement values
        all_values = self.measurement_value_ids.mapped('value')

        if not all_values:
            raise UserError(_("No measurement values found. Please add measurements first."))

        # Calculate frequency for each interval
        for interval in intervals:
            # Count how many values fall within this interval
            # interval1 <= value < interval2 (except for last interval which includes upper bound)
            if interval == intervals[-1]:  # Last interval
                count = len([v for v in all_values if interval.interval1 <= v <= interval.interval2])
            else:
                count = len([v for v in all_values if interval.interval1 <= v < interval.interval2])

            # Create frequency record
            self.env['spc.frequency'].create({
                'spc_id': self.id,
                'sequence': interval.sequence,
                'frequency': count,
            })

        # ✅ ADD THESE LINES - Auto-populate display data and generate chart
        self.action_update_interval_frequency_display()
        try:
            self.action_generate_interval_frequency_chart()
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Could not auto-generate chart: {e}")

        # return {
        #     'type': 'ir.actions.client',
        #     'tag': 'display_notification',
        #     'params': {
        #         # 'title': _('Success'),
        #         # 'message': _('Intervals, frequencies, and chart have been generated successfully.'),
        #         'type': 'success',
        #         'sticky': False,
        #     }
        # }

    def action_calculate_statistics(self):
        """Action to calculate statistics"""
        self._compute_group_statistics()

        # Get the groups from measurement_group_ids
        groups = self.measurement_group_ids
        existing_group_ids = groups.ids  # Get IDs of existing groups

        # Delete control limits lines for groups that no longer exist
        orphaned_lines = self.control_limits_lines.filtered(
            lambda line: not line.group_id or line.group_id.id not in existing_group_ids
        )
        orphaned_lines.unlink()

        if not groups:
            self.statistics_calculated = True
            return True

        # Store control limit values
        limit_values = {
            'ucl_x': self.ucl_x,
            'lcl_x': self.lcl_x,
            'ucl_r': self.ucl_r,
            'lcl_r': self.lcl_r,
            'avg_range': self.avg_range,
            'avg_of_avgs': self.avg_of_avgs
        }

        # Process each group
        for group in groups:
            range_stat = self.group_stat_ids.filtered(
                lambda s: s.group_id == group and s.stat_type == 'range'
            )
            avg_stat = self.group_stat_ids.filtered(
                lambda s: s.group_id == group and s.stat_type == 'avg'
            )
            range_value = range_stat.value if range_stat else 0.0
            avg_value = avg_stat.value if avg_stat else 0.0

            existing_line = self.control_limits_lines.filtered(lambda l: l.group_id == group)

            if existing_line:
                existing_line.write({
                    'range_value': range_value,
                    'avg_value': avg_value,
                    'ucl_x': limit_values['ucl_x'],
                    'lcl_x': limit_values['lcl_x'],
                    'ucl_r': limit_values['ucl_r'],
                    'lcl_r': limit_values['lcl_r'],
                    'avg_range': limit_values['avg_range'],
                    'avg_of_avgs': limit_values['avg_of_avgs'],
                })
            else:
                self.env['spc.control.limits.line'].create({
                    'spc_id': self.id,
                    'group_id': group.id,
                    'range_value': range_value,
                    'avg_value': avg_value,
                    'ucl_x': limit_values['ucl_x'],
                    'lcl_x': limit_values['lcl_x'],
                    'ucl_r': limit_values['ucl_r'],
                    'lcl_r': limit_values['lcl_r'],
                    'avg_range': limit_values['avg_range'],
                    'avg_of_avgs': limit_values['avg_of_avgs'],
                })

        self.statistics_calculated = True

        # Auto-generate intervals and frequencies if they don't exist
        if not self.interval_ids and self.interval_c and self.lower_class_limit:
            try:
                self.action_generate_intervals_and_frequencies()
            except UserError as e:
                # Log the error but don't block statistics calculation
                import logging
                _logger = logging.getLogger(__name__)
                _logger.warning(f"Could not auto-generate intervals/frequencies: {e}")

        return True
            

    @api.onchange('usl', 'lsl', 'least_count')
    def _onchange_spec_limits(self):
        """Trigger UI updates when specification limits or least count changes"""
        if self.usl and self.lsl:
            # Update design center immediately for better user experience
            self.design_centre = (self.usl + self.lsl) / 2
            self.specification_width = self.usl - self.lsl
            
            # If we have measurement data, recalculate relevant metrics
            if self.measurement_value_ids:
                # Only recalculate metrics that depend directly on these changed values
                if self.process_width and self.specification_width:
                    self.index_k = self.process_width * (self.design_centre - self.process_width) / self.specification_width
                
                if self.avg_of_avgs:
                    self.shift_x_from_d = self.avg_of_avgs - self.design_centre
        
        # Handle least count changes
        if self.least_count and self.starting_point:
            self.lower_class_limit = self.starting_point - (0.5 * self.least_count)
            
            # Recalculate interval if we have the needed values
            if hasattr(self, 'selected_classes_k') and self.selected_classes_k and self.selected_classes_k.isdigit():
                k_value = float(self.selected_classes_k)
                if k_value > 0 and self.process_width:
                    self.interval_c = (self.process_width + self.least_count) / k_value
            
    def _compute_group_statistics(self):
        """Compute statistics for each measurement group"""
        for record in self:
            # Remove old statistics
            self.env['spc.group.statistics'].search([('spc_id', '=', record.id)]).unlink()
            
            for group in record.measurement_group_ids:
                values = self.env['spc.measurement.value'].search([
                    ('group_id', '=', group.id),
                    ('spc_id', '=', record.id)
                ]).mapped('value')
                
                if values:
                    # Create statistics records
                    self.env['spc.group.statistics'].create({
                        'spc_id': record.id,
                        'group_id': group.id,
                        'stat_type': 'large',
                        'value': max(values)
                    })
                    self.env['spc.group.statistics'].create({
                        'spc_id': record.id,
                        'group_id': group.id,
                        'stat_type': 'small',
                        'value': min(values)
                    })
                    self.env['spc.group.statistics'].create({
                        'spc_id': record.id,
                        'group_id': group.id,
                        'stat_type': 'range',
                        'value': max(values) - min(values)
                    })
                    self.env['spc.group.statistics'].create({
                        'spc_id': record.id,
                        'group_id': group.id,
                        'stat_type': 'avg',
                        'value': sum(values) / len(values)
                    })
            
            # Trigger recomputation of summary fields
            record._compute_summary_statistics()
            record._compute_advanced_statistics()
            record._compute_control_limits()
            record._compute_process_capability()
        
        
        
    #### def action_calculate_statistics(self):
    ###    # """Action to calculate statistics"""
    ###    # """
    ###    # Calculate statistics and update control_limits_lines without deleting existing lines.
    ###    # """
    ###    # self._compute_group_statistics()
    ###    
    ###    
    ###    # # self._compute_group_statistics()
    ###    # # self._compute_summary_statistics()
    ###    # # self._compute_control_limits()
    ###    # # Get the groups from measurement_group_ids
    ###    # groups = self.measurement_group_ids
    ###    # if not groups:
    ###    #     self.statistics_calculated = True  # Mark as calculated if no groups
    ###    #     return True
    ### 
    ###    # # Store control limit values (e.g., from the parent record)
    ###    # limit_values = {
    ###    #     'ucl_x': self.ucl_x,
    ###    #     'lcl_x': self.lcl_x,
    ###    #     'ucl_r': self.ucl_r,
    ###    #     'lcl_r': self.lcl_r,
    ###    #     'avg_range': self.avg_range,
    ###    #     'avg_of_avgs': self.avg_of_avgs
    ###    # }
    ###
    ###    # # Process each group
    ###    # for group in groups:
    ###    #     # Get range and average values for this group (assuming group_stat_ids exists)
    ###    #     range_stat = self.group_stat_ids.filtered(
    ###    #         lambda s: s.group_id == group and s.stat_type == 'range'
    ###    #     )
    ###    #     avg_stat = self.group_stat_ids.filtered(
    ###    #         lambda s: s.group_id == group and s.stat_type == 'avg'
    ###    #     )
    ###    #     range_value = range_stat.value if range_stat else 0.0
    ###    #     avg_value = avg_stat.value if avg_stat else 0.0
    ###
    ###    #     # Check if a line already exists for this group in control_limits_lines
    ###    #     existing_line = self.control_limits_lines.filtered(lambda l: l.group_id == group)
    ###
    ###    #     if existing_line:
    ###    #         # Update the existing line with new values
    ###    #         existing_line.write({
    ###    #             'range_value': range_value,
    ###    #             'avg_value': avg_value,
    ###    #             'ucl_x': limit_values['ucl_x'],
    ###    #             'lcl_x': limit_values['lcl_x'],
    ###    #             'ucl_r': limit_values['ucl_r'],
    ###    #             'lcl_r': limit_values['lcl_r'],
    ###    #             'avg_range': limit_values['avg_range'],
    ###    #             'avg_of_avgs': limit_values['avg_of_avgs'],
    ###    #         })
    ###    #     else:
    ###    #         # Create a new line if none exists for this group
    ###    #         self.env['spc.control.limits.line'].create({
    ###    #             'spc_id': self.id,
    ###    #             'group_id': group.id,
    ###    #             'range_value': range_value,
    ###    #             'avg_value': avg_value,
    ###    #             'ucl_x': limit_values['ucl_x'],
    ###    #             'lcl_x': limit_values['lcl_x'],
    ###    #             'ucl_r': limit_values['ucl_r'],
    ###    #             'lcl_r': limit_values['lcl_r'],
    ###    #             'avg_range': limit_values['avg_range'],
    ###    #             'avg_of_avgs': limit_values['avg_of_avgs'],
    ###    #         })
    ###            
    ###    # self.statistics_calculated = True
    ###    # return True


    @api.onchange('measurement_group_ids')
    def _onchange_measurement_group_ids(self):
                """Lightweight onchange.

                Previous implementation called action_calculate_statistics() which in turn
                creates / updates / unlinks multiple related records (statistics + control
                limit lines). In Odoo 17+ the web client keeps a snapshot of the recordset
                state; performing heavy create/unlink operations inside an onchange can
                lead to diffing issues (the int 'origin' AttributeError) because new
                relational commands are produced outside the expected batched context.

                Strategy:
                - Only clear cached / derived fields client‑side.
                - Defer full statistics recomputation to write() (already handled) or an
                    explicit button the user presses.
                - Set a flag so the UI may show a 'Recalculate' button if desired.
                """
                if self.measurement_group_ids:
                        # Clear control limits lines in memory (do not unlink in onchange)
                        self.control_limits_lines = False
                        # Mark statistics as needing recalculation; actual recompute deferred
                        self.statistics_calculated = False

    @api.depends('measurement_value_ids', 'measurement_value_ids.value')
    def _compute_measurement_display(self):
        for record in self:
            parameters = record.parameter_ids
            groups = record.measurement_group_ids.sorted('group_no')
            if not parameters or not groups:
                record.measurement_html = "<p>No measurements available.</p>"
                continue

            # Build header
            header_template = "<tr><th style='background-color: #f8f9fa; font-weight: bold; padding: 8px; text-align: center;'>Parameter</th>"
            for group in groups:
                header_template += f"<th style='background-color: #f8f9fa; font-weight: bold; padding: 8px; text-align: center;'>Group {group.group_no}</th>"
            header_template += "</tr>"

            # Build rows
            row_template = ""
            for parameter in parameters:
                row_template += "<tr>"
                row_template += f"<td style='padding: 8px; font-weight: bold; text-align: center; background-color: #f8f9fa;'>{parameter.name}</td>"
                
                # Create a dictionary to map group_id to measurement value for this parameter
                measurement_dict = {}
                for measurement in parameter.measurement_value_ids:
                    measurement_dict[measurement.group_id.id] = measurement.value
                
                # Add cells for each group (ensuring all groups have a cell)
                for group in groups:
                    value = measurement_dict.get(group.id, '')
                    cell_style = "padding: 8px; text-align: center;"
                    if value != '':
                        # Color coding based on specification limits
                        if record.usl and record.lsl:
                            if value > record.usl or value < record.lsl:
                                cell_style += " background-color: #ffebee; color: #c62828;"  # Red for out of spec
                            else:
                                cell_style += " background-color: #e8f5e8; color: #2e7d32;"  # Green for in spec
                    row_template += f"<td style='{cell_style}'>{value}</td>"
                row_template += "</tr>"

            html_content = ""
            html_content += "<h3 style='color: #1976d2; margin-bottom: 15px;'>Measurement Values</h3>"
            html_content += "<table class='table' border='1' width='100%' style='border-collapse: collapse; margin-bottom: 20px;'>"
            html_content += header_template
            html_content += row_template
            html_content += "</table>"

            record.measurement_html = html_content

    @api.depends('group_stat_ids', 'group_stat_ids.value')
    def _compute_group_statistics_display(self):
        for record in self:
            stats = record.group_stat_ids
            if not stats:
                record.group_statistics_html = "<p>No statistics available.</p>"
                continue

            # Get unique groups and sort them by group_no
            groups = stats.mapped('group_id').sorted('group_no')
            
            # Build header
            header_template = "<tr><th style='background-color: #f8f9fa; font-weight: bold; padding: 8px; text-align: center;'>Statistic Type</th>"
            for group in groups:
                header_template += f"<th style='background-color: #f8f9fa; font-weight: bold; padding: 8px; text-align: center;'>Group {group.group_no}</th>"
            header_template += "</tr>"

            # Define the order of stat types for consistent display
            stat_type_order = ['large', 'small', 'range', 'avg']
            stat_type_labels = {
                'large': 'LARGE',
                'small': 'SMALL', 
                'range': 'RANGE',
                'avg': 'AVG'
            }
            
            # Build rows
            row_template = ""
            for stat_type in stat_type_order:
                # Check if this stat_type exists in the data
                if stats.filtered(lambda s: s.stat_type == stat_type):
                    row_template += "<tr>"
                    row_template += f"<td style='padding: 8px; font-weight: bold; text-align: center; background-color: #f8f9fa;'>{stat_type_labels[stat_type]}</td>"
                    
                    # Create a dictionary to map group_id to stat value for this stat_type
                    stat_dict = {}
                    for stat in stats.filtered(lambda s: s.stat_type == stat_type):
                        stat_dict[stat.group_id.id] = stat.value
                    
                    # Add cells for each group (ensuring all groups have a cell)
                    for group in groups:
                        value = stat_dict.get(group.id, '')
                        cell_style = "padding: 8px; text-align: center;"
                        if value != '':
                            # Format the value with 3 decimal places
                            formatted_value = f"{value:.3f}" if isinstance(value, (int, float)) else str(value)
                        else:
                            formatted_value = ''
                        row_template += f"<td style='{cell_style}'>{formatted_value}</td>"
                    row_template += "</tr>"

            html_content = ""
            html_content += "<h3 style='color: #1976d2; margin-bottom: 15px;'>Group Statistics</h3>"
            html_content += "<table class='table' border='1' width='100%' style='border-collapse: collapse; margin-bottom: 20px;'>"
            html_content += header_template
            html_content += row_template
            html_content += "</table>"

            record.group_statistics_html = html_content

    def action_calculate_statistics(self):
        """Action to calculate statistics"""
        self._compute_group_statistics()
        
        # Get the groups from measurement_group_ids
        groups = self.measurement_group_ids
        existing_group_ids = groups.ids  # Get IDs of existing groups

        # Delete control limits lines for groups that no longer exist
        # Also delete lines that don't have any group_id
        orphaned_lines = self.control_limits_lines.filtered(
            lambda line: not line.group_id or line.group_id.id not in existing_group_ids
        )
        orphaned_lines.unlink()  # Remove lines for deleted groups or lines without group_id

        if not groups:
            self.statistics_calculated = True  # Mark as calculated if no groups
            return True

        # Store control limit values (e.g., from the parent record)
        limit_values = {
            'ucl_x': self.ucl_x,
            'lcl_x': self.lcl_x,
            'ucl_r': self.ucl_r,
            'lcl_r': self.lcl_r,
            'avg_range': self.avg_range,
            'avg_of_avgs': self.avg_of_avgs
        }

        # Process each group
        for group in groups:
            # Get range and average values for this group (assuming group_stat_ids exists)
            range_stat = self.group_stat_ids.filtered(
                lambda s: s.group_id == group and s.stat_type == 'range'
            )
            avg_stat = self.group_stat_ids.filtered(
                lambda s: s.group_id == group and s.stat_type == 'avg'
            )
            range_value = range_stat.value if range_stat else 0.0
            avg_value = avg_stat.value if avg_stat else 0.0

            # Check if a line already exists for this group in control_limits_lines
            existing_line = self.control_limits_lines.filtered(lambda l: l.group_id == group)

            if existing_line:
                # Update the existing line with new values
                existing_line.write({
                    'range_value': range_value,
                    'avg_value': avg_value,
                    'ucl_x': limit_values['ucl_x'],
                    'lcl_x': limit_values['lcl_x'],
                    'ucl_r': limit_values['ucl_r'],
                    'lcl_r': limit_values['lcl_r'],
                    'avg_range': limit_values['avg_range'],
                    'avg_of_avgs': limit_values['avg_of_avgs'],
                })
            else:
                # Create a new line if none exists for this group
                self.env['spc.control.limits.line'].create({
                    'spc_id': self.id,
                    'group_id': group.id,
                    'range_value': range_value,
                    'avg_value': avg_value,
                    'ucl_x': limit_values['ucl_x'],
                    'lcl_x': limit_values['lcl_x'],
                    'ucl_r': limit_values['ucl_r'],
                    'lcl_r': limit_values['lcl_r'],
                    'avg_range': limit_values['avg_range'],
                    'avg_of_avgs': limit_values['avg_of_avgs'],
                })
                
        self.statistics_calculated = True
        return True

    def action_calculate_interval_c(self):
        """Calculate Interval (C) manually based on current values and recommended k."""
            
        for record in self:
            k_value = 0
            if record.selected_classes_k and record.selected_classes_k.isdigit():
                k_value = float(record.selected_classes_k)
                
            if k_value > 0:
                # Calculate recommended k using Sturges' formula: 1 + 3.222 * log10(N)
                record.interval_c = (record.process_width + record.least_count) / k_value
                record.show_calculate_button = False
            else:
                record.interval_c = "0"
                
            # if record.selected_classes_k and record.selected_classes_k.isdigit():
            #     k_value = float(record.selected_classes_k)
                        
            # # Interval (C)
            # if k_value > 0:
            #     record.interval_c = (record.process_width + record.least_count) / k_value
            # else:
            #     record.interval_c = 0            
    
    
    @api.model
    def write(self, vals):
        """
        Override write to recalculate statistics when measurement_value_ids is updated.
        """
        # Call the parent write method to save the changes
        res = super(StatisticalProcessControl, self).write(vals)

        # Recalculate statistics if measurement values OR groups changed
        if any(k in vals for k in ('measurement_value_ids', 'measurement_group_ids')):
            # Use sudo-less call; method handles unlink/create of derived lines
            self.action_calculate_statistics()

        return res
    
    @api.constrains('usl', 'lsl')
    def _check_spec_limits(self):
        for record in self:
            if record.usl and record.lsl:
                if record.usl <= record.lsl:
                    raise ValidationError(_("USL must be greater than LSL"))
    
    
    def _generate_measurement_values(self):
        for group in self.measurement_group_ids:
            for param in self.parameter_ids:
                self.env['spc.measurement.value'].create({
                    'parameter_id': param.id,
                    'group_id': group.id,
                    'spc_id': self.id,
                })
    
    def action_open_measurement_pivot(self):
        self.ensure_one()
        return {
            'name': _('Measurement Pivot'),
            'view_mode': 'pivot',
            'res_model': 'spc.measurement.value',
            'domain': [('spc_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {
                'default_spc_id': self.id,
                'search_default_spc_id': self.id,
            },
        }

        
    def action_view_statistics_pivot(self):
        self.ensure_one()
        # Calculate statistics if needed
        if not self.group_stat_ids:
            self._compute_group_statistics()
        
        return {
            'name': _('Group Statistics Pivot'),
            'view_mode': 'pivot',
            'res_model': 'spc.group.statistics',
            'domain': [('spc_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {
                'pivot_measures': ['value'],
                'pivot_row_groupby': ['stat_type'],
                'pivot_column_groupby': ['group_id'],
            },
        }