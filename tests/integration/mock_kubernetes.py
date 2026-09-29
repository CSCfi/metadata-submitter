#!/usr/bin/env python3
"""A mock Kubernetes API server.

Used for testing Kubernetes authentication in OpenBao, which asks the cluster whether
a token is valid by calling `POST /apis/authentication.k8s.io/v1/tokenreviews`.

Only Kubernetes is mocked. The OpenBao service is real.
"""

import base64
import json
import logging
import ssl
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = 8443
KEYS = Path("/keys")

TOKEN_REVIEW_PATH = "/apis/authentication.k8s.io/v1/tokenreviews"

LOG = logging.getLogger("mock_kubernetes")


def _claims(token: str) -> dict[str, object]:
    """Read the claims of a JSON web token without verifying it."""

    try:
        payload = token.split(".")[1]
        claims: dict[str, object] = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return claims
    except Exception:
        return {}


class Handler(BaseHTTPRequestHandler):
    """Answers the token review endpoint."""

    def do_POST(self) -> None:  # noqa: N802
        """Review the presented token, authenticating whoever it says it is."""

        if self.path != TOKEN_REVIEW_PATH:
            self._respond(404, {"message": f"unknown path {self.path}"})
            return

        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        spec = body.get("spec", {})
        claims = _claims(spec.get("token", ""))
        subject = claims.get("sub")

        if not isinstance(subject, str):
            self._respond(200, {"status": {"authenticated": False, "error": "the token names no subject"}})
            return

        # OpenBao checks the identity it gets back against the one the token claims,
        # so the uid has to be the service account's rather than anything else.
        service_account = claims.get("kubernetes.io", {})
        namespace = service_account.get("namespace", "") if isinstance(service_account, dict) else ""
        uid = ""
        if isinstance(service_account, dict):
            account = service_account.get("serviceaccount", {})
            uid = account.get("uid", "") if isinstance(account, dict) else ""

        LOG.info("Authenticated '%s'.", subject)
        self._respond(
            200,
            {
                "apiVersion": "authentication.k8s.io/v1",
                "kind": "TokenReview",
                "status": {
                    "authenticated": True,
                    # The audiences the token is confirmed for. OpenBao refuses a
                    # login unless the ones it asked about come back.
                    "audiences": spec.get("audiences") or claims.get("aud") or [],
                    "user": {
                        "username": subject,
                        "uid": uid,
                        "groups": [
                            "system:serviceaccounts",
                            f"system:serviceaccounts:{namespace}",
                            "system:authenticated",
                        ],
                    },
                },
            },
        )

    def _respond(self, status: int, body: dict[str, object]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Log through the module logger rather than to stderr."""

        LOG.debug(format, *args)


def main() -> None:
    """Serve the token review endpoint over TLS."""

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(KEYS / "mock_kubernetes.crt", KEYS / "mock_kubernetes_private.txt")

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)

    LOG.info("Serving %s on port %d.", TOKEN_REVIEW_PATH, PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
