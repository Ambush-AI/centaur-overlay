"""Credential-safe Ambush Streams API client for Centaur.

The Centaur sandbox receives only a placeholder from ``secret``. Iron-proxy
injects the real ``AMBUSH_API_KEY`` into requests to ``api.ambush.ai`` at the
network boundary. The client exposes only the stream lifecycle and emission
operations also available through the official Ambush MCP server.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import httpx

try:
    from centaur_sdk import secret as _centaur_secret
except ImportError:  # Local operator use outside a Centaur sandbox.

    def _centaur_secret(name: str, default: str = "") -> str:
        return os.environ.get(name, default)


AMBUSH_API_HOST = "api.ambush.ai"
AMBUSH_API_BASE_URL = f"https://{AMBUSH_API_HOST}/api/v1"
AMBUSH_API_KEY_SECRET = "AMBUSH_API_KEY"
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 50
MAX_CURSOR_LENGTH = 512
MAX_STREAM_NAME_LENGTH = 80
MAX_PROMPT_LENGTH = 10_000


class AmbushApiError(RuntimeError):
    """A structured error returned by the Ambush API."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(
            f"Ambush API request failed ({status_code}, {code}): {message}"
        )


def _required_text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field} is required")
    if len(clean) > maximum:
        raise ValueError(f"{field} must be {maximum} characters or less")
    return clean


def _optional_text(value: str | None, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    return _required_text(value, field, maximum)


def _guid(value: str, field: str = "stream_id") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a UUID string")
    clean = value.strip()
    try:
        return str(UUID(clean))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{field} must be a UUID") from exc


def _page_params(limit: int, cursor: str | None) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if limit < 1 or limit > MAX_PAGE_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_LIMIT}")

    params: dict[str, Any] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = _required_text(cursor, "cursor", MAX_CURSOR_LENGTH)
    return params


def _error_from_response(response: httpx.Response) -> AmbushApiError:
    code = "HTTP_ERROR"
    message = response.reason_phrase or "Ambush API request failed"
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            if isinstance(error.get("code"), str):
                code = error["code"]
            if isinstance(error.get("message"), str):
                message = error["message"]
    return AmbushApiError(response.status_code, code, message)


class AmbushStreamsClient:
    """Stream lifecycle client bound to one operator-configured Ambush account."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or _centaur_secret(AMBUSH_API_KEY_SECRET, "")
        if not self.api_key:
            raise RuntimeError(f"{AMBUSH_API_KEY_SECRET} is required")

        self._http = http_client or httpx.Client(
            base_url=AMBUSH_API_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, params=params, json=json)
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Unable to reach {AMBUSH_API_HOST} ({type(exc).__name__})"
            ) from exc

        if not 200 <= response.status_code < 300:
            raise _error_from_response(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Ambush API returned a non-JSON success response"
            ) from exc
        if not isinstance(payload, dict):
            raise TypeError("Ambush API returned an unexpected JSON response")
        return payload

    def _close(self) -> None:
        self._http.close()

    def whoami(self) -> dict[str, Any]:
        """Verify the configured credential and return its Ambush user identity."""
        return self._request("GET", "/me")

    def list_streams(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List the configured account's streams, newest first."""
        return self._request("GET", "/feeds", params=_page_params(limit, cursor))

    def get_stream(self, stream_id: str) -> dict[str, Any]:
        """Read one stream, its destinations, usage, and recent emissions."""
        return self._request("GET", f"/feeds/{_guid(stream_id)}")

    def create_stream(
        self,
        *,
        prompt: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Create one stream from a focused monitoring prompt."""
        clean_prompt = _required_text(prompt, "prompt", MAX_PROMPT_LENGTH)
        clean_name = _optional_text(name, "name", MAX_STREAM_NAME_LENGTH)

        body: dict[str, Any] = {"prompt": clean_prompt}
        if clean_name is not None:
            body["name"] = clean_name
        return self._request("POST", "/feeds", json=body)

    def update_stream(
        self,
        stream_id: str,
        *,
        prompt: str | None = None,
        name: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Change a stream prompt, name, or active/paused status."""
        clean_prompt = _optional_text(prompt, "prompt", MAX_PROMPT_LENGTH)
        clean_name = _optional_text(name, "name", MAX_STREAM_NAME_LENGTH)
        if status is not None and not isinstance(status, str):
            raise TypeError("status must be a string")
        clean_status = status.strip().lower() if status is not None else None
        if clean_status not in {None, "active", "paused"}:
            raise ValueError("status must be active or paused")
        if clean_prompt is None and clean_name is None and clean_status is None:
            raise ValueError("prompt, name, or status is required")

        body: dict[str, Any] = {}
        if clean_prompt is not None:
            body["prompt"] = clean_prompt
        if clean_name is not None:
            body["name"] = clean_name
        if clean_status is not None:
            body["status"] = clean_status
        return self._request("PATCH", f"/feeds/{_guid(stream_id)}", json=body)

    def list_emissions(
        self,
        stream_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List one stream's emission history by page, newest first."""
        return self._request(
            "GET",
            f"/feeds/{_guid(stream_id)}/emissions",
            params=_page_params(limit, cursor),
        )

    def delete_stream(
        self,
        stream_id: str,
        *,
        confirm_stream_id: str,
    ) -> dict[str, Any]:
        """Permanently delete one stream after exact-ID confirmation."""
        clean_stream_id = _guid(stream_id)
        clean_confirmation = _guid(confirm_stream_id, "confirm_stream_id")
        if clean_stream_id != clean_confirmation:
            raise ValueError("confirm_stream_id must exactly match stream_id")
        return self._request("DELETE", f"/feeds/{clean_stream_id}")


def _client() -> AmbushStreamsClient:
    return AmbushStreamsClient()
