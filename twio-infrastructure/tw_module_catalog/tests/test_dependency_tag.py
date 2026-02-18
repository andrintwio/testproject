from .common import TestTwModuleCatalogCommon

class TestDependencyTag(TestTwModuleCatalogCommon):
    def test_get_or_create_tags(self):
        """Test tag creation and retrieval logic."""
        depends = ['base', 'sale', 'base ', '']
        
        # Initial call should create tags
        tag_ids = self.tag_model.get_or_create_tags(depends)
        
        # Check that empty and duplicates are handled
        self.assertEqual(len(tag_ids), 2, "Should have created only 2 unique, non-empty tags")
        
        tags = self.tag_model.browse(tag_ids)
        tag_names = tags.mapped('name')
        self.assertIn('base', tag_names)
        self.assertIn('sale', tag_names)
        
        # Second call with same names should NOT create new records
        tag_ids_second = self.tag_model.get_or_create_tags(['base'])
        self.assertEqual(tag_ids_second[0], tags.filtered(lambda t: t.name == 'base').id)
        
        total_count = self.tag_model.search_count([('name', 'in', ['base', 'sale'])])
        self.assertEqual(total_count, 2, "Records should be reused, not duplicated")
