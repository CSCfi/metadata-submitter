#!/usr/bin/env python3
"""Helper script for SDS AAI login and storing the access tokens in tests/http/.env."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

AUTH_COOKIE_NAME = "access_token"
OIDC_COOKIE_NAME = "oidc_access_token"

S3_ENDPOINT = "S3_ENDPOINT"
S3_REGION = "S3_REGION"
USER_S3_ACCESS_KEY_ID = "USER_S3_ACCESS_KEY_ID"
USER_S3_SECRET_ACCESS_KEY = "USER_S3_SECRET_ACCESS_KEY"
ACCESS_TOKEN = "ACCESS_TOKEN"
OIDC_ACCESS_TOKEN = "OIDC_ACCESS_TOKEN"

DEFAULT_TIMEOUT_SECONDS = 120
OUTPUT_ENV_PATH = Path("tests/http/.env")


def load_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def resolve_base_url(args_base_url: Optional[str], env_values: dict[str, str]) -> str:
    base_url = args_base_url or env_values.get("BASE_URL")
    if not base_url:
        raise ValueError("Missing BASE_URL.")
    return base_url.rstrip("/")


def wait_for_cookies(context, base_url: str, cookie_names: list[str], timeout_seconds: int) -> dict[str, str]:
    deadline = time.monotonic() + timeout_seconds
    found_cookies: dict[str, str] = {}

    while time.monotonic() < deadline:
        cookies = context.cookies(base_url)
        for cookie in cookies:
            cookie_name = cookie.get("name")
            if cookie_name in cookie_names and cookie_name not in found_cookies:
                found_cookies[cookie_name] = cookie.get("value", "")

        if len(found_cookies) == len(cookie_names):
            return found_cookies
        time.sleep(0.5)

    missing = set(cookie_names) - set(found_cookies.keys())
    raise TimeoutError(f"Timed out waiting for cookies: {missing}")


def main():
    parser = argparse.ArgumentParser(
        description="Open CSC login in a browser and write the resulting access tokens in tests/http/.env."
    )
    parser.add_argument(
        "--base-url",
        help="SD Submit API base URL. Read from base .env file if not provided.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to the base .env file (default: .env).",
    )

    args = parser.parse_args()
    env_path = Path(args.env_file)
    env_values = load_env_file(env_path)
    base_url = resolve_base_url(args.base_url, env_values)

    login_url = f"{base_url}/login"
    print("Opening browser for CSC login...")
    print(f"Login URL: {login_url}")

    try:
        with sync_playwright() as playwright:
            browser = playwright.firefox.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(login_url, wait_until="domcontentloaded")

            print("Complete the login in the browser window.")
            cookies = wait_for_cookies(context, base_url, [AUTH_COOKIE_NAME, OIDC_COOKIE_NAME], DEFAULT_TIMEOUT_SECONDS)
            browser.close()
    except Exception as exc:
        print(f"Error during login: {exc}")
        exit(1)

    env_vars = {
        S3_ENDPOINT: env_values.get(S3_ENDPOINT),
        S3_REGION: env_values.get(S3_REGION),
        "S3_KEY_ID": env_values.get(USER_S3_ACCESS_KEY_ID),
        "S3_SECRET_KEY": env_values.get(USER_S3_SECRET_ACCESS_KEY),
        ACCESS_TOKEN: cookies[AUTH_COOKIE_NAME],
        OIDC_ACCESS_TOKEN: cookies[OIDC_COOKIE_NAME],
    }
    content = "\n".join(f"{key}={value}" for key, value in env_vars.items())
    OUTPUT_ENV_PATH.write_text(f"{content}\n", encoding="utf-8")

    print(f"Saved S3 credentials and access tokens to {OUTPUT_ENV_PATH}.")
    exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
