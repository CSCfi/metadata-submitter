"""Functions shared between handlers."""
from typing import List, Tuple, cast

from aiohttp import BodyPartReader, web
from aiohttp.web import Request

from ...conf.conf import schema_types
from ...helpers.logger import LOG


async def extract_xml_upload(req: Request, extract_one: bool = False) -> List[Tuple[str, str]]:
    """Extract submitted xml-file(s) from multi-part request.

    Files are sorted to spesific order by their schema priorities (e.g.
    submission should be processed before study).

    :param req: POST request containing "multipart/form-data" upload
    :raises: HTTPBadRequest if request is not valid for multipart or multiple files sent. HTTPNotFound if
    schema was not found.
    :returns: content and schema type for each uploaded file, sorted by schema
    type.
    """
    files: List[Tuple[str, str]] = []
    try:
        reader = await req.multipart()
    except AssertionError:
        reason = "Request does not have valid multipart/form content"
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)
    while True:
        part = await reader.next()
        # Following is probably error in aiohttp type hints, fixing so
        # mypy doesn't complain about it. No runtime consequences.
        part = cast(BodyPartReader, part)
        if not part:
            break
        if extract_one and files:
            reason = "Only one file can be sent to this endpoint at a time."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if part.name:
            schema_type = part.name.lower()
            if schema_type not in schema_types:
                reason = f"Specified schema {schema_type} was not found."
                LOG.error(reason)
                raise web.HTTPNotFound(reason=reason)
            data = []
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                data.append(chunk)
            xml_content = "".join(x.decode("UTF-8") for x in data)
            files.append((xml_content, schema_type))
            LOG.debug(f"processed file in {schema_type}")
    return sorted(files, key=lambda x: schema_types[x[1]]["priority"])
