"""Mock aiohttp.web server for DOI API calls."""

import json
import logging
from datetime import datetime

from aiohttp import web


async def dois(req: web.Request) -> web.Response:
    """DOI endpoint."""
    try:
        content = await req.json()
    except json.decoder.JSONDecodeError as e:
        reason = "JSON is not correctly formatted." f" See: {e}"
        logging.info(reason)
        raise web.HTTPBadRequest(reason=reason)

    try:
        attributes = content["data"]["attributes"]
    except KeyError:
        reason = "Provided payload did not include required attributes."
        logging.info(reason)
        raise web.HTTPBadRequest(reason=reason)

    data = {
        "data": {
            "id": "10.xxxx/yyyy",
            "type": "dois",
            "attributes": {
                "doi": "10.xxxx/yyyy",
                "prefix": "10.xxxx",
                "suffix": "yyyy",
                "identifiers": [{"identifier": "https://mock_doi.org/10.xxxx/yyyy", "identifierType": "DOI"}],
                "creators": [],
                "titles": [],
                "publisher": None,
                "container": {},
                "publicationYear": None,
                "subjects": [],
                "contributors": [],
                "dates": [],
                "language": None,
                "types": {},
                "relatedIdentifiers": [],
                "sizes": [],
                "formats": [],
                "version": None,
                "rightsList": [],
                "descriptions": [],
                "geoLocations": [],
                "fundingReferences": [],
                "xml": None,
                "url": None,
                "contentUrl": None,
                "metadataVersion": 1,
                "schemaVersion": "http://datacite.org/schema/kernel-4",
                "source": None,
                "isActive": None,
                "state": "draft",
                "reason": None,
                "created": str(datetime.utcnow()),
                "registered": None,
                "updated": str(datetime.utcnow()),
            },
            "relationships": {
                "client": {"data": {"id": "datacite.datacite", "type": "clients"}},
                "media": {"data": []},
            },
        },
        "included": [
            {
                "id": "mockcite.mockcite",
                "type": "clients",
                "attributes": {
                    "name": "MockCite",
                    "symbol": "MOCKCITE.MOCKCITE",
                    "year": 2021,
                    "contactName": "MockCite",
                    "contactEmail": "support@mock_cite.org",
                    "description": None,
                    "domains": "*",
                    "url": None,
                    "created": "2010-01-01 12:00:00.000",
                    "updated": str(datetime.utcnow()),
                    "isActive": True,
                    "hasPassword": True,
                },
                "relationships": {
                    "provider": {"data": {"id": "mockcite", "type": "providers"}},
                    "prefixes": {"data": [{"id": "10.xxxx", "type": "prefixes"}]},
                },
            }
        ],
    }

    if "doi" in attributes or "prefix" in attributes:
        logging.info(data)
        return web.json_response(data)
    else:
        reason = "Provided payload include faulty attributes."
        logging.info(reason)
        raise web.HTTPBadRequest(reason=reason)


def init() -> web.Application:
    """Start server."""
    app = web.Application()
    app.router.add_post("/dois", dois)
    return app


if __name__ == "__main__":
    web.run_app(init(), port=8001)
