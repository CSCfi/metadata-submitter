"""Handle HTTP methods for server."""
import mimetypes
from pathlib import Path

from aiohttp.web import Request, Response

from ...helpers.logger import LOG


class StaticHandler:
    """Handler for static routes, mostly frontend and 404."""

    def __init__(self, frontend_static_files: Path) -> None:
        """Initialize path to frontend static files folder."""
        self.path = frontend_static_files

    async def frontend(self, req: Request) -> Response:
        """Serve requests related to frontend SPA.

        :param req: GET request
        :returns: Response containing frontpage static file
        """
        serve_path = self.path.joinpath("./" + req.path)

        if not serve_path.exists() or not serve_path.is_file():
            LOG.debug(f"{serve_path} was not found or is not a file - serving index.html")
            serve_path = self.path.joinpath("./index.html")

        LOG.debug(f"Serve Frontend SPA {req.path} by {serve_path}.")

        mime_type = mimetypes.guess_type(serve_path.as_posix())

        return Response(body=serve_path.read_bytes(), content_type=(mime_type[0] or "text/html"))

    def setup_static(self) -> Path:
        """Set path for static js files and correct return mimetypes.

        :returns: Path to static js files folder
        """
        mimetypes.init()
        mimetypes.types_map[".js"] = "application/javascript"
        mimetypes.types_map[".js.map"] = "application/json"
        mimetypes.types_map[".svg"] = "image/svg+xml"
        mimetypes.types_map[".css"] = "text/css"
        mimetypes.types_map[".css.map"] = "application/json"
        LOG.debug("static paths for SPA set.")
        return self.path / "static"
