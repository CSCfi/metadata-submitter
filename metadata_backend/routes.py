"""Routing setup for aiohttp server"""


def setup_routes(server, handler):
    """
    Setup routes for views from views.py

    :param server: aiohttp web application instance
    """
    server.router.add_post('/submit', handler.submit)
