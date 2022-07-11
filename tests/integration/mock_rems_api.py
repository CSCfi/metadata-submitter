"""Mock aiohttp.web server for REMS API calls."""

import logging
from json import JSONDecodeError
from os import getenv

import ujson
from aiohttp import web

FORMAT = "[%(asctime)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

LOG = logging.getLogger("server")
LOG.setLevel(getenv("LOG_LEVEL", "DEBUG"))

handlers = {
    "user_id_1": {"name": "test_user", "email": "test.user@example.org"},
    "user_id_2": {"name": "test_user_2", "email": "test.user.2@example.org"},
}
forms = {
    1: {"internal-name": "Base form", "external-title": {"en": "Base form"}},
    2: {"internal-name": "Test Form", "external-title": {"en": "Test Application"}},
}
organizations = {
    "CSC": {
        "short-name": {"en": "Another organization"},
        "name": {"en": "Another organization"},
        "handlers": ["user_id_2", "user_id_1"],
        "workflows": [1],
        "licenses": [1],
        "resources": {},
        "catalogue-items": {},
    },
    "testorg": {
        "short-name": {"en": "Test Organization"},
        "name": {"en": "Test Organization"},
        "workflows": [3],
        "licenses": [2],
        "resources": {},
        "catalogue-items": {},
    },
}
workflows = {
    1: {
        "id": 1,
        "title": "another_org workflow 1",
        "organization": {
            "organization/id": "CSC",
            "organization/short-name": organizations["CSC"]["short-name"],
            "organization/name": organizations["CSC"]["name"],
        },
        "workflow": {
            "type": "workflow/default",
            "handlers": ["user_id_1", "user_id_2"],
            "forms": [1],
        },
        "licenses": [],
        "enabled": True,
        "archived": False,
    },
    3: {
        "id": 3,
        "title": "Test Workflow",
        "organization": {
            "organization/id": "testorg",
            "organization/short-name": organizations["testorg"]["short-name"],
            "organization/name": organizations["testorg"]["name"],
        },
        "workflow": {
            "type": "workflow/default",
            "handlers": ["user_id_1"],
            "forms": [2],
        },
        "licenses": [],
        "enabled": True,
        "archived": True,
    },
}
licenses = {
    1: {
        "id": 1,
        "licensetype": "link",
        "organization": {
            "organization/id": "CSC",
            "organization/short-name": organizations["CSC"]["short-name"],
            "organization/name": organizations["CSC"]["name"],
        },
        "localizations": {
            "fi": {
                "title": "Nimeä 4.0 Kansainvälinen (CC BY 4.0)",
                "textcontent": "https://creativecommons.org/licenses/by/4.0/deed.fi",
                "attachment-id": None,
            },
            "en": {
                "title": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
                "textcontent": "https://creativecommons.org/licenses/by/4.0/",
                "attachment-id": None,
            },
        },
        "enabled": True,
        "archived": False,
    },
    2: {
        "id": 2,
        "licensetype": "text",
        "organization": {
            "organization/id": "testorg",
            "organization/short-name": organizations["testorg"]["short-name"],
            "organization/name": organizations["testorg"]["name"],
        },
        "localizations": {
            "en": {"title": "Test License", "textcontent": "Everything is prohibited!", "attachment-id": None}
        },
        "enabled": True,
        "archived": False,
    },
}
resource_id = 0
catalogue_id = 0
catalogue = {}


def make_handlers(user_ids: list):
    """Make handler into response format."""
    return [{"userid": user_id, **handlers[user_id]} for user_id in user_ids]


def make_forms(form_ids: list):
    """Make form into response format."""
    return [
        {
            "form/id": form_id,
            "form/internal-name": forms[form_id]["internal-name"],
            "form/external-title": forms[form_id]["external-title"],
        }
        for form_id in form_ids
    ]


def make_workflow_response():
    """Convert organization into workflow response."""
    response = []
    for oid, org in organizations.items():
        for wid in org["workflows"]:
            workflow = workflows[wid]
            response.append(
                {
                    "id": wid,
                    "title": workflow["title"],
                    "organization": {
                        "organization/id": oid,
                        "organization/short-name": org["short-name"],
                        "organization/name": org["name"],
                    },
                    "workflow": {
                        "type": workflow["workflow"]["type"],
                        "handlers": make_handlers(workflow["workflow"]["handlers"]),
                        "forms": make_forms(workflow["workflow"]["forms"]),
                    },
                    "licenses": workflow["licenses"],
                    "enabled": workflow["enabled"],
                    "archived": workflow["archived"],
                }
            )
    return response


def make_license_response():
    """Convert organization into workflow response."""
    response = []
    for oid, org in organizations.items():
        for lid in org["licenses"]:
            license = licenses[lid]
            response.append(
                {
                    "id": lid,
                    "licensetype": license["licensetype"],
                    "organization": {
                        "organization/id": oid,
                        "organization/short-name": org["short-name"],
                        "organization/name": org["name"],
                    },
                    "localizations": license["localizations"],
                    "enabled": license["enabled"],
                    "archived": license["archived"],
                }
            )
    return response


