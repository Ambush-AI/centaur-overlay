"""JSON CLI for the Ambush Streams Centaur tool."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import typer

from .client import AmbushApiError, AmbushStreamsClient, _client

app = typer.Typer(
    name="ambush-streams",
    help="Create and manage shared Ambush news streams.",
    no_args_is_help=True,
)


def _print(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _run(operation: Callable[[AmbushStreamsClient], dict[str, Any]]) -> None:
    client: AmbushStreamsClient | None = None
    try:
        client = _client()
        _print(operation(client))
    except AmbushApiError as exc:
        _print(
            {
                "ok": False,
                "error": {
                    "status_code": exc.status_code,
                    "code": exc.code,
                    "message": exc.message,
                },
            }
        )
        raise typer.Exit(1) from exc
    except (RuntimeError, TypeError, ValueError) as exc:
        _print(
            {
                "ok": False,
                "error": {
                    "code": "INVALID_REQUEST"
                    if isinstance(exc, (TypeError, ValueError))
                    else "TOOL_ERROR",
                    "message": str(exc),
                },
            }
        )
        raise typer.Exit(1) from exc
    finally:
        if client is not None:
            client._close()


@app.command()
def health() -> None:
    """Check API connectivity and credential identity without exposing the key."""

    def check(client: AmbushStreamsClient) -> dict[str, Any]:
        return {
            "ok": True,
            "tool": "ambush-streams",
            "identity": client.whoami(),
        }

    _run(check)


@app.command()
def whoami() -> None:
    """Return the Ambush user identity that owns this installation's streams."""
    _run(lambda client: client.whoami())


@app.command("list")
def list_streams(
    limit: int = typer.Option(20, min=1, max=50, help="Maximum streams to return."),
    cursor: str | None = typer.Option(
        None, help="Opaque next_cursor from a prior page."
    ),
) -> None:
    """List shared streams, newest first."""
    _run(lambda client: client.list_streams(limit=limit, cursor=cursor))


@app.command("get")
def get_stream(
    stream_id: str = typer.Argument(..., help="Stream UUID (returned as feed_id)."),
) -> None:
    """Get one stream with recent emissions and usage."""
    _run(lambda client: client.get_stream(stream_id))


@app.command("create")
def create_stream(
    prompt: str = typer.Option(..., help="Focused monitoring prompt."),
    name: str | None = typer.Option(None, help="Optional display name."),
) -> None:
    """Create one shared stream from a focused monitoring prompt."""
    _run(
        lambda client: client.create_stream(
            prompt=prompt,
            name=name,
        )
    )


@app.command("update")
def update_stream(
    stream_id: str = typer.Argument(..., help="Stream UUID (returned as feed_id)."),
    prompt: str | None = typer.Option(None, help="Replacement monitoring prompt."),
    name: str | None = typer.Option(None, help="Replacement display name."),
    status: str | None = typer.Option(None, help="active or paused."),
) -> None:
    """Change a stream prompt, name, or status."""
    _run(
        lambda client: client.update_stream(
            stream_id,
            prompt=prompt,
            name=name,
            status=status,
        )
    )


@app.command()
def pause(
    stream_id: str = typer.Argument(..., help="Stream UUID (returned as feed_id)."),
) -> None:
    """Pause one stream."""
    _run(lambda client: client.update_stream(stream_id, status="paused"))


@app.command()
def resume(
    stream_id: str = typer.Argument(..., help="Stream UUID (returned as feed_id)."),
) -> None:
    """Resume one paused stream."""
    _run(lambda client: client.update_stream(stream_id, status="active"))


@app.command("emissions")
def list_emissions(
    stream_id: str = typer.Argument(..., help="Stream UUID (returned as feed_id)."),
    limit: int = typer.Option(20, min=1, max=50, help="Maximum emissions to return."),
    cursor: str | None = typer.Option(
        None, help="Opaque next_cursor from a prior page."
    ),
) -> None:
    """List one stream's emitted news items, newest first."""
    _run(
        lambda client: client.list_emissions(
            stream_id,
            limit=limit,
            cursor=cursor,
        )
    )


@app.command("delete")
def delete_stream(
    stream_id: str = typer.Argument(..., help="Stream UUID to permanently delete."),
    confirm_stream_id: str = typer.Option(
        ...,
        "--confirm-stream-id",
        help="Must exactly match STREAM_ID after explicit human confirmation.",
    ),
) -> None:
    """Permanently delete one exactly confirmed stream."""
    _run(
        lambda client: client.delete_stream(
            stream_id,
            confirm_stream_id=confirm_stream_id,
        )
    )


if __name__ == "__main__":
    app()
