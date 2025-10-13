# -*- coding: utf-8 -*-

from odoo import models, fields, api


class QEOverrideWizard(models.TransientModel):
    _name = 'manufacturing.qe.override.wizard'
    _description = 'QE Override Wizard'

    part_quality_id = fields.Many2one('manufacturing.part.quality', string='Part Quality', required=True)
    new_result = fields.Selection([
        ('pass', 'Pass'),
        ('reject', 'Reject')
    ], string='New Result', required=True)
    comments = fields.Text('Comments', required=True)

    @api.model
    def default_get(self, fields_list):
        """Set default values from context"""
        defaults = super().default_get(fields_list)
        if 'part_quality_id' in fields_list and self.env.context.get('active_id'):
            defaults['part_quality_id'] = self.env.context['active_id']
        return defaults

    def action_override(self):
        """Apply the QE override"""
        self.ensure_one()
        self.part_quality_id.qe_override_result(self.new_result, self.comments)
        return {'type': 'ir.actions.act_window_close'}
