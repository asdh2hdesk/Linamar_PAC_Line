# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class StationOverrideWizard(models.TransientModel):
    _name = 'manufacturing.station.override.wizard'
    _description = 'Station Result Override Wizard'

    station_model = fields.Char(string='Station Model', required=True)
    station_record_id = fields.Integer(string='Station Record ID', required=True)
    station_name = fields.Selection([
        ('vici', 'VICI Vision'),
        ('ruhlamat', 'Ruhlamat Press'),
        ('aumann', 'Aumann Measurement'),
        ('gauging', 'Gauging Measurement')
    ], string='Station', required=True)
    station_label = fields.Char(string='Station Label', compute='_compute_station_label', store=False)
    current_result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('reject', 'Reject'),
        ('bypass', 'Bypass')
    ], string='Current Result', readonly=True)
    new_result = fields.Selection([
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], string='New Result', required=True, default='pass')
    comments = fields.Text('Comments', required=True, placeholder="Enter reason for override...")

    @api.depends('station_name')
    def _compute_station_label(self):
        """Compute the station label from station name"""
        labels = {
            'vici': 'VICI Vision',
            'ruhlamat': 'Ruhlamat Press',
            'aumann': 'Aumann Measurement',
            'gauging': 'Gauging Measurement'
        }
        for record in self:
            record.station_label = labels.get(record.station_name, record.station_name)

    @api.model
    def default_get(self, fields_list):
        """Set default values from context"""
        defaults = super().default_get(fields_list)
        
        # Get station record information from context
        if 'station_model' in fields_list and self.env.context.get('default_station_model'):
            defaults['station_model'] = self.env.context['default_station_model']
        elif 'station_model' in fields_list and self.env.context.get('active_model'):
            # Use active_model if it's a station model
            active_model = self.env.context['active_model']
            station_models = {
                'manufacturing.vici.vision': 'manufacturing.vici.vision',
                'manufacturing.ruhlamat.press': 'manufacturing.ruhlamat.press',
                'manufacturing.aumann.measurement': 'manufacturing.aumann.measurement',
                'manufacturing.gauging.measurement': 'manufacturing.gauging.measurement'
            }
            if active_model in station_models:
                defaults['station_model'] = active_model
        
        if 'station_record_id' in fields_list and self.env.context.get('default_station_record_id'):
            defaults['station_record_id'] = self.env.context['default_station_record_id']
        elif 'station_record_id' in fields_list and self.env.context.get('active_id'):
            defaults['station_record_id'] = self.env.context['active_id']
        
        if 'station_name' in fields_list and self.env.context.get('default_station_name'):
            defaults['station_name'] = self.env.context['default_station_name']
        
        # Set current result from station record and default new_result to 'pass'
        if defaults.get('station_model') and defaults.get('station_record_id'):
            try:
                station_record = self.env[defaults['station_model']].browse(defaults['station_record_id'])
                if station_record.exists() and hasattr(station_record, 'result'):
                    # Map station result to part_quality format
                    station_result = station_record.result
                    if station_result in ('pass', 'reject'):
                        defaults['current_result'] = station_result
                    else:
                        defaults['current_result'] = 'pending'
            except Exception:
                pass
        
        # Default new_result to 'pass' (override is for passing rejected parts)
        if 'new_result' in fields_list and 'new_result' not in defaults:
            defaults['new_result'] = 'pass'
        
        return defaults

    def action_override(self):
        """Apply the station override - update station record first, then sync to part_quality"""
        self.ensure_one()
        
        if not self.station_model or not self.station_record_id:
            raise UserError("Station record information is missing")
        
        # Get the station record
        station_record = self.env[self.station_model].browse(self.station_record_id)
        if not station_record.exists():
            raise UserError(f"Station record not found: {self.station_model}({self.station_record_id})")
        
        # Update the station record's result field
        # Note: Station models only support 'pass' and 'reject', not 'pending' or 'bypass'
        station_result = self.new_result if self.new_result in ('pass', 'reject') else 'reject'
        
        # Check if result is a computed stored field (like Ruhlamat)
        result_field = station_record._fields.get('result')
        is_computed_stored = result_field and hasattr(result_field, 'compute') and result_field.store
        
        if is_computed_stored:
            # For computed stored fields, write directly to database to bypass compute method
            table_name = station_record._table
            self.env.cr.execute(
                "UPDATE %s SET result = %%s WHERE id = %%s" % table_name,
                (station_result, station_record.id)
            )
            # Invalidate cache to reflect the change
            station_record.invalidate_recordset(['result'])
        else:
            # For non-computed fields, use normal write
            station_record.write({'result': station_result})
        
        # Re-read the record to get updated result value
        station_record = self.env[self.station_model].browse(self.station_record_id)
        
        # Now sync to part_quality by calling _update_part_quality
        # This will update part_quality with the new result and latest test_date
        if hasattr(station_record, '_update_part_quality'):
            station_record._update_part_quality(station_record)
        else:
            # Fallback: manually update part_quality
            self._sync_to_part_quality(station_record, station_result)
        
        return {'type': 'ir.actions.act_window_close'}
    
    def _sync_to_part_quality(self, station_record, new_result):
        """Sync the station result to part_quality"""
        # Get serial number based on station type
        serial_number = None
        if hasattr(station_record, 'serial_number'):
            serial_number = station_record.serial_number
        elif hasattr(station_record, 'part_id1'):
            serial_number = station_record.part_id1
        
        if not serial_number:
            return
        
        # Find or create part quality record
        part_quality = self.env['manufacturing.part.quality'].search([
            ('serial_number', '=', serial_number)
        ], limit=1)
        
        if not part_quality:
            # Get test_date from station record
            test_date = None
            if hasattr(station_record, 'test_date'):
                test_date = station_record.test_date
            elif hasattr(station_record, 'cycle_date'):
                test_date = station_record.cycle_date
            
            part_quality = self.env['manufacturing.part.quality'].create({
                'serial_number': serial_number,
                'test_date': test_date,
            })
        
        # Map station result to part_quality result field
        station_field_map = {
            'manufacturing.vici.vision': 'vici_result',
            'manufacturing.ruhlamat.press': 'ruhlamat_result',
            'manufacturing.aumann.measurement': 'aumann_result',
            'manufacturing.gauging.measurement': 'gauging_result'
        }
        
        station_field = station_field_map.get(self.station_model)
        if station_field:
            # Update part_quality with override info
            part_quality.with_context(skip_station_recalculate=True).write({
                station_field: new_result,
                'test_date': self.env['manufacturing.part.quality'].get_ist_now(),  # Update test_date on override
                'qe_override': True,
                'qe_comments': f"[{self.station_name.upper()} Override] {self.comments}"
            })

