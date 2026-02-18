from .common import TestTwModuleCatalogCommon

class TestSyncQueue(TestTwModuleCatalogCommon):
    def test_add_to_queue(self):
        """Test the logic for adding modules to the sync queue."""
        repo_name = "test-repo"
        tech_name = "test_module"
        module_path = "addons/test_module"
        shas = {
            'module_sha': 'm123',
            'manifest_sha': 'f123',
            'readme_sha': 'r123',
            'index_sha': 'i123',
            'readme_path': 'README.md'
        }

        # 1. Add new item
        added = self.queue_model.add_to_queue(repo_name, tech_name, module_path, shas)
        self.assertTrue(added)
        
        task = self.queue_model.search([('tw_technical_name', '=', tech_name)])
        self.assertEqual(len(task), 1)
        self.assertEqual(task.state, 'pending')
        self.assertEqual(task.tw_module_sha, 'm123')

        # 2. Add same item again (should skip if pending)
        added_skip = self.queue_model.add_to_queue(repo_name, tech_name, module_path, shas)
        self.assertFalse(added_skip)
        self.assertEqual(self.queue_model.search_count([('tw_technical_name', '=', tech_name)]), 1)

        # 3. Add with different SHA (should update and reset state if not pending)
        task.write({'state': 'done'})
        new_shas = dict(shas, module_sha='m456')
        added_update = self.queue_model.add_to_queue(repo_name, tech_name, module_path, new_shas)
        self.assertTrue(added_update)
        self.assertEqual(task.state, 'pending')
        self.assertEqual(task.tw_module_sha, 'm456')
