from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL_ROOT = ROOT / "tools/productivity/ambush-streams"
STREAM_ID = "11111111-1111-4111-8111-111111111111"
OTHER_STREAM_ID = "22222222-2222-4222-8222-222222222222"


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any = None,
        reason_phrase: str = "OK",
    ) -> None:
        self.status_code = status_code
        self.payload = payload if payload is not None else {"ok": True}
        self.reason_phrase = reason_phrase

    def json(self) -> Any:
        if isinstance(self.payload, ValueError):
            raise self.payload
        return self.payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse | None = None) -> None:
        self.response = response or FakeResponse()
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> FakeResponse:
        self.calls.append(
            {"method": method, "path": path, "params": params, "json": json}
        )
        return self.response

    def close(self) -> None:
        self.closed = True


def load_client_module():
    sys.modules["centaur_sdk"] = types.SimpleNamespace(
        secret=lambda key, default="": f"placeholder:{key}"
    )
    spec = importlib.util.spec_from_file_location(
        "ambush_streams_test_client",
        TOOL_ROOT / "client.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_client_uses_production_host_and_centaur_placeholder(monkeypatch) -> None:
    module = load_client_module()
    constructed: dict[str, Any] = {}

    def fake_client(**kwargs):
        constructed.update(kwargs)
        return FakeHttpClient()

    monkeypatch.setattr(module.httpx, "Client", fake_client)
    client = module.AmbushStreamsClient()

    assert client.api_key == "placeholder:AMBUSH_API_KEY"
    assert constructed["base_url"] == "https://api.ambush.ai/api/v1"
    assert constructed["headers"]["Authorization"] == (
        "Bearer placeholder:AMBUSH_API_KEY"
    )


def test_client_exposes_only_focused_stream_operations() -> None:
    module = load_client_module()
    public_methods = {
        name
        for name in dir(module.AmbushStreamsClient)
        if not name.startswith("_")
        and callable(getattr(module.AmbushStreamsClient, name))
    }

    assert public_methods == {
        "create_stream",
        "delete_stream",
        "get_stream",
        "list_emissions",
        "list_streams",
        "update_stream",
        "whoami",
    }


def test_list_streams_forwards_bounded_pagination() -> None:
    module = load_client_module()
    fake_http = FakeHttpClient(FakeResponse(payload={"feeds": []}))
    client = module.AmbushStreamsClient(api_key="test-key", http_client=fake_http)

    result = client.list_streams(limit=50, cursor="next-page")

    assert result == {"feeds": []}
    assert fake_http.calls == [
        {
            "method": "GET",
            "path": "/feeds",
            "params": {"limit": 50, "cursor": "next-page"},
            "json": None,
        }
    ]


@pytest.mark.parametrize("limit", [0, 51, True, 1.5])
def test_list_streams_rejects_invalid_limits(limit: Any) -> None:
    module = load_client_module()
    client = module.AmbushStreamsClient(
        api_key="test-key", http_client=FakeHttpClient()
    )

    with pytest.raises((TypeError, ValueError), match="limit"):
        client.list_streams(limit=limit)


def test_create_stream_maps_public_terminology_to_legacy_api_fields() -> None:
    module = load_client_module()
    fake_http = FakeHttpClient()
    client = module.AmbushStreamsClient(api_key="test-key", http_client=fake_http)

    client.create_stream(
        name=" AI policy ",
        prompt=" New AI rules in Canada ",
        base_stream_id=STREAM_ID,
    )

    assert fake_http.calls == [
        {
            "method": "POST",
            "path": "/feeds",
            "params": None,
            "json": {
                "name": "AI policy",
                "prompt": "New AI rules in Canada",
                "base_feed_id": STREAM_ID,
            },
        }
    ]


def test_create_stream_requires_prompt_or_base_stream() -> None:
    module = load_client_module()
    client = module.AmbushStreamsClient(
        api_key="test-key", http_client=FakeHttpClient()
    )

    with pytest.raises(ValueError, match="prompt or base_stream_id"):
        client.create_stream(name="Name only")


def test_update_stream_validates_status_and_maps_route() -> None:
    module = load_client_module()
    fake_http = FakeHttpClient()
    client = module.AmbushStreamsClient(api_key="test-key", http_client=fake_http)

    client.update_stream(STREAM_ID, status=" PAUSED ")

    assert fake_http.calls == [
        {
            "method": "PATCH",
            "path": f"/feeds/{STREAM_ID}",
            "params": None,
            "json": {"status": "paused"},
        }
    ]

    with pytest.raises(ValueError, match="active or paused"):
        client.update_stream(STREAM_ID, status="deleted")


def test_delete_requires_exact_confirmed_stream_id() -> None:
    module = load_client_module()
    fake_http = FakeHttpClient()
    client = module.AmbushStreamsClient(api_key="test-key", http_client=fake_http)

    with pytest.raises(ValueError, match="exactly match"):
        client.delete_stream(STREAM_ID, confirm_stream_id=OTHER_STREAM_ID)
    assert fake_http.calls == []

    client.delete_stream(STREAM_ID, confirm_stream_id=STREAM_ID)
    assert fake_http.calls == [
        {
            "method": "DELETE",
            "path": f"/feeds/{STREAM_ID}",
            "params": None,
            "json": None,
        }
    ]


def test_api_error_preserves_safe_structured_details() -> None:
    module = load_client_module()
    client = module.AmbushStreamsClient(
        api_key="test-key",
        http_client=FakeHttpClient(
            FakeResponse(
                status_code=401,
                reason_phrase="Unauthorized",
                payload={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "The API key is invalid",
                    }
                },
            )
        ),
    )

    with pytest.raises(module.AmbushApiError) as captured:
        client.whoami()

    assert captured.value.status_code == 401
    assert captured.value.code == "UNAUTHORIZED"
    assert "test-key" not in str(captured.value)


def test_non_json_success_is_rejected() -> None:
    module = load_client_module()
    client = module.AmbushStreamsClient(
        api_key="test-key",
        http_client=FakeHttpClient(FakeResponse(payload=ValueError("not json"))),
    )

    with pytest.raises(RuntimeError, match="non-JSON"):
        client.whoami()


def test_network_failure_does_not_include_credentials() -> None:
    module = load_client_module()

    class FailingHttpClient(FakeHttpClient):
        def request(self, *args: Any, **kwargs: Any) -> FakeResponse:
            request = httpx.Request("GET", "https://api.ambush.ai/api/v1/me")
            raise httpx.ConnectError("Authorization: Bearer test-key", request=request)

    client = module.AmbushStreamsClient(
        api_key="test-key", http_client=FailingHttpClient()
    )

    with pytest.raises(RuntimeError) as captured:
        client.whoami()

    assert "test-key" not in str(captured.value)
    assert "ConnectError" in str(captured.value)
