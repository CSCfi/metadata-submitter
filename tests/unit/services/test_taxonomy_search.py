"""Test taxonomy search methods."""

import unittest

from metadata_backend.services.taxonomy_search_handler import TaxonomySearchHandler


class TaxonomySearchTestCase(unittest.TestCase):
    """Taxonomy search test cases."""

    def setUp(self):
        """Set up tests with handler."""
        self.search = TaxonomySearchHandler()

    def test_name_query(self):
        """Test that search by name returns results."""
        results = self.search._search_by_name("ab", self.search.max_results)
        self.assertEqual(len(results), self.search.max_results)

    def test_id_query(self):
        """Test that search by id returns results."""
        results = self.search._search_by_id("11", self.search.max_results)
        self.assertEqual(len(results), self.search.max_results)

    def test_validation_pass(self):
        """Test that query is validated correctly."""
        self.assertTrue(self.search._validate_query("red fir"))

    def test_validation_fail(self):
        """Test that query is validated correctly."""
        self.assertFalse(self.search._validate_query(""))
        self.assertFalse(self.search._validate_query(123))
