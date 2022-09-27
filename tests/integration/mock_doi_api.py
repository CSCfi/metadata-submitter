"""Mock aiohttp.web server for DOI API calls."""

import collections.abc
import json
import logging
from copy import deepcopy
from datetime import date, datetime
from os import getenv

from aiohttp import web

FORMAT = "[%(asctime)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

LOG = logging.getLogger("server")
LOG.setLevel(getenv("LOG_LEVEL", "INFO"))

BASE_RESPONSE = {
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
            "publicationYear": date.today().year,
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
            "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
            "source": None,
            "isActive": None,
            "state": "draft",
            "reason": None,
            "created": "",
            "registered": None,
            "updated": "",
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
                "year": date.today().year,
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

DATASETS = {}


def update_dict(d, u):
    """Update values in a dictionary with values from another dictionary."""
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update_dict(d.get(k, {}), v)
        else:
            d[k] = v
    return d


async def create(req: web.Request) -> web.Response:
    """DOI draft creation endpoint."""
    try:
        content = await req.json()
    except json.decoder.JSONDecodeError as e:
        reason = f"JSON is not correctly formatted. See: {e}"
        LOG.info(reason)
        raise web.HTTPBadRequest(reason=reason)

    data = deepcopy(BASE_RESPONSE)
    try:
        _doi = content["data"]["attributes"]["doi"]
        data["data"]["id"] = content["data"]["attributes"]["doi"]
        data["data"]["attributes"]["doi"] = _doi
        data["data"]["attributes"]["prefix"] = _doi.split("/")[0]
        data["data"]["attributes"]["suffix"] = _doi.split("/")[1]
        data["data"]["attributes"]["identifiers"] = [
            {"identifier": f"https://mock_doi.org/{content['data']['attributes']['doi']}", "identifierType": "DOI"}
        ]
    except Exception as e:
        reason = f"Provided payload did not include required attributes: {e}"
        LOG.info(reason)
        raise web.HTTPBadRequest(reason=reason)

    data["data"]["attributes"]["created"] = str(datetime.utcnow())
    data["data"]["attributes"]["updated"] = str(datetime.utcnow())
    data["included"][0]["attributes"]["created"] = str(datetime.utcnow())
    data["included"][0]["attributes"]["updated"] = str(datetime.utcnow())
    DATASETS[_doi] = data
    return web.json_response(data, status=201)


async def update(req: web.Request) -> web.Response:
    """DOI update endpoint."""
    try:
        content = await req.json()
        _doi = req.match_info["id"]
    except json.decoder.JSONDecodeError as e:
        reason = f"JSON is not correctly formatted. See: {e}"
        LOG.info(reason)
        raise web.HTTPBadRequest(reason=reason)

    data = DATASETS[_doi]
    data["data"]["attributes"]["updated"] = str(datetime.utcnow())
    data["included"][0]["attributes"]["updated"] = str(datetime.utcnow())
    try:
        data = update_dict(data, content)
    except Exception as e:
        reason = f"Provided payload did not include required attributes: {e}"
        LOG.info(reason)
        raise web.HTTPBadRequest(reason=reason)
    return web.json_response(data, status=200)


async def get(req: web.Request) -> web.Response:
    """DOI get endpoint."""
    try:
        _doi = req.match_info["id"]
    except Exception as e:
        reason = f"No identifier is provided : {e}"
        LOG.info(reason)
        raise web.HTTPBadRequest(reason=reason)

    data = DATASETS[_doi]
    return web.json_response(data, status=200)


async def delete(req: web.Request) -> web.Response:
    """DOI delete endpoint."""
    return web.json_response(status=204)


async def heartbeat(req: web.Request) -> web.Response:
    """DOI heartbeat endpoint."""
    return web.Response(status=200, text="OK")


async def init() -> web.Application:
    """Start server."""
    app = web.Application()
    app.router.add_get("/heartbeat", heartbeat)
    app.router.add_get("/dois/{id:.*}", get)
    app.router.add_post("/dois", create)
    app.router.add_put("/dois/{id:.*}", update)
    app.router.add_delete("/dois/{id:.*}", delete)
    return app


if __name__ == "__main__":
    web.run_app(init(), port=8001)
