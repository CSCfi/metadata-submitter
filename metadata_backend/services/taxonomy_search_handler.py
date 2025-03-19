"""Class for handling taxonomy search."""

import re
from typing import Any

import ujson
from aiohttp import web
from aiohttp.web import Request, Response

from ..conf.conf import TAXONOMY_NAME_DATA
from ..helpers.logger import LOG


class TaxonomySearchHandler:
    """Handler for taxonomy search."""

    def __init__(self) -> None:
        """Set default max results for search."""
        self.max_results = 10

    def _validate_query(self, query: str) -> bool:
        """Validate search query.

        :param query: string to validate
        :returns: True if valid
        """
        # Query should be alphanumeric, spaces allowed
        query_pattern = re.compile("^[0-9a-z ]{1,}$")
        try:
            matched = query_pattern.match(query)
        except TypeError:
            return False
        return bool(matched)

    def _search_by_id(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Get search results by tax id.

        param query: id query to search for
        param max_results: how many results to return
        returns: list of items
        """
        search_results = []
        for key, value in TAXONOMY_NAME_DATA.items():
            if key.startswith(query):
                search_results.append({"tax_id": key, **value})
                if len(search_results) >= max_results:
                    return search_results
        return search_results

    def _search_by_name(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Get search results by name.

        Since there's around 3 mil entries, only check the beginning of name

        param query: name query to search for
        param max_results: how many results to return
        returns: list of items
        """
        search_results = []
        for taxId, names in TAXONOMY_NAME_DATA.items():
            for name in names.values():
                if name.lower().startswith(query):
                    search_results.append({"tax_id": taxId, **names})
                    if len(search_results) >= max_results:
                        return search_results
        return search_results

    async def get_query_results(self, req: Request) -> Response:
        """Get query results.

        :param req: GET request
        :raises HTTPBadRequest if query is invalid
        :returns: JSON response containing a list of result dicts with taxonId and names
        """
        # Validate query
        try:
            query = req.query["search"]
        except Exception as exc:
            reason = "Search query is missing"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason) from exc
        query = query.lower()
        valid_query = self._validate_query(query)

        if not valid_query:
            reason = "Search query is invalid"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        # If no result count provided, use default
        max_results: int = self.max_results

        try:
            max_results = int(req.query["results"])
            if max_results < 1:
                raise ValueError
        except KeyError:
            pass
        except ValueError as exc:
            reason = "Search result count is invalid"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason) from exc

        search_results = []

        # Check if to search by taxId or names
        if query.isdigit():
            search_results = self._search_by_id(query, max_results)
        else:
            search_results = self._search_by_name(query, max_results)

        return web.Response(
            body=ujson.dumps(search_results, escape_forward_slashes=False), status=200, content_type="application/json"
        )
