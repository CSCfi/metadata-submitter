"""ROR Service."""

import re
from datetime import timedelta
from typing import override

from aiocache import SimpleMemoryCache, cached
from aiohttp import ClientResponse
from yarl import URL

from ..api.services.ror import RorService
from ..conf.ror import ror_config
from .service_handler import ServiceHandler


class RorServiceHandler(RorService, ServiceHandler):
    """ROR Service."""

    service_name = "ror"

    def __init__(self) -> None:
        """ROR Service."""

        ror_url = URL(ror_config().ROR_URL)

        super().__init__(
            service_name="ror",
            base_url=ror_url,
            healthcheck_url=ror_url / "heartbeat",
            healthcheck_callback=self.healthcheck_callback,
        )

    @override
    @cached(ttl=int(timedelta(weeks=1).total_seconds()), cache=SimpleMemoryCache)  # type: ignore
    async def is_ror_organisation(self, organisation: str) -> str | None:
        """
        Check if the ROR organisation exists and return the preferred name or None.

        :param organisation: the organisation name
        :return: The preferred name or None
        """

        # https://ror.readme.io/docs/rest-api

        # The query parameter searches for active organisations by
        # the names field, which includes acronyms and aliases,
        # and names in various languages.
        params = {
            "query": '"' + organisation + '"'  # Words separated by a space are searched using OR.
        }
        response = await self._request(method="GET", path="/organizations", params=params)

        items = response.get("items", [])

        if len(items) == 1:
            # Single match: return preferred name.
            item = items[0]
            for name in item.get("names", []):
                if "ror_display" in name.get("types", []):
                    return str(name.get("value"))
        else:
            # Multiple matches or no matches. If multiple matches
            # then match preferred name and return it. If no matches
            # then return None.

            def _normalize(_name: str) -> str:
                _name = _name.lower()
                _name = re.sub(r"[^\w]", "", _name)
                return _name

            normalized_organisation = _normalize(organisation)
            matched_organisations = []
            for item in items:
                for name in item.get("names", []):
                    if "ror_display" in name.get("types", []):
                        value = str(name.get("value"))
                        if _normalize(value) == normalized_organisation:
                            matched_organisations.append(value)

            if len(matched_organisations) == 1:
                return matched_organisations[0]

        return None

    @staticmethod
    async def healthcheck_callback(response: ClientResponse) -> bool:
        content = await response.text()
        return content == "OK"
