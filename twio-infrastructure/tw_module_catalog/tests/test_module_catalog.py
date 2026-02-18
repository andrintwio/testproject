from .common import TestTwModuleCatalogCommon

class TestModuleCatalog(TestTwModuleCatalogCommon):
    def test_parse_manifest(self):
        """Test Odoo manifest parsing."""
        valid_manifest = "{'name': 'Test', 'depends': ['base'], 'author': 'TWIO'}"
        data = self.catalog_model._parse_manifest(valid_manifest)
        self.assertEqual(data['name'], 'Test')
        self.assertEqual(data['author'], 'TWIO')

        invalid_manifest = "not a dict"
        data_err = self.catalog_model._parse_manifest(invalid_manifest)
        self.assertFalse(data_err)

    def test_generate_pillar_hashes(self):
        """Test hash generation for grouping models."""
        data = {
            'name': 'Module',
            'author': 'TWIO',
            'summary': 'Summary',
            'description': 'Description',
            'version': '1.0',
            'category': 'Sales',
            'website': 'https://twio.io'
        }
        hashes = self.catalog_model.generate_pillar_hashes(data)
        
        # Pillars are: author, website, category, summary, description
        self.assertIn('tw_hash_1', hashes)
        self.assertIn('tw_hash_2', hashes)
        self.assertNotEqual(hashes['tw_hash_1'], hashes['tw_hash_2'])
        
        # Check stability
        hashes_v2 = self.catalog_model.generate_pillar_hashes(data)
        self.assertEqual(hashes['tw_hash_1'], hashes_v2['tw_hash_1'])
