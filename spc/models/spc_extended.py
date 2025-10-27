from odoo import models, fields, api, _, tools
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging
_logger = logging.getLogger(__name__)



class StatisticalProcessControl(models.Model):
    _inherit = 'statistical.process.control'
    
    manager = fields.Many2one('res.users', string='Manager', default=lambda self: self.env.user)
    # Add computed field
    is_manager = fields.Boolean(
        compute='_compute_is_manager',
        string='Is Manager'
    )
    approval_members = fields.Many2many('res.users', string='Approval Members')
    stage = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('to_approve', 'To Approve'),
        ('approved', 'Approved'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),
    ], string='Stage', default='draft', track_visibility='onchange')

    approval_line_ids = fields.One2many('spc.approval.line', 'spc_id', string='Approval Lines')
    can_approve = fields.Boolean(compute='_compute_can_approve', string='Can Approve')
    
    stage_display = fields.Char(
        string="Stage Display",
        compute="_compute_stage_display",
        store=False,
    )
    
    def _compute_stage_display(self):
        for record in self:
            selection = record._fields['stage'].selection
            if callable(selection):
                selection = selection(record)
            
            # Handle selection safely to avoid type errors
            selection_dict = {}
            if selection:
                for key, value in selection:
                    selection_dict[key] = value
                    
            if record.stage in selection_dict:
                record.stage_display = selection_dict[record.stage]
            else:
                record.stage_display = ''


    @api.depends('manager')
    def _compute_is_manager(self):
        for record in self:
            record.is_manager = record.manager == self.env.user


    def _send_action_email(self, action_name):
        template = self.env.ref('spc.mail_template_spc_action')
        if template:
            # Send email to the manager
            template.with_context(action_name=action_name).send_mail(
                self.id, force_send=True, email_values={'email_to': self.manager.email}
            )
            
            # Send email to approval members
            for member in self.approval_members:
                template.with_context(action_name=action_name).send_mail(
                    self.id, force_send=True, email_values={'email_to': member.email}
                )
            
            # Send email to users in group_spc_approver (excluding duplicates)
            group_spc_approver = self.env.ref('spc.group_spc_approver')
            for user in group_spc_approver.users:
                if user != self.manager and user not in self.approval_members:
                    template.with_context(action_name=action_name).send_mail(
                        self.id, force_send=True, email_values={'email_to': user.email}
                    )
    
    
    def action_back_to_draft(self):
        """Move from 'in_progress' to 'draft'."""
        self.ensure_one()
        if self.stage == 'in_progress':
            self.write({'stage': 'draft'})
        return True

    def _send_template_email(self, template_id):
        """Send an email using the specified template to manager, approval members, and group_spc_approver users."""
        self.ensure_one()  # Ensure we’re working with a single record
        template = self.env.ref(template_id, raise_if_not_found=False)
        if not template:
            _logger.warning(f"Email template {template_id} not found.")
            return

        # Collect unique recipients: manager, approval members, and group_spc_approver users
        recipients = set()
        
        # Add manager if present and has an email
        if self.manager and self.manager.email:
            recipients.add(self.manager)
        
        # Add approval members if they have emails
        if self.approval_members:
            recipients.update(user for user in self.approval_members if user.email)
        
        # Add users from group_spc_approver
        group_spc_approver = self.env.ref('spc.group_spc_approver', raise_if_not_found=False)
        if group_spc_approver:
            recipients.update(user for user in group_spc_approver.users if user.email)

        # Send email to each unique recipient
        for recipient in recipients:
            try:
                # Cast the template to a mail.template record to access the send_mail method
                mail_template = self.env['mail.template'].browse(template.id)
                mail_template.with_context(recipient_name=recipient.name).send_mail(
                    self.id,
                    force_send=True,
                    email_values={
                        'email_to': recipient.email,
                        'recipient_ids': [(4, recipient.partner_id.id)],  # Link to partner for tracking
                    }
                )
                # template.with_context(recipient_name=recipient.name).send_mail(
                #     self.id,
                #     force_send=True,
                #     email_values={
                #         'email_to': recipient.email,
                #         'recipient_ids': [(4, recipient.partner_id.id)],  # Link to partner for tracking
                #     }
                # )
            except Exception as e:
                _logger.error(f"Failed to send email to {recipient.email} for SPC {self.name}: {str(e)}")

    @api.depends('approval_line_ids', 'approval_line_ids.state', 'stage')
    def _compute_can_approve(self):
        """Determine if the current user can approve the document."""
        group_spc_approver = self.env.ref('spc.group_spc_approver')
        for record in self:
            # Check if the document is in the 'to_approve' stage
            if record.stage == 'to_approve':
                # Allow approval if the user is in group_spc_approver
                if self.env.user in group_spc_approver.users:
                    record.can_approve = True
                else:
                    # Otherwise, check for a pending approval line
                    approval_line = record.approval_line_ids.filtered(
                        lambda l: l.user_id == self.env.user and l.state == 'pending'
                    )
                    record.can_approve = bool(approval_line)
            else:
                # If not in 'to_approve' stage, user cannot approve
                record.can_approve = False

    def action_start(self):
        """Move from 'draft' to 'in_progress'."""
        self.ensure_one()
        if self.stage == 'draft':
            self.write({'stage': 'in_progress'})
            # self._send_action_email('Start')
            self._send_template_email('spc.mail_template_spc_start')
        return True

    def action_send_for_approval(self):
        """Move from 'in_progress' to 'to_approve' and create approval lines."""
        self.ensure_one()
        if not self.approval_members:
            raise UserError(_('Please add approval members before sending for approval.'))
        if self.stage == 'in_progress':
            # Clear existing approval lines
            self.approval_line_ids.unlink()
            # Create approval lines for each member
            approval_lines = [
                {
                    'spc_id': self.id,
                    'user_id': member.id,
                    'state': 'pending',
                } for member in self.approval_members
            ]
            self.env['spc.approval.line'].create(approval_lines)
            self.write({'stage': 'to_approve'})
            # self._send_action_email('Send for Approval')
            self._send_template_email('spc.mail_template_spc_send_for_approval')
        return True


    
    def action_approve(self):
        """Approval member approves their line; move to 'approved' if all approve.
        Manager or users in spc.group_spc_approver can approve directly.
        """
        self.ensure_one()
        
        # Get the spc.group_spc_approver group
        group_spc_approver = self.env.ref('spc.group_spc_approver')
        
        # Check if the current user is the manager or in the spc.group_spc_approver group
        is_special_approver = self.env.user == self.manager or self.env.user in group_spc_approver.users
        
        if self.stage == 'to_approve':
            if is_special_approver:
                # Directly approve the document for manager or group members
                self.write({'stage': 'approved'})
                # Optionally update all approval lines to 'approved'
                self.approval_line_ids.write({'state': 'approved'})
                # self._send_action_email('Approve')
                self._send_template_email('spc.mail_template_spc_approve')
            else:
                # Existing logic for regular users
                approval_line = self.approval_line_ids.filtered(
                    lambda l: l.user_id == self.env.user and l.state == 'pending'
                )
                if approval_line:
                    approval_line.write({'state': 'approved'})
                    self.check_approval_status()
                    # self._send_action_email('Approve')
                    self._send_template_email('spc.mail_template_spc_approve')
        return True

   
    
    def action_reject(self):
        """Approval member rejects their line; move back to 'in_progress'.
        Manager or users in spc.group_spc_approver can reject directly.
        """
        self.ensure_one()
        
        # Get the spc.group_spc_approver group
        group_spc_approver = self.env.ref('spc.group_spc_approver')
        
        # Check if the current user is the manager or in the spc.group_spc_approver group
        is_special_approver = self.env.user == self.manager or self.env.user in group_spc_approver.users
        
        if self.stage == 'to_approve':
            if is_special_approver:
                # Directly reject the document for manager or group members
                self.approval_line_ids.unlink()  # Clear existing approval lines
                self.write({'stage': 'in_progress'})
                # self._send_action_email('Reject')
                self._send_template_email('spc.mail_template_spc_reject')
            else:
                # Existing logic for regular users
                approval_line = self.approval_line_ids.filtered(
                    lambda l: l.user_id == self.env.user and l.state == 'pending'
                )
                if approval_line:
                    approval_line.write({'state': 'rejected'})
                    self.check_approval_status()
                    # self._send_action_email('Reject')
                    self._send_template_email('spc.mail_template_spc_reject')
        return True

    def action_complete(self):
        """Move from 'approved' to 'completed' if the user is in group_spc_approver."""
        self.ensure_one()
        group_spc_approver = self.env.ref('spc.group_spc_approver')
        if self.env.user not in group_spc_approver.users:
            raise UserError(_('Only users in the SPC Approver group can complete this document.'))
        if self.stage != 'approved':
            raise UserError(_('The document must be in the Approved stage to be completed.'))
        self.write({'stage': 'completed'})
        # self._send_action_email('Complete')
        self._send_template_email('spc.mail_template_spc_complete')
        return True


    def action_cancel(self):
        """Manager cancels the document."""
        self.ensure_one()
        if self.env.user != self.manager:
            raise UserError(_('Only the manager can cancel this document.'))
        if self.stage not in ('completed', 'canceled'):
            self.write({'stage': 'canceled'})
            # self._send_action_email('Cancel')
            self._send_template_email('spc.mail_template_spc_cancel')
        return True

    def action_undo(self):
        self.ensure_one()  # Ensures the method operates on a single record
        if self.stage in ('to_approve', 'approved', 'completed', 'canceled'):
            self.approval_line_ids.unlink()  # Remove existing approval lines
            self.write({'stage': 'in_progress'})  # Set stage back to "in_progress"
        else:
            raise UserError(_("Cannot undo from the current state."))
        return True
    
    
    def check_approval_status(self):
        """Check the approval status and update the stage accordingly."""
        self.ensure_one()
        if self.stage == 'to_approve':
            approved = all(line.state == 'approved' for line in self.approval_line_ids)
            rejected = all(line.state == 'rejected' for line in self.approval_line_ids)
            if approved:
                self.write({'stage': 'approved'})
            elif rejected:
                self.approval_line_ids.unlink()
                self.write({'stage': 'in_progress'})
        return True
    
    # def check_approval_status(self):
    #     """Check approval lines and update stage accordingly."""
    #     self.ensure_one()
    #     if all(line.state == 'approved' for line in self.approval_line_ids):
    #         self.write({'stage': 'approved'})
    #     elif any(line.state == 'rejected' for line in self.approval_line_ids):
    #         self.write({'stage': 'in_progress'})


    def _generate_measurement_values(self):
        """
        Ensure measurement values exist for all groups and parameters **without deleting existing values**.
        """
        for record in self:
            existing_values = self.env['spc.measurement.value'].search([
                ('spc_id', '=', record.id)
            ])

            existing_pairs = {(val.parameter_id.id, val.group_id.id) for val in existing_values}

            new_values = []
            for group in record.measurement_group_ids:
                for parameter in record.parameter_ids:
                    if (parameter.id, group.id) not in existing_pairs:
                        new_values.append({
                            'parameter_id': parameter.id,
                            'group_id': group.id,
                            'spc_id': record.id,
                        })

            if new_values:
                self.env['spc.measurement.value'].create(new_values)

    @api.model
    def create(self, vals):
        """
        Override create method to generate measurement values after record creation.
        """
        record = super(StatisticalProcessControl, self).create(vals)
        record._generate_measurement_values()
        return record

    def write(self, vals):
        """
        Override write method to generate measurement values **only for new groups/parameters**.
        """
        result = super(StatisticalProcessControl, self).write(vals)
        if 'measurement_group_ids' in vals or 'parameter_ids' in vals:
            self._generate_measurement_values()
        return result
    
    
    
    
