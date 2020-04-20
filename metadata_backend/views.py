from aiohttp import web
from metadata_backend.schema_load import SchemaLoader
from metadata_backend.validator import XMLValidator


async def submit(request):
    """Handles submission to server

    :param request: POST request sent
    :raises: HTTP Exceptions with status code 201 or 400
    :returns: JSON response with submitted xml_content or validation error
    reason
    """
    reader = await request.multipart()
    field = await reader.next()
    schema = field.name.lower()
    result = []
    while True:
        chunk = await field.read_chunk()
        if not chunk:
            break
        result.append(chunk)
    xml_content = ''.join(x.decode('UTF-8') for x in result)

    schema_loader = SchemaLoader()
    valid_xml = XMLValidator.validate(xml_content, schema, schema_loader)

    if not valid_xml:
        reason = f"Submitted XML file was not valid against schema {schema}"
        raise web.HTTPBadRequest()
        return web.json_response({'Validation error': reason})

    raise web.HTTPCreated()
    return web.json_response({'content': xml_content})
