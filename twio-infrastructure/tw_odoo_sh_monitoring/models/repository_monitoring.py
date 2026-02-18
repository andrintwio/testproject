from odoo import models, fields, api
import requests
import json
import logging
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

    def _get_cookies(self):
        """Get cookies for Odoo.sh API requests"""
        session_id = self._get_session_id()
        if not session_id:
            raise ValueError("Odoo.sh Session ID is not configured. Please set it in Settings > Databases > Odoo.sh Monitoring.")
        return {
            "session_id": session_id,
            "frontend_lang": "en_US",
            "tz": "Europe/Zurich",
        }

    def _odoo_post(self, url, payload, key="result", default=None):
        """Helper: POST request, return JSON field or default"""
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


