from odoo import fields, models, _
from odoo.exceptions import UserError


class TwOdooShGitHubDeviceVerification(models.TransientModel):
    _name = 'tw_odoo_sh.github.device.verification'
    _description = 'GitHub Device Verification Wizard'

    otp_code = fields.Char(string='Verification Code', required=True, help='Enter the GitHub verification code (from e-mail or authenticator app).')

    def action_verify(self):
        """Submit the device verification code to GitHub and finish the OAuth flow."""
        self.ensure_one()
        repo_model = self.env['tw_odoo_sh.repository']
        success = repo_model._submit_github_device_verification(self.otp_code)
        if success:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Verification Successful'),
                    'message': _(
                        'GitHub device verification was successful. '
                        'The Odoo.sh session has been renewed. '
                        'You can now synchronize repositories.'
                    ),
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }
        raise UserError(_('Device verification failed. The code may have expired or is incorrect. Please close this wizard and try synchronizing again.'))

