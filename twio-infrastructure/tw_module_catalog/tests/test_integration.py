from .common import TestTwModuleCatalogCommon
from unittest.mock import patch, MagicMock
import base64
import logging
_logger = logging.getLogger(__name__)

class TestIntegrationSync(TestTwModuleCatalogCommon):
    
    @patch('odoo.addons.tw_module_catalog.models.tw_github_repo.Github')
    def test_full_sync_flow(self, mock_github_class):
        """Test the full flow from repository discovery to queue processing."""
        # 1. Setup Mock GitHub Structure
        mock_g, mock_org, mock_repo = self._mock_github_client()
        mock_github_class.return_value = mock_g
        mock_g.get_repo.return_value = mock_repo
        
        # Mock tree with one module
        mock_tree = MagicMock()
        mock_item = MagicMock()
        mock_item.path = "test_mod/__manifest__.py"
        mock_item.sha = "sha_manifest"
        mock_tree.tree = [mock_item]
        mock_repo.get_git_tree.return_value = mock_tree
        
        # Mock blob for manifest
        mock_blob = MagicMock()
        manifest_content = "{'name': 'Test Module', 'depends': ['base']}"
        mock_blob.content = base64.b64encode(manifest_content.encode()).decode()
        mock_repo.get_git_blob.return_value = mock_blob

        # Set GitHub Token parameter
        self.env['ir.config_parameter'].set_param('tw_module_catalog.github_token', 'fake-token')

        # 2. RUN DISCOVERY
        self.repo_model.action_discovery_cron()
        
        # Verify repo record was created
        repo_record = self.repo_model.search([('name', '=', 'test-repo')])
        self.assertTrue(repo_record, "Repo record should have been created")
        
        # Verify item added to queue
        queue_item = self.queue_model.search([('tw_repo_name', '=', 'test-repo')])
        self.assertEqual(len(queue_item), 1, "One item should be in the queue")
        self.assertEqual(queue_item.tw_technical_name, 'test_mod')

        # 3. RUN WORKER (Process Queue)
        # Mock the content fetcher to skip actual API calls inside action_process_queue_cron 
        # as it already tests _process_found_module logic
        with patch('odoo.addons.tw_module_catalog.models.tw_module_catalog.TWModuleCatalog._fetch_module_content') as mock_fetch:
            mock_fetch.return_value = {
                'manifest_raw': manifest_content,
                'index_raw': False,
                'readme_html': False
            }
            self.catalog_model.action_process_queue_cron()

        # 4. VERIFY FINAL CATALOG RECORD
        catalog_record = self.catalog_model.search([('tw_technical_name', '=', 'test_mod')])
        self.assertTrue(catalog_record, "Catalog record should have been created")
        self.assertEqual(catalog_record.name, 'Test Module')
        self.assertEqual(queue_item.state, 'done', "Queue item should be marked as done")