async def get_workflows(_: web.Request) -> web.Response:
    """REMS workflows."""
    return web.json_response(data=make_workflow_response())


async def get_workflow(request: web.Request) -> web.Response:
    """REMS workflow."""
    workflow_id = int(request.match_info["workflow_id"])
    workflow = workflows[workflow_id]
    try:
        return web.json_response(
            data={
                "id": workflow_id,
                "title": workflow["title"],
                "organization": workflow["organization"],
                "workflow": {
                    "type": workflow["workflow"]["type"],
                    "handlers": make_handlers(workflow["workflow"]["handlers"]),
                    "forms": make_forms(workflow["workflow"]["forms"]),
                },
                "licenses": workflow["licenses"],
                "enabled": workflow["enabled"],
                "archived": workflow["archived"],
            }
        )
    except KeyError:
        raise web.HTTPNotFound(reason=f"Workflow with id '{workflow_id}' was not found.")


async def get_licenses(_: web.Request) -> web.Response:
    """REMS licenses."""
    return web.json_response(data=make_license_response())


async def get_license(request: web.Request) -> web.Response:
    """REMS license."""
    license_id = int(request.match_info["license_id"])
    try:
        return web.json_response(data=licenses[license_id])
    except KeyError:
        raise web.HTTPNotFound(reason=f"License with id '{license_id}' was not found.")


async def get_application(request: web.Request) -> web.Response:
    """REMS application."""
    try:
        items = int(request.query["items"])
        item = catalogue[items]
    except (KeyError, TypeError) as e:
        LOG.exception(e)
        LOG.debug(request)
        return web.HTTPNotFound(reason="Catalogue item was not found")
    return web.json_response(data=item)


async def post_resource(request: web.Request) -> web.Response:
    """REMS create resource and return id."""
    global resource_id
    try:

        resource = await request.json()
        oid = resource["organization"]["organization/id"]
        if oid not in organizations:
            raise web.HTTPNotFound(reason=f"Organization '{oid}' was not found.")
        for lic in resource["licenses"]:
            if lic not in organizations[oid]["licenses"]:
                raise web.HTTPNotFound(reason=f"License '{lic}' was not found in organization '{oid}'.")
        resource_id += 1
        organizations[oid]["resources"][resource_id] = {
            "resid": resource["resid"],  # DOI
            "licenses": resource["licenses"],
        }
    except (KeyError, TypeError, JSONDecodeError) as e:
        LOG.exception(e)
        raise web.HTTPBadRequest(text=ujson.dumps({"errors": ["check the logs ^^"]}))

    return web.json_response(data={"success": True, "id": resource_id})


async def post_catalogue_item(request: web.Request) -> web.Response:
    """REMS create resource and return id."""
    global catalogue, catalogue_id
    try:
        catalogue_request = await request.json()
        catalogue_id += 1
        oid = catalogue_request["organization"]["organization/id"]
        resid = catalogue_request["resid"]
        wfid = catalogue_request["wfid"]
        form = catalogue_request["form"]
        if form and form not in forms:
            raise web.HTTPNotFound(reason=f"Form '{form}' was not found.")
        if resource_id not in organizations[oid]["resources"]:
            raise web.HTTPNotFound(reason=f"Resource '{resid}' was not found in organization '{oid}'.")
        if wfid not in organizations[oid]["workflows"]:
            raise web.HTTPNotFound(reason=f"Workflow '{wfid}' was not found in organization '{oid}'.")
        catalogue_item = {
            "form": form,
            "resid": resid,
            "wfid": wfid,
            "localizations": catalogue_request["localizations"],
            "enabled": catalogue_request["enabled"],
            "archived": catalogue_request["archived"],
        }
        organizations[oid]["catalogue-items"][catalogue_id] = catalogue_item
        catalogue[catalogue_id] = catalogue_item
    except (KeyError, TypeError, JSONDecodeError) as e:
        LOG.exception(e)
        LOG.debug(await request.text())
        raise web.HTTPBadRequest(text=ujson.dumps({"errors": ["check the logs ^^"]}))

    return web.json_response(data={"success": True, "id": catalogue_id})


async def init() -> web.Application:
    """Start server."""
    app = web.Application()
    app.router.add_get("/api/workflows", get_workflows)
    app.router.add_get("/api/workflows/{workflow_id}", get_workflow)
    app.router.add_get("/api/licenses", get_licenses)
    app.router.add_get("/api/licenses/{license_id}", get_license)
    app.router.add_post("/api/resources/create", post_resource)
    app.router.add_post("/api/catalogue-items/create", post_catalogue_item)
    app.router.add_get("/application", get_application)
    return app


if __name__ == "__main__":
    web.run_app(init(), port=8003)
