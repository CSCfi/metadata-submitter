"""Mock aiohttp.web server for Metax API calls."""

import json
import logging
import os
from datetime import datetime
from typing import Dict
from uuid import uuid4

import ujson
from aiohttp import web

FORMAT = "[%(asctime)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

LOG = logging.getLogger("server")
LOG.setLevel(os.getenv("LOG_LEVEL", "DEBUG"))

# Example error responds from Metax
# {
#     "detail": [
#         "Specified organization object does not have a name. If you are using an org identifier from reference data, \
# then the name will be populated automatically. If your org identifier is not from reference data, \
# you must provide the organization name. The object that caused the error: {'@type': 'Organization'}"
#     ],
#     "error_identifier": "2022-01-21T10:27:02-02ad2e36",
# }
# {
#     "detail": "[ErrorDetail(string=\"'creator' is a required property., code='invalid')]",
#     "error_identifier": "2022-01-21T10:27:02-02ad2e36",
# }

# mimic db for saved datasets, volatile!!
drafts = {}
published = {}


async def get_dataset(req: web.Request) -> web.Response:
    """Mock endpoint for retrieving Metax dataset.

    :params req: HTTP request with data for Metax dataset
    :return: HTTP response with mocked Metax dataset data
    """
    metax_id = req.match_info["metax_id"]
    LOG.info(f"Retrieving Metax dataset {metax_id}")
    if not metax_id:
        LOG.error("Query params missing Metax ID.")
        raise web.HTTPBadRequest(
            reason={
                "detail": ["Query params missing Metax ID."],
                "error_identifier": str(datetime.now()),
            }
        )
    datasets = list(drafts.keys()) + list(published.keys())
    if metax_id not in datasets:
        LOG.error(f"No dataset found with identifier {metax_id}")
        raise web.HTTPNotFound(reason={"detail": "Not found."})
    try:
        content = drafts[metax_id]
    except KeyError:
        content = published[metax_id]

    LOG.debug(f"Found {content['state']} dataset {content['identifier']} with data: {content}")
    return web.Response(
        body=ujson.dumps(content, escape_forward_slashes=False),
        status=200,
        content_type="application/json",
    )


async def post_dataset(req: web.Request) -> web.Response:
    """Mock endpoint for creating draft Metax dataset.

    :params req: HTTP request with data for Metax dataset
    :return: HTTP response with mocked Metax dataset data
    """
    LOG.info("Creating Metax dataset")
    try:
        content = await req.json()
    except json.decoder.JSONDecodeError as e:
        reason = f"JSON is not correctly formatted. See: {e}"
        LOG.error(f"Error while validating payload: {reason}")
        raise web.HTTPBadRequest(
            reason={
                "detail": reason,
                "error_identifier": str(datetime.now()),
            }
        )
    validate_data(content)

    content["research_dataset"]["preferred_identifier"] = f"draft:{str(uuid4())}"
    metax_id = str(uuid4())
    metax_additions = {
        "identifier": metax_id,
        "preservation_state": 0,
        "state": "draft",
        "use_doi_for_published": False,
        "cumulative_state": 0,
        "api_meta": {"version": 2},
        "date_created": f"{datetime.now()}",
        "service_created": "sd",
        "removed": False,
    }
    resp_data = dict(content, **metax_additions)
    drafts[metax_id] = resp_data
    LOG.info(f'Created Metax dataset with identifier {resp_data["identifier"]}')
    return web.Response(
        body=ujson.dumps(resp_data, escape_forward_slashes=False),
        status=201,
        content_type="application/json",
    )


