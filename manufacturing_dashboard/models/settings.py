# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ManufacturingDashboardSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    aumann_intake_tolerances_json = fields.Char(
        string='Aumann Intake Tolerances JSON (980)',
        config_parameter='manufacturing.aumann.intake_tolerances_json',
        help='JSON mapping of field name to [lower, upper] limits for serial prefix 980'
    )

    aumann_exhaust_tolerances_json = fields.Char(
        string='Aumann Exhaust Tolerances JSON (480)',
        config_parameter='manufacturing.aumann.exhaust_tolerances_json',
        help='JSON mapping of field name to [lower, upper] limits for serial prefix 480'
    )


