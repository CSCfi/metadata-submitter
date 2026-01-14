"""Python-based app configurations.

1) Frontend static files folder
Production version gets frontend SPA from this folder, after it has been built
and inserted here in projects Dockerfile.
"""

from pathlib import Path

API_PREFIX = "/v1"

# 1) Set frontend folder to be inside metadata_backend modules root
frontend_static_files = Path(__file__).parent.parent / "frontend"

# 2.1) Path to swagger HTML file
swagger_static_path = Path(__file__).parent.parent / "swagger" / "index.html"

DEPLOYMENT_CSC = "CSC"
DEPLOYMENT_NBIS = "NBIS"