async def update_dataset(req: web.Request) -> web.Response:
    """Mock endpoint for updating Metax dataset.

    :params req: HTTP request with data for Metax dataset
    :return: HTTP response with mocked Metax dataset data
    """
    LOG.info("Updating Metax dataset")
    metax_id = req.match_info["metax_id"]
    if not metax_id:
        raise web.HTTPBadRequest(
            reason={
                "detail": ["Query params missing Metax ID."],
                "error_identifier": str(datetime.now()),
            }
        )
    if metax_id not in drafts.keys():
        LOG.error(f"No dataset found with identifier {metax_id}")
        raise web.HTTPNotFound(reason={"detail": "Not found."})

    try:
        content = await req.json()
    except json.decoder.JSONDecodeError as e:
        reason = f"JSON is not correctly formatted. See: {e}"
        LOG.error(f"Error while validating payload: {reason}")
        raise web.HTTPBadRequest(
            reason={
                "detail": reason,
                "error_identifier": str(datetime.now()),
            }
        )
    validate_data(content)

    for key, value in content.items():
        drafts[metax_id][key] = value

    drafts[metax_id]["date_modified"] = str(datetime.now())

    LOG.info(f'Updated Metax dataset with identifier {drafts[metax_id]["identifier"]}')
    return web.Response(
        body=ujson.dumps(drafts[metax_id], escape_forward_slashes=False),
        status=200,
        content_type="application/json",
    )


async def patch_datasets(req: web.Request) -> web.Response:
    """Mock endpoint for patching bulk Metax datasets.

    :params req: HTTP request with data for Metax datasets
    :return: HTTP response with IDs of patched Metax datasets and possible errors
    """
    LOG.info("Patching Metax datasets")

    success = []
    failed = []
    try:
        content = await req.json()
    except json.decoder.JSONDecodeError as e:
        reason = f"JSON is not correctly formatted. See: {e}"
        LOG.error(f"Error while validating payload: {reason}")
        raise web.HTTPBadRequest(
            reason={
                "detail": reason,
                "error_identifier": str(datetime.now()),
            }
        )
    for dataset in content:
        try:
            metax_id = dataset["identifier"]
            _ = dataset["research_dataset"]["preferred_identifier"]
        except KeyError:
            raise web.HTTPBadRequest(
                reason={
                    "detail": "Dataset is missing required identifiers",
                    "error_identifier": str(datetime.now()),
                }
            )
        if metax_id not in drafts.keys():
            reason = f"No dataset found with identifier {metax_id}"
            LOG.error(reason)
            failed.append(
                {
                    "object": {
                        "detail": reason,
                        "error_identifier": str(datetime.now()),
                    }
                }
            )
            continue

        for key, value in dataset.items():
            drafts[metax_id][key] = value

        drafts[metax_id]["date_modified"] = str(datetime.now())
        success.append({"object": drafts[metax_id]})

    LOG.info("Metax datasets patched")
    body = {"success": success, "failed": failed}
    return web.Response(
        body=ujson.dumps(body, escape_forward_slashes=False),
        status=200,
        content_type="application/json",
    )


async def patch_dataset(req: web.Request) -> web.Response:
    """Mock endpoint for patching Metax dataset.

    :params req: HTTP request with data for Metax dataset
    :return: HTTP response with mocked Metax dataset data
    """
    LOG.info("Patching Metax dataset")
    metax_id = req.match_info["metax_id"]
    if not metax_id:
        raise web.HTTPBadRequest(
            reason={
                "detail": ["Query params missing Metax ID."],
                "error_identifier": str(datetime.now()),
            }
        )
    if metax_id not in drafts.keys():
        LOG.error(f"No dataset found with identifier {metax_id}")
        raise web.HTTPNotFound(reason={"detail": "Not found."})

    try:
        content = await req.json()
    except json.decoder.JSONDecodeError as e:
        reason = f"JSON is not correctly formatted. See: {e}"
        LOG.error(f"Error while validating payload: {reason}")
        raise web.HTTPBadRequest(
            reason={
                "detail": reason,
                "error_identifier": str(datetime.now()),
            }
        )
    for key, value in content.items():
        drafts[metax_id][key] = value

    drafts[metax_id]["date_modified"] = str(datetime.now())

    LOG.info(f'Updated Metax dataset with identifier {drafts[metax_id]["identifier"]}')
    return web.Response(
        body=ujson.dumps(drafts[metax_id], escape_forward_slashes=False),
        status=200,
        content_type="application/json",
    )


