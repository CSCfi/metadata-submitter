"""Routing setup for aiohttp server"""

from metadata_backend.views import submit


def setup_routes(server):
    """
    Setup routes for views from views.py

    :param server: aiohttp web application instance
    """
    server.router.add_post('/submit', submit)
