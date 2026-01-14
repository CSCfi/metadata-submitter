"""Handle HTTP methods for server."""

import mimetypes
from pathlib import Path

from aiohttp.typedefs import Handler
from aiohttp.web import Request, Response

from ...helpers.logger import LOG


def html_handler_factory(html_static_path: Path) -> Handler:
    """Create a handler that returns a html file for a route.

    :returns: html file handler
    """

    async def html_handler(_: Request) -> Response:
        serve_path = html_static_path
        if html_static_path.exists() and not html_static_path.is_file():
            LOG.debug("%r was not found or is not a file - serving index.html", html_static_path)
            serve_path = html_static_path.joinpath("./index.html")

        mime_type = mimetypes.guess_type(serve_path.as_posix())

        return Response(body=serve_path.read_bytes(), content_type=(mime_type[0] or "text/html"))

    return html_handler
