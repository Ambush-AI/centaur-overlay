from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
TOOL_ROOT = ROOT / "tools/productivity/ambush-streams"
PACKAGE = "centaur_tool_ambush_streams"
STREAM_ID = "11111111-1111-4111-8111-111111111111"


def load_cli_module():
    for name in list(sys.modules):
        if name == PACKAGE or name.startswith(f"{PACKAGE}."):
            del sys.modules[name]
    sys.path.insert(0, str(TOOL_ROOT.parent))
    try:
        # The flat source directory is renamed to centaur_tool_ambush_streams
        # by Hatch at build time. Import it through a temporary package alias
        # so tests exercise the source without first building a wheel.
        import importlib.util

        package_spec = importlib.util.spec_from_file_location(
            PACKAGE,
            TOOL_ROOT / "__init__.py",
            submodule_search_locations=[str(TOOL_ROOT)],
        )
        assert package_spec and package_spec.loader
        package = importlib.util.module_from_spec(package_spec)
        sys.modules[PACKAGE] = package
        package_spec.loader.exec_module(package)
        return importlib.import_module(f"{PACKAGE}.cli")
    finally:
        sys.path.pop(0)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def _close(self) -> None:
        self.closed = True

    def whoami(self) -> dict[str, Any]:
        self.calls.append(("whoami", {}))
        return {"user_id": "user_test"}

    def list_streams(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("list_streams", kwargs))
        return {"feeds": [], "next_cursor": None}

    def create_stream(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("create_stream", kwargs))
        return {"feed_id": STREAM_ID, "status": "active"}

    def update_stream(self, stream_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("update_stream", {"stream_id": stream_id, **kwargs}))
        return {"feed_id": stream_id, "status": kwargs["status"]}

    def delete_stream(self, stream_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("delete_stream", {"stream_id": stream_id, **kwargs}))
        return {"feed_id": stream_id, "status": "deleted"}


def test_health_returns_identity_and_closes_client(monkeypatch) -> None:
    cli = load_cli_module()
    client = FakeClient()
    monkeypatch.setattr(cli, "_client", lambda: client)

    result = CliRunner().invoke(cli.app, ["health"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "ok": True,
        "tool": "ambush-streams",
        "identity": {"user_id": "user_test"},
    }
    assert client.calls == [("whoami", {})]
    assert client.closed is True


def test_list_maps_cli_options(monkeypatch) -> None:
    cli = load_cli_module()
    client = FakeClient()
    monkeypatch.setattr(cli, "_client", lambda: client)

    result = CliRunner().invoke(
        cli.app, ["list", "--limit", "7", "--cursor", "next-page"]
    )

    assert result.exit_code == 0, result.output
    assert client.calls == [("list_streams", {"limit": 7, "cursor": "next-page"})]


def test_create_requires_and_maps_prompt(monkeypatch) -> None:
    cli = load_cli_module()
    client = FakeClient()
    monkeypatch.setattr(cli, "_client", lambda: client)
    runner = CliRunner()

    missing = runner.invoke(cli.app, ["create", "--name", "AI policy"])
    created = runner.invoke(
        cli.app,
        [
            "create",
            "--prompt",
            "New AI rules in Canada",
            "--name",
            "AI policy",
        ],
    )

    assert missing.exit_code != 0
    assert created.exit_code == 0, created.output
    assert client.calls == [
        (
            "create_stream",
            {"prompt": "New AI rules in Canada", "name": "AI policy"},
        )
    ]


def test_pause_and_resume_use_explicit_statuses(monkeypatch) -> None:
    cli = load_cli_module()
    client = FakeClient()
    monkeypatch.setattr(cli, "_client", lambda: client)
    runner = CliRunner()

    paused = runner.invoke(cli.app, ["pause", STREAM_ID])
    resumed = runner.invoke(cli.app, ["resume", STREAM_ID])

    assert paused.exit_code == 0, paused.output
    assert resumed.exit_code == 0, resumed.output
    assert client.calls == [
        ("update_stream", {"stream_id": STREAM_ID, "status": "paused"}),
        ("update_stream", {"stream_id": STREAM_ID, "status": "active"}),
    ]


def test_delete_requires_confirmation_option(monkeypatch) -> None:
    cli = load_cli_module()
    client = FakeClient()
    monkeypatch.setattr(cli, "_client", lambda: client)

    missing = CliRunner().invoke(cli.app, ["delete", STREAM_ID])
    confirmed = CliRunner().invoke(
        cli.app,
        ["delete", STREAM_ID, "--confirm-stream-id", STREAM_ID],
    )

    assert missing.exit_code != 0
    assert client.calls == [
        (
            "delete_stream",
            {"stream_id": STREAM_ID, "confirm_stream_id": STREAM_ID},
        )
    ]
    assert confirmed.exit_code == 0, confirmed.output
