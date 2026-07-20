"""
MI AI verified-link guard.

Prevents guessed, malformed and dead URLs from being displayed as working
links. Public URLs are checked before they are returned to the frontend.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import requests


LOGGER = logging.getLogger(__name__)

URL_PATTERN = re.compile(
    r"""(?ix)
    https?://
    [^\s<>"'`)\]}]+
    """
)

TRAILING_PUNCTUATION = ".,;:!?)]}>"

BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "0.0.0.0",
    "127.0.0.1",
    "::1",
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/150.0.0.0 Safari/537.36 "
        "MI-AI-LinkVerifier/1.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/json,"
        "text/plain;q=0.9,*/*;q=0.7"
    ),
    "Accept-Language": "en-US,en;q=0.9,si;q=0.8,ta;q=0.7",
}

INVALID_LINK_MESSAGE = (
    "[This link could not be verified, so MI AI removed it.]"
)


def _clean_url(url: str) -> str:
    return str(url or "").strip().rstrip(TRAILING_PUNCTUATION)


def _host_is_public(hostname: str) -> bool:
    hostname = str(hostname or "").strip().lower().rstrip(".")

    if not hostname:
        return False

    if hostname in BLOCKED_HOSTS:
        return False

    if hostname.endswith((".local", ".internal", ".localhost")):
        return False

    try:
        ip = ipaddress.ip_address(hostname)

        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )

    except ValueError:
        pass

    try:
        addresses = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return False

    if not addresses:
        return False

    for address in addresses:
        candidate = address[4][0]

        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            return False

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False

    return True


def _looks_like_real_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    if not parsed.netloc:
        return False

    hostname = parsed.hostname or ""

    if "." not in hostname and hostname != "localhost":
        return False

    return _host_is_public(hostname)


@lru_cache(maxsize=512)
def verify_public_url(url: str) -> bool:
    """
    Return True only when the public URL responds successfully.

    Redirects are followed. A final HTTP status between 200 and 399 is
    considered reachable.
    """

    url = _clean_url(url)

    if not _looks_like_real_http_url(url):
        return False

    try:
        response = requests.head(
            url,
            timeout=7,
            allow_redirects=True,
            headers=REQUEST_HEADERS,
        )

        if 200 <= response.status_code < 400:
            final_url = _clean_url(response.url)

            return _looks_like_real_http_url(final_url)

        if response.status_code not in {
            403,
            405,
            429,
        }:
            return False

    except requests.RequestException:
        pass

    try:
        response = requests.get(
            url,
            timeout=10,
            allow_redirects=True,
            stream=True,
            headers={
                **REQUEST_HEADERS,
                "Range": "bytes=0-4095",
            },
        )

        valid = 200 <= response.status_code < 400

        if valid:
            valid = _looks_like_real_http_url(
                _clean_url(response.url)
            )

        response.close()
        return valid

    except requests.RequestException as exc:
        LOGGER.info(
            "MI AI link verification failed for %s: %s",
            url,
            exc,
        )
        return False


def extract_urls(text: str) -> list[str]:
    if not isinstance(text, str):
        return []

    found: list[str] = []

    for match in URL_PATTERN.finditer(text):
        url = _clean_url(match.group(0))

        if url and url not in found:
            found.append(url)

    return found


def sanitize_text_links(text: str) -> str:
    """
    Replace dead or unverifiable URLs while preserving verified URLs.
    """

    if not isinstance(text, str) or "http" not in text.lower():
        return text

    verification_cache: dict[str, bool] = {}

    def replace_match(match: re.Match[str]) -> str:
        original = match.group(0)
        url = _clean_url(original)
        suffix = original[len(url):]

        if url not in verification_cache:
            verification_cache[url] = verify_public_url(url)

        if verification_cache[url]:
            return url + suffix

        return INVALID_LINK_MESSAGE + suffix

    return URL_PATTERN.sub(replace_match, text)


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text_links(value)

    if isinstance(value, list):
        return [
            sanitize_json_value(item)
            for item in value
        ]

    if isinstance(value, dict):
        return {
            key: sanitize_json_value(item)
            for key, item in value.items()
        }

    return value


def sanitize_flask_json_response(response: Any) -> Any:
    """
    Sanitize Flask JSON responses without altering non-JSON assets.
    """

    try:
        content_type = str(
            response.headers.get("Content-Type", "")
        ).lower()
    except Exception:
        return response

    if "application/json" not in content_type:
        return response

    try:
        raw_data = response.get_data(as_text=True)

        if not raw_data or "http" not in raw_data.lower():
            return response

        payload = json.loads(raw_data)
        cleaned = sanitize_json_value(payload)

        if cleaned == payload:
            return response

        encoded = json.dumps(
            cleaned,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        response.set_data(
            encoded.encode("utf-8")
        )

        response.headers["Content-Type"] = (
            "application/json; charset=utf-8"
        )
        response.headers["Content-Length"] = str(
            len(response.get_data())
        )

        return response

    except Exception as exc:
        LOGGER.warning(
            "MI AI JSON link sanitization failed: %s",
            exc,
        )
        return response


def verified_source_lines(
    results: list[dict[str, Any]],
) -> list[str]:
    """
    Build source lines only from URLs that really respond.
    """

    source_lines: list[str] = []

    for result in results or []:
        if not isinstance(result, dict):
            continue

        title = str(
            result.get("title") or "Source"
        ).strip()

        url = _clean_url(
            str(result.get("url") or "")
        )

        if not url:
            continue

        if verify_public_url(url):
            source_lines.append(
                f"- {title}: {url}"
            )

    return source_lines


__all__ = [
    "extract_urls",
    "verify_public_url",
    "sanitize_text_links",
    "sanitize_json_value",
    "sanitize_flask_json_response",
    "verified_source_lines",
]