class SpcApprovalLine(models.Model):
    _name = 'spc.approval.line'
    _description = 'SPC Approval Line'

    spc_id = fields.Many2one('statistical.process.control', string='SPC', ondelete='cascade', required=True)
    user_id = fields.Many2one('res.users', string='User', required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='State', default='pending', required=True)
    
    
    
    
     # def action_reject(self):
    #     """Approval member rejects their line; move back to 'in_progress'."""
    #     self.ensure_one()
    #     if self.stage == 'to_approve':
    #         approval_line = self.approval_line_ids.filtered(
    #             lambda l: l.user_id == self.env.user and l.state == 'pending'
    #         )
    #         if approval_line:
    #             approval_line.write({'state': 'rejected'})
    #             self.check_approval_status()
    #     return True
    
    
    # def action_complete(self):
    #     """Manager moves from 'approved' to 'completed'."""
    #     self.ensure_one()
    #     if self.env.user != self.manager:
    #         raise UserError(_('Only the manager can complete this document.'))
    #     if self.stage == 'approved':
    #         self.write({'stage': 'completed'})
    #     return True



    # def action_approve(self):
    #     """Approval member approves their line; move to 'approved' if all approve."""
    #     self.ensure_one()
    #     if self.stage == 'to_approve':
    #         approval_line = self.approval_line_ids.filtered(
    #             lambda l: l.user_id == self.env.user and l.state == 'pending'
    #         )
    #         if approval_line:
    #             approval_line.write({'state': 'approved'})
    #             self.check_approval_status()
    #     return True
    
    
    # def _send_action_email(self, template_id):
    #     """Send an email using the specified template to manager, approval members, and group_spc_approver users."""
    #     template = self.env.ref(template_id)
    #     if template:
    #         # Collect unique recipients
    #         recipients = self.manager | self.approval_members
    #         group_spc_approver = self.env.ref('spc.group_spc_approver')
    #         recipients |= group_spc_approver.users
    #         # Send email to each recipient with their name in the context
    #         for recipient in recipients:
    #             if recipient.email:
    #                 template.with_context(recipient_name=recipient.name).send_mail(
    #                     self.id,
    #                     force_send=True,
    #                     email_values={'email_to': recipient.email}
    #                 )