async def publish_dataset(req: web.Request) -> web.Response:
    """Mock endpoint for publishing Metax dataset.

    :params req: HTTP request with data for Metax dataset
    :return: HTTP response with mocked Metax dataset data
    """
    LOG.info("Publishing Metax dataset")
    metax_id = req.query.get("identifier", None)
    if not metax_id:
        LOG.error("Query params missing Metax ID.")
        raise web.HTTPBadRequest(
            reason={
                "detail": ["Query params missing Metax ID."],
                "error_identifier": str(datetime.now()),
            }
        )
    if metax_id in published:
        LOG.error(f"Dataset {metax_id} is already published.")
        reason = {"detail": ["Dataset is already published."], "error_identifier": str(datetime.now())}
        raise web.HTTPBadRequest(reason=reason)
    if metax_id not in drafts.keys():
        LOG.error(f"No dataset found with identifier {metax_id}")
        raise web.HTTPNotFound(reason={"detail": "Not found."})

    data = drafts[metax_id]
    validate_data(data, draft=True)
    published[metax_id] = data
    del drafts[metax_id]
    published[metax_id]["state"] = "published"
    published[metax_id]["modified"] = str(datetime.now())
    LOG.info(f"Published Metax dataset with identifier {metax_id}")
    return web.Response(
        body=ujson.dumps(
            {"preferred_identifier": data["research_dataset"]["preferred_identifier"]}, escape_forward_slashes=False
        ),
        status=200,
        content_type="application/json",
    )


async def delete_dataset(req: web.Request) -> web.Response:
    """Mock endpoint for deleting Metax dataset.

    :params req: HTTP request with Metax dataset id
    :return: HTTP response with HTTP status
    """
    metax_id = req.match_info["metax_id"]
    LOG.debug(f"Deleting Metax dataset {metax_id}")

    if not metax_id:
        raise web.HTTPBadRequest(
            reason={
                "detail": ["Query params missing Metax ID."],
                "error_identifier": str(datetime.now()),
            }
        )
    if metax_id not in drafts.keys():
        raise web.HTTPNotFound(reason={"detail": "Not found."})
    else:
        del drafts[metax_id]
    LOG.info(f"Deleted Metax dataset with identifier {metax_id}")
    return web.HTTPNoContent()


def validate_data(data: Dict, draft=True) -> None:
    """Check for required fields in dataset.

    :param data: Metax data to be validated
    :param draft: Indicator if dataset needs to be validated as draft or not; default true
    """
    LOG.info("Validating payload")

    required = ["data_catalog", "metadata_provider_org", "metadata_provider_user", "research_dataset"]
    rd_required = ["title", "description", "preferred_identifier", "access_rights", "publisher"]

    if not draft:
        rd_required = rd_required + ["creator"]
    if not all(key in data.keys() for key in required):
        reason = {"detail": [f"Dataset did not include all required fields: {', '.join(required)}."]}
        reason = json.dumps(reason)
        LOG.error(f"Error while validating payload: {reason}")
        raise web.HTTPBadRequest(reason=reason, content_type="application/json")
    if not all(key in data["research_dataset"].keys() for key in rd_required):
        reason = {"detail": [f"Research dataset did not include all required fields: {', '.join(rd_required)}."]}
        reason = json.dumps(reason)
        LOG.error(f"Error while validating payload: {reason}")
        raise web.HTTPBadRequest(reason=reason, content_type="application/json")


def init() -> web.Application:
    """Start server."""
    app = web.Application()
    api_routes = [
        web.post("/rest/v2/datasets", post_dataset),
        web.put("/rest/v2/datasets/{metax_id}", update_dataset),
        web.delete("/rest/v2/datasets/{metax_id}", delete_dataset),
        web.post("/rpc/v2/datasets/publish_dataset", publish_dataset),
        web.get("/rest/v2/datasets/{metax_id}", get_dataset),
        web.patch("/rest/v2/datasets", patch_datasets),
        web.patch("/rest/v2/datasets/{metax_id}", patch_dataset),
    ]
    app.router.add_routes(api_routes)
    LOG.info("Metax mock API started")
    return app


if __name__ == "__main__":
    web.run_app(init(), port=8002)
