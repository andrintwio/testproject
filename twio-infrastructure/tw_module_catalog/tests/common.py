from odoo.tests.common import TransactionCase
from unittest.mock import MagicMock

class TestTwModuleCatalogCommon(TransactionCase):
    def setUp(self):
        super(TestTwModuleCatalogCommon, self).setUp()
        self.repo_model = self.env['tw.github.repo']
        self.catalog_model = self.env['tw.module.catalog']
        self.queue_model = self.env['tw.module.sync.queue']
        self.tag_model = self.env['tw.module.dependency.tag']

    def _mock_github_client(self):
        """Creates a mocked Github client structure."""
        mock_g = MagicMock()
        mock_org = MagicMock()
        mock_repo = MagicMock()
        
        mock_g.get_organization.return_value = mock_org
        mock_org.get_repos.return_value = [mock_repo]
        
        mock_repo.name = "test-repo"
        mock_repo.fork = False
        mock_repo.default_branch = "main"
        
        mock_branch = MagicMock()
        mock_branch.commit.sha = "fake-sha-123"
        mock_repo.get_branch.return_value = mock_branch
        
        return mock_g, mock_org, mock_repo
