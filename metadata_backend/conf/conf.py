"""Application configuration."""

from pathlib import Path

API_PREFIX = "/v1"

# 2.1) Path to swagger HTML file
swagger_static_path = Path(__file__).parent.parent / "swagger" / "index.html"

DEPLOYMENT_CSC = "CSC"
DEPLOYMENT_NBIS = "NBIS"
