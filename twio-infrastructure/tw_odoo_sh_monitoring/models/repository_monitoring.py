from odoo import models, fields, api
import requests
import json
import logging
import re
import html as html_module
from datetime import datetime

_logger = logging.getLogger(__name__)


class RepositoryMonitoringMixin(models.AbstractModel):
    _name = 'tw_odoo_sh.monitoring.mixin'
    _description = 'Odoo.sh Repository Monitoring Mixin'

    def _get_session_id(self):
        """Get session ID from config parameter"""
        return self.env['ir.config_parameter'].sudo().get_param('tw_odoo_sh_monitoring.session_id')

    def _get_default_project_id(self):
        """Get default project ID from config parameter"""
        return int(self.env['ir.config_parameter'].sudo().get_param('tw_odoo_sh_monitoring.default_project') or 0)

    def _get_headers(self):
        """Get headers for Odoo.sh API requests"""
        return {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "content-type": "application/json",
            "x-requested-with": "XMLHttpRequest",
            "origin": "https://www.odoo.sh",
            "referer": "https://www.odoo.sh/",
            "user-agent": "Mozilla/5.0",
        }

    def _extract_authenticity_token(self, html_content):
        """Extract GitHub authenticity token from HTML page."""
        token_match = re.search(r'name="authenticity_token"\s+value="([^"]*)"', html_content or '')
        return token_match.group(1) if token_match else ''

    def _get_cookies(self):
        """Get cookies for Odoo.sh API requests. If no session_id, attempt re-login."""
        session_id = self._get_session_id()
        if not session_id:
            _logger.warning("No session_id found. Attempting re-login to obtain one...")
            result = self._relogin_odoo_sh()
            if result == 'device_verification':
                self._notify_device_verification_required()
                raise ValueError("GitHub requires verification. Please go to Odoo.sh Repositories and use 'Renew Odoo.sh Session' to enter the verification code.")
            elif result:
                session_id = self._get_session_id()
            if not session_id:
                raise ValueError("Could not obtain Odoo.sh session_id. Please configure GitHub credentials in Settings > Infrastructure > Odoo.sh Monitoring.")
        return {
            "session_id": session_id,
            "frontend_lang": "en_US",
            "tz": "Europe/Zurich",
        }

    def _relogin_odoo_sh(self):
        """Re-login to Odoo.sh via GitHub OAuth to obtain a fresh session_id.
        Returns:
        True  –> session renewed successfully.
        False –> login failed (credentials wrong, network error, etc.).
        'device_verification' –> GitHub requires a one-time verification code. The caller must open the verification wizard so the user can enter the code.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        github_username = ICP.get_param('tw_odoo_sh_monitoring.github_username')
        github_password = ICP.get_param('tw_odoo_sh_monitoring.github_password')

        if not github_username or not github_password:
            _logger.error("Odoo.sh re-login: GitHub credentials not configured.")
            return False

        _logger.info("Odoo.sh re-login: Starting session renewal...")
        session = requests.Session()
        session.headers.update({
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        })

        try:
            # Step 1: GET login page (redirects to GitHub)
            login_resp = session.get("https://www.odoo.sh/web/login", timeout=30)
            login_resp.raise_for_status()

            # Step 2: Parse form fields from GitHub login page
            page_html = login_resp.text
            form_match = re.search(r'<form[^>]*action="([^"]*)"[^>]*method="post"', page_html)
            form_action = form_match.group(1) if form_match else "/session"

            form_data = {}
            for tag in re.finditer(r'<input\s[^>]*>', page_html, re.DOTALL):
                tag_str = tag.group(0)
                name_m = re.search(r'name="([^"]*)"', tag_str)
                value_m = re.search(r'value="([^"]*)"', tag_str)
                type_m = re.search(r'type="([^"]*)"', tag_str)
                if not name_m or (type_m and type_m.group(1) == "submit"):
                    continue
                form_data[name_m.group(1)] = value_m.group(1) if value_m else ""
            form_data["login"] = github_username
            form_data["password"] = github_password
            form_data["commit"] = "Sign in"
            form_data["webauthn-conditional"] = "undefined"
            form_data["javascript-support"] = "true"
            form_data["webauthn-support"] = "supported"
            form_data["webauthn-iuvpaa-support"] = "unsupported"
            form_data["return_to"] = html_module.unescape(form_data.get("return_to", ""))

            # Step 3: POST credentials to GitHub /session
            post_url = f"https://github.com{form_action}"
            login_post_resp = session.post(post_url, data=form_data, timeout=30, allow_redirects=True)
            login_post_resp.raise_for_status()

            _logger.info("Odoo.sh re-login: POST %s -> %s (final URL: %s)", post_url, login_post_resp.status_code, login_post_resp.url)

            # Step 3b: Check if GitHub requires verification (email OTP or authenticator app)
            verification_endpoint = ''
            otp_field = ''
            verification_html = login_post_resp.text

            if 'sessions/verified-device' in login_post_resp.url:
                _logger.warning("Odoo.sh re-login: GitHub requires verified-device OTP. Manual intervention is needed.")
                verification_endpoint = 'https://github.com/sessions/verified-device'
                otp_field = 'otp'
            elif '/sessions/two-factor' in login_post_resp.url:
                _logger.warning("Odoo.sh re-login: GitHub requires two-factor authentication. Manual intervention is needed.")
                # If GitHub first lands on webauthn page, switch to authenticator app flow.
                if '/sessions/two-factor/webauthn' in login_post_resp.url:
                    app_link_match = re.search(
                        r'<a[^>]*data-test-selector="totp-app-link"[^>]*href="([^"]+)"',
                        login_post_resp.text or '',
                        re.DOTALL
                    )
                    app_path = app_link_match.group(1) if app_link_match else '/sessions/two-factor/app'
                    app_url = f"https://github.com{app_path}"
                    app_resp = session.get(app_url, timeout=30, allow_redirects=True)
                    app_resp.raise_for_status()
                    verification_html = app_resp.text
                    _logger.info("Odoo.sh re-login: Switched to authenticator app flow (URL: %s).", app_resp.url)
                verification_endpoint = 'https://github.com/sessions/two-factor'
                otp_field = 'app_otp'

            if verification_endpoint:
                authenticity_token = self._extract_authenticity_token(verification_html)
                if not authenticity_token:
                    _logger.error("Odoo.sh re-login: Missing authenticity_token for GitHub verification flow.")
                    return False

                cookies_data = []
                for cookie in session.cookies:
                    cookies_data.append({'name': cookie.name, 'value': cookie.value, 'domain': cookie.domain, 'path': cookie.path})
                ICP.set_param('tw_odoo_sh_monitoring.github_session_cookies', json.dumps(cookies_data))
                ICP.set_param('tw_odoo_sh_monitoring.github_authenticity_token', authenticity_token)
                ICP.set_param('tw_odoo_sh_monitoring.github_verification_endpoint', verification_endpoint)
                ICP.set_param('tw_odoo_sh_monitoring.github_verification_otp_field', otp_field)
                ICP.set_param('tw_odoo_sh_monitoring.device_verification_pending', 'True')
                ICP.set_param('tw_odoo_sh_monitoring.device_verification_notification_sent', 'False')
                return 'device_verification'

            # Step 4: Extract and save new session_id
            new_session_id = session.cookies.get("session_id", domain="www.odoo.sh") or session.cookies.get("session_id")

            if not new_session_id:
                _logger.error("Odoo.sh re-login: Failed — no session_id in response cookies.")
                return False

            ICP.set_param('tw_odoo_sh_monitoring.session_id', new_session_id)
            ICP.set_param('tw_odoo_sh_monitoring.device_verification_pending', 'False')
            ICP.set_param('tw_odoo_sh_monitoring.device_verification_notification_sent', 'False')
            ICP.set_param('tw_odoo_sh_monitoring.github_verification_endpoint', '')
            ICP.set_param('tw_odoo_sh_monitoring.github_verification_otp_field', '')
            _logger.info("Odoo.sh re-login: Session renewed successfully.")
            return True
        except Exception as e:
            _logger.error(f"Odoo.sh re-login: Failed — {e}")
            return False

    def _submit_github_device_verification(self, otp_code):
        """Submit the device-verification OTP to GitHub and finish the OAuth flow"""
        ICP = self.env['ir.config_parameter'].sudo()
        cookies_json = ICP.get_param('tw_odoo_sh_monitoring.github_session_cookies')
        authenticity_token = ICP.get_param('tw_odoo_sh_monitoring.github_authenticity_token')
        verification_endpoint = ICP.get_param('tw_odoo_sh_monitoring.github_verification_endpoint') or 'https://github.com/sessions/verified-device'
        otp_field = ICP.get_param('tw_odoo_sh_monitoring.github_verification_otp_field') or 'otp'

        if not cookies_json or not authenticity_token:
            _logger.error("GitHub device verification: No stored session state found.")
            return False

        try:
            cookies_data = json.loads(cookies_json)
        except (json.JSONDecodeError, TypeError):
            _logger.error("GitHub device verification: Invalid stored cookies.")
            return False

        session = requests.Session()
        session.headers.update({
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        })
        for cookie in cookies_data:
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', ''), path=cookie.get('path', '/'))

        try:
            # POST the OTP to GitHub
            payload = {'authenticity_token': authenticity_token, otp_field: otp_code}
            verify_resp = session.post(
                verification_endpoint,
                data=payload,
                timeout=30,
                allow_redirects=True,
            )
            verify_resp.raise_for_status()
            _logger.info("GitHub device verification: POST -> %s (final URL: %s)",verify_resp.status_code, verify_resp.url)

            # If we are still on a verification page, the code was wrong / expired.
            if 'sessions/verified-device' in verify_resp.url or '/sessions/two-factor' in verify_resp.url:
                _logger.error("GitHub device verification: Code rejected or expired.")
                return False

            # Try to obtain the Odoo.sh session_id from the redirect chain
            new_session_id = session.cookies.get("session_id", domain="www.odoo.sh") or session.cookies.get("session_id")

            # Fallback: explicitly visit Odoo.sh login to finish the OAuth flow
            if not new_session_id:
                _logger.info("GitHub device verification: Completing OAuth flow via Odoo.sh login…")
                session.get("https://www.odoo.sh/web/login", timeout=30, allow_redirects=True)
                new_session_id = session.cookies.get("session_id", domain="www.odoo.sh") or session.cookies.get("session_id")

            if new_session_id:
                ICP.set_param('tw_odoo_sh_monitoring.session_id', new_session_id)
                ICP.set_param('tw_odoo_sh_monitoring.device_verification_pending', 'False')
                ICP.set_param('tw_odoo_sh_monitoring.device_verification_notification_sent', 'False')
                ICP.set_param('tw_odoo_sh_monitoring.github_session_cookies', '')
                ICP.set_param('tw_odoo_sh_monitoring.github_authenticity_token', '')
                ICP.set_param('tw_odoo_sh_monitoring.github_verification_endpoint', '')
                ICP.set_param('tw_odoo_sh_monitoring.github_verification_otp_field', '')
                _logger.info("GitHub device verification: Session renewed successfully.")
                return True

            _logger.error("GitHub device verification: Could not obtain session_id after verification.")
            return False
        except Exception as e:
            _logger.error(f"GitHub device verification: Failed — {e}")
            return False

    def _notify_device_verification_required(self):
        """Notify the configured technical responsible about pending device verification"""
        ICP = self.env['ir.config_parameter'].sudo()
        pending = ICP.get_param('tw_odoo_sh_monitoring.device_verification_pending', default='False') == 'True'
        already_notified = ICP.get_param('tw_odoo_sh_monitoring.device_verification_notification_sent', default='False') == 'True'
        if pending and already_notified:
            return

        _logger.error("Odoo.sh session renewal blocked by GitHub verification. An administrator must go to Odoo.sh Repositories → 'Renew Odoo.sh Session' and enter the verification code.")
        responsible_user_id = int(ICP.get_param('tw_odoo_sh_monitoring.responsible_user_id', default=0) or 0)
        if not responsible_user_id:
            _logger.warning("No technical responsible configured in Settings → Infrastructure → Odoo.sh Monitoring. Cannot send device-verification notification.")
            return
        user = self.env['res.users'].sudo().browse(responsible_user_id).exists()
        if not user:
            _logger.warning("Configured technical responsible (ID %s) does not exist.", responsible_user_id)
            return
        notification_body = (
            '<p>GitHub requires <b>verification</b> to renew the Odoo.sh session.</p>'
            '<p>Please go to <b>Odoo.sh Repositories</b> and click '
            '<em>"Renew Odoo.sh Session"</em> to enter the verification code '
            'from your configured GitHub verification method (e-mail or authenticator app).</p>'
            '<p><i>Note: the verification code expires after a few minutes.</i></p>'
        )
        # Email notification
        self.env['mail.thread'].sudo().message_notify(
            subject='GitHub Device Verification Required — Odoo.sh Monitoring',
            body=notification_body,
            partner_ids=user.partner_id.ids,
        )
        ICP.set_param('tw_odoo_sh_monitoring.device_verification_notification_sent', 'True')

    def _odoo_post(self, url, payload, key="result", default=None):
        """Helper: POST request, return JSON field or default."""
        try:
            resp = requests.post(
                url,
                headers=self._get_headers(),
                cookies=self._get_cookies(),
                data=json.dumps(payload),
                timeout=30
            )
            resp.raise_for_status()
            return resp.json().get(key, {} if default is None else default)
        except Exception as e:
            _logger.error(f"Error in _odoo_post: {e}")
            return {} if default is None else default

    def _get_repositories(self, project_id):
        """Fetch repositories for a given project ID"""
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"repository_id": project_id},
            "id": 1,
        }
        result = self._odoo_post("https://www.odoo.sh/project/json/init", payload)
        return result.get("repos", [])

    def _get_branches_info(self, repo_id):
        """Fetch branches for a repository"""
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "args": [repo_id],
                "model": "paas.repository",
                "method": "get_branches_info_public",
                "kwargs": {}
            },
            "id": 1,
        }
        return self._odoo_post(
            "https://www.odoo.sh/web/dataset/call_kw/paas.repository/get_branches_info_public",
            payload,
            default=[]
        )

    def _get_builds_per_branch(self, branch_id, build_limit=1):
        """Fetch builds for a branch (limit to most recent)"""
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"branch_id": branch_id, "build_limit": build_limit},
            "id": 1,
        }
        return self._odoo_post(
            "https://www.odoo.sh/project/json/builds_per_branch",
            payload,
            default=[]
        )

    def _get_branch_history(self, branch_id, offset=0):
        """Fetch branch history info"""
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"branch_id": branch_id, "offset": offset},
            "id": 1,
        }
        return self._odoo_post(
            "https://www.odoo.sh/project/json/branch_history",
            payload,
            default={}
        )

    def _fetch_repository_settings(self, repository_id):
        """Fetch repository settings including users"""
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "repository_id": repository_id,
                "customs_only": True
            },
            "id": 131904383,
        }
        return self._odoo_post(
            "https://www.odoo.sh/project/json/fetch_settings",
            payload,
            default={}
        )

    def _change_user_access_public(self, project_name, hosting_identifier, access_level):
        """Change user access level in Odoo.sh"""
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "args": [
                    project_name,
                    int(hosting_identifier),
                    access_level
                ],
                "model": "paas.repository",
                "method": "change_user_access_public",
                "kwargs": {}
            },
            "id": 332862687,
        }
        return self._odoo_post(
            "https://www.odoo.sh/web/dataset/call_kw/paas.repository/change_user_access_public",
            payload,
            default={}
        )

    def _remove_collaborator_public(self, project_name, hosting_identifier):
        """Remove collaborator from repository in Odoo.sh"""
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "args": [
                    project_name,
                    int(hosting_identifier)
                ],
                "model": "paas.repository",
                "method": "remove_collaborator_public",
                "kwargs": {}
            },
            "id": 379671477,
        }
        return self._odoo_post(
            "https://www.odoo.sh/web/dataset/call_kw/paas.repository/remove_collaborator_public",
            payload,
            default={}
        )

    def _add_collaborator_public(self, project_name, github_username):
        """Add collaborator to repository in Odoo.sh"""
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "args": [
                    project_name,
                    github_username
                ],
                "model": "paas.repository",
                "method": "add_collaborator_public",
                "kwargs": {}
            },
            "id": 713811319,
        }
        return self._odoo_post(
            "https://www.odoo.sh/web/dataset/call_kw/paas.repository/add_collaborator_public",
            payload,
            default={}
        )

    def _parse_datetime(self, date_str):
        """Parse datetime string from Odoo.sh format"""
        if not date_str:
            return False
        try:
            # Try to parse common datetime formats
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            return False
        except Exception:
            return False


