"""Test taxonomy search."""

import logging

from tests.integration.helpers import search_taxonomy

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_taxonomy_search_by_name_works(client_logged_in):
    """Test that taxonomy search by name works.

    :param client_logged_in: HTTP client in which request call is made
    """
    query = "ab"
    res = await search_taxonomy(client_logged_in, query)
    assert len(res) == 10
    for item in res:
        assert item["scientific_name"].lower().startswith(query) or item["common_name"].lower().startswith(query)
    LOG.debug(res)


async def test_taxonomy_search_by_id_works(client_logged_in):
    """Test that taxonomy search by id works.

    :param client_logged_in: HTTP client in which request call is made
    """
    query = "10"
    res = await search_taxonomy(client_logged_in, query)
    assert len(res) == 10
    for item in res:
        assert item["tax_id"].startswith(query)
    LOG.debug(res)


async def test_taxonomy_limit_search_results_works(client_logged_in):
    """Test that taxonomy search results can be limited.

    :param client_logged_in: HTTP client in which request call is made
    """
    query = "10"
    max_results = 5
    res = await search_taxonomy(client_logged_in, query, max_results)
    assert len(res) == max_results
    LOG.debug(res)


async def test_taxonomy_invalid_query_fails(client_logged_in):
    """Test that search with invalid search query fails.

    :param client_logged_in: HTTP client in which request call is made
    """
    query = ""
    res = await search_taxonomy(client_logged_in, query)
    assert res.status == 400


async def test_taxonomy_invalid_result_count_fails(client_logged_in):
    """Test that search with invalid result count fails.

    :param client_logged_in: HTTP client in which request call is made
    """
    query = "ac"
    max_results = 0
    res = await search_taxonomy(client_logged_in, query, max_results)
    assert res.status == 400
