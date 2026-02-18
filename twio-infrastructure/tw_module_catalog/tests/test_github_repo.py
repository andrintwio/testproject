from .common import TestTwModuleCatalogCommon
from odoo import fields
import datetime
from unittest.mock import MagicMock

class TestGithubRepo(TestTwModuleCatalogCommon):
    def test_is_up_to_date(self):
        """Test the logic for determining if a repo needs syncing."""
        repo_gh = MagicMock()
        repo_gh.default_branch = "main"
        branch = MagicMock()
        branch.commit.sha = "new-sha"
        repo_gh.get_branch.return_value = branch

        record = self.repo_model.create({'name': 'test-repo', 'tw_last_main_sha': 'old-sha'})
        threshold = fields.Datetime.now() - datetime.timedelta(hours=12)

        # 1. SHA changed and no recent sync -> Should return False (not up to date)
        is_up_to_date, b = record._is_up_to_date(repo_gh, threshold)
        self.assertFalse(is_up_to_date)
        self.assertEqual(b, branch)

        # 2. SHA matches -> Should return True (up to date)
        record.tw_last_main_sha = "new-sha"
        is_up_to_date, b = record._is_up_to_date(repo_gh, threshold)
        self.assertTrue(is_up_to_date)

        # 3. Recent sync -> Should return True (even if SHA mismatch, though unlikely)
        record.tw_last_main_sha = "old-sha"
        record.tw_last_sync = fields.Datetime.now()
        is_up_to_date, b = record._is_up_to_date(repo_gh, threshold)
        self.assertTrue(is_up_to_date)

    def test_get_module_shas(self):
        """Test SHA extraction from tree map."""
        tree_map = {
            'addons/m1/__manifest__.py': 'man1',
            'addons/m1/README.md': 'readme1',
            'addons/m1/static/description/index.html': 'index1',
        }
        res = self.repo_model._get_module_shas('addons/m1', tree_map)
        self.assertEqual(res['manifest_sha'], 'man1')
        self.assertEqual(res['readme_sha'], 'readme1')
        self.assertEqual(res['index_sha'], 'index1')
        self.assertEqual(res['module_sha'], 'man1|readme1|index1')
        self.assertEqual(res['readme_path'], 'addons/m1/README.md')
