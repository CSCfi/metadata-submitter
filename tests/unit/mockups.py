"""Mock-up classes and functions for testing."""

import yarl


class Mock_Request:
    """
    Mock-up class for the aiohttp.web.Request.

    It contains the dictionary
    representation of the requests that will be passed to the functions.
    (the actual request eing a MutableMapping instance)
    """

    def __init__(self):
        """Initialize Mock request."""
        # Application mutable mapping represented by a dictionary
        self.app = {}
        self.headers = {}
        self.cookies = {}
        self.query = {}
        self.remote = "127.0.0.1"
        self.url = yarl.URL("http://localhost:8080")
        self.post_data = {}

    def set_headers(self, headers):
        """
        Set mock request headers.

        Params:
            headers: dict
        """
        for i in headers.keys():
            self.headers[i] = headers[i]

    def set_cookies(self, cookies):
        """
        Set mock request cookies.

        Params:
            cookies: dict
        """
        for i in cookies.keys():
            self.cookies[i] = cookies[i]

    def set_post(self, data):
        """Set post data."""
        self.post_data = data

    async def post(self):
        """Return post data."""
        return self.post_data
