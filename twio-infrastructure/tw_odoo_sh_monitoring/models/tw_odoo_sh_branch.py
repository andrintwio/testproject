from odoo import fields, models, api
from odoo.tools import email_normalize
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class TwOdooShBranch(models.Model):
    _name = 'tw_odoo_sh.branch'
    _description = 'Odoo.sh Branch'
    _inherit = 'tw_odoo_sh.monitoring.mixin'
    _order = 'tw_stage, tw_last_build_date desc'

    name = fields.Char(string='Branch Name', required=True, index=True)
    tw_branch_id = fields.Integer(string='Odoo.sh Branch ID', required=True, index=True)
    tw_repository_id = fields.Many2one('tw_odoo_sh.repository', string='Repository', required=True, ondelete='cascade', index=True)
    tw_stage = fields.Selection([
            ('production', 'Production'),
            ('staging', 'Staging'),
            ('dev', 'Dev'),
        ], string='Stage')
    tw_last_build_id = fields.Integer(string='Last Build ID')
    tw_last_build_status = fields.Char(string='Last Build Status')
    tw_last_build_result = fields.Char(string='Last Build Result')
    tw_last_build_commit_msg = fields.Text(string='Last Build Commit Message')
    tw_last_build_commit_author = fields.Char(string='Last Build Commit Author')
    tw_last_build_date = fields.Char(string='Last Build Date')
    tw_last_tracking_type = fields.Char(string='Last Tracking Type', help='Type of last tracking: push or rebuild')
    tw_last_pusher_name = fields.Char(string='Last Pusher Name', help='Name of the person who triggered the push or rebuild')
    tw_tracking_count = fields.Integer(string='Tracking Count', default=0)
    tw_last_update = fields.Datetime(string='Last Sync', readonly=True)
    tw_last_update_status = fields.Char(string='Last Update Status', compute='_compute_tw_last_update_status', store=True)
    tw_block_user_id = fields.Many2one('res.users', string='Blocked By', help='User to notify when there are changes in this branch')
    tw_block_date = fields.Datetime(string='Block Date', help='Date when the block was assigned')
    tw_blocked_until = fields.Datetime(string='Blocked Until', help='Date until which the branch is blocked. After this date, a reminder email will be sent to the blocker.')

    @api.depends('tw_last_build_result')
    def _compute_tw_last_update_status(self):
        for branch in self:
            if not branch.tw_last_build_result:
                branch.tw_last_update_status = '⚪'  # Gray for no build
            else:
                result_lower = branch.tw_last_build_result.lower()
                if 'success' in result_lower or 'ok' in result_lower:
                    branch.tw_last_update_status = '🟢'  # Green for success
                elif 'warning' in result_lower or 'warn' in result_lower:
                    branch.tw_last_update_status = '🟡'  # Yellow for warning
                elif 'fail' in result_lower or 'error' in result_lower:
                    branch.tw_last_update_status = '🔴'  # Red for failed
                else:
                    branch.tw_last_update_status = '⚪'  # Gray for unknown

    def _parse_build_datetime(self, date_str):
        """Parse datetime string from Odoo.sh format to datetime object"""
        if not date_str:
            return False
        try:
            # Try to parse common datetime formats from Odoo.sh
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S.%f']:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            return False
        except Exception:
            return False

    def _check_and_send_notification(self, new_build_datetime_str):
        """Check if there's a new build after block date and send notification if needed"""
        if not self.tw_block_user_id or not self.tw_block_date:
            return False
        
        new_build_datetime = self._parse_build_datetime(new_build_datetime_str)
        if not new_build_datetime:
            return False
        
        # Convert block_date to datetime if it's a string
        block_date = self.tw_block_date
        if isinstance(block_date, str):
            block_date = self._parse_build_datetime(block_date)
            if not block_date:
                return False
        
        # Check if new build is after block date
        if new_build_datetime > block_date:
            self._send_block_notification()
            return True
        return False

    def _send_block_notification(self):
        """Send email notification to blocked user about branch changes"""
        if not self.tw_block_user_id:
            return
        
        user = self.tw_block_user_id
        # Get email address from user
        email_to = False
        if user.email:
            email_to = user.email
        elif user.partner_id and user.partner_id.email:
            email_to = user.partner_id.email
        
        if not email_to:
            _logger.warning(f"Cannot send notification to user {user.name}: no email address")
            return
        
        # Prepare email content
        repo_name = self.tw_repository_id.name or 'Unknown Repository'
        branch_name = self.name
        pusher_name = self.tw_last_pusher_name or self.tw_last_build_commit_author or 'Unknown'
        commit_msg = self.tw_last_build_commit_msg or 'No commit message'
        build_date = self.tw_last_build_date or 'Unknown'
        tracking_type = self.tw_last_tracking_type or 'push'
        tracking_type_display = 'Rebuild' if tracking_type == 'rebuild' else 'Push'
        
        subject = f"Branch Change Notification: {branch_name} in {repo_name}"
        body_html = f"""
        <div style="font-family: Arial, sans-serif;">
            <h2>Branch Change Notification</h2>
            <p>Hello {user.name},</p>
            <p>There has been a <strong>{tracking_type_display}</strong> in the branch <strong>{branch_name}</strong> of the repository <strong>{repo_name}</strong>.</p>
            <p>This branch was blocked for you on {self.tw_block_date.strftime('%Y-%m-%d %H:%M:%S') if hasattr(self.tw_block_date, 'strftime') else str(self.tw_block_date)}.</p>
            <hr>
            <h3>Change Details:</h3>
            <ul>
                <li><strong>Type:</strong> {tracking_type_display}</li>
                <li><strong>Date:</strong> {build_date}</li>
                <li><strong>Triggered by:</strong> {pusher_name}</li>
                <li><strong>Message:</strong> {commit_msg}</li>
            </ul>
            <p>Please review the changes and take appropriate action if needed.</p>
        </div>
        """
        
        # Send email using mail.mail
        try:
            mail_values = {
                'subject': subject,
                'body_html': body_html,
                'email_to': email_to,
                'email_from': self.env['ir.config_parameter'].sudo().get_param('mail.catchall.alias', 'noreply@odoo.com'),
                'auto_delete': True,
            }
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            _logger.info(f"Notification email sent to {email_to} for branch {branch_name} in repository {repo_name}")
        except Exception as e:
            _logger.error(f"Error sending notification email: {str(e)}")

    def write(self, vals):
        """Override write to check for new builds and send notifications"""
        # Store old build datetime before update
        old_build_datetime = {}
        for record in self:
            old_build_datetime[record.id] = record.tw_last_build_date
        
        # Auto-set block_date when user is assigned
        if 'tw_block_user_id' in vals:
            if vals.get('tw_block_user_id'):
                # Set block date to now if user is assigned
                if 'tw_block_date' not in vals:
                    vals['tw_block_date'] = fields.Datetime.now()
            else:
                # Clear block date if user is removed
                vals['tw_block_date'] = False
        
        result = super().write(vals)
        
        # Check if tw_last_build_date changed and send notification if needed
        if 'tw_last_build_date' in vals:
            for record in self:
                record._check_and_send_notification(vals.get('tw_last_build_date'))
        
        return result

    def _send_blocked_until_reminder(self):
        """Send reminder email to blocker when blocked_until date is reached"""
        if not self.tw_block_user_id or not self.tw_blocked_until:
            return
        
        user = self.tw_block_user_id
        # Get email address from user
        email_to = False
        if user.email:
            email_to = user.email
        elif user.partner_id and user.partner_id.email:
            email_to = user.partner_id.email
        
        if not email_to:
            _logger.warning(f"Cannot send reminder to user {user.name}: no email address")
            return
        
        # Prepare email content
        repo_name = self.tw_repository_id.name or 'Unknown Repository'
        branch_name = self.name
        blocked_until_str = self.tw_blocked_until.strftime('%Y-%m-%d %H:%M:%S') if hasattr(self.tw_blocked_until, 'strftime') else str(self.tw_blocked_until)
        block_date_str = self.tw_block_date.strftime('%Y-%m-%d %H:%M:%S') if hasattr(self.tw_block_date, 'strftime') else str(self.tw_block_date)
        
        subject = f"Branch Block Reminder: {branch_name} in {repo_name}"
        body_html = f"""
        <div style="font-family: Arial, sans-serif;">
            <h2>Branch Block Reminder</h2>
            <p>Hello {user.name},</p>
            <p>The branch <strong>{branch_name}</strong> in the repository <strong>{repo_name}</strong> has reached its blocked until date (<strong>{blocked_until_str}</strong>).</p>
            <p>This branch was blocked for you on {block_date_str}.</p>
            <hr>
            <h3>Action Required:</h3>
            <p>Please review the branch and:</p>
            <ul>
                <li>Remove the block if it's no longer needed</li>
                <li>Move the "Blocked Until" date forward if you need more time</li>
                <li>Review any recent changes that may have occurred</li>
            </ul>
            <p>You can access the branch in Odoo to make these changes.</p>
        </div>
        """
        
        # Send email using mail.mail
        try:
            mail_values = {
                'subject': subject,
                'body_html': body_html,
                'email_to': email_to,
                'email_from': self.env.user.email or self.env['ir.config_parameter'].sudo().get_param('mail.catchall.alias', 'noreply@odoo.com'),
                'auto_delete': True,
            }
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            _logger.info(f"Block reminder email sent to {email_to} for branch {branch_name} in repository {repo_name}")
        except Exception as e:
            _logger.error(f"Error sending block reminder email: {str(e)}")

    @api.model
    def action_check_blocked_until_reminders(self):
        """Check all branches with blocked_until dates that have passed and send reminders"""
        _logger.info("Checking for branches with expired blocked_until dates...")
        now = fields.Datetime.now()
        
        # Find branches where blocked_until has passed and there's a blocker assigned
        expired_branches = self.search([
            ('tw_blocked_until', '!=', False),
            ('tw_blocked_until', '<=', now),
            ('tw_block_user_id', '!=', False),
        ])
        
        _logger.info(f"Found {len(expired_branches)} branches with expired blocked_until dates")
        
        for branch in expired_branches:
            try:
                branch._send_blocked_until_reminder()
            except Exception as e:
                _logger.error(f"Error processing reminder for branch {branch.name}: {str(e)}")
        
        return len(expired_branches)

    _branch_repository_unique = models.Constraint(
        "unique(tw_branch_id, tw_repository_id)",
        "A branch with the same ID already exists for this repository!",
    )

