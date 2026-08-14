"""Smoke-test this overlay against a read-only Centaur checkout.

This is intentionally a standalone script rather than a pytest test. CI first
installs the built Ambush Streams wheel and the SDK from the current Centaur
checkout, then runs this script in the same environment.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_ROOT = ROOT / "tools/productivity/ambush-streams"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _load_installer(centaur_checkout: Path):
    installer_path = centaur_checkout / "services/sandbox/install_tool_shims.py"
    _require(installer_path.is_file(), f"missing Centaur installer: {installer_path}")
    spec = importlib.util.spec_from_file_location(
        "centaur_install_tool_shims_compatibility",
        installer_path,
    )
    _require(spec is not None and spec.loader is not None, "cannot load installer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    checkout_value = os.environ.get("CENTAUR_CHECKOUT", "").strip()
    _require(bool(checkout_value), "CENTAUR_CHECKOUT is required")
    centaur_checkout = Path(checkout_value).resolve()
    sys.path.insert(0, str(centaur_checkout))
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(centaur_checkout), existing_pythonpath) if part
    )
    centaur_revision = subprocess.run(
        ["git", "-C", str(centaur_checkout), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    installer = _load_installer(centaur_checkout)
    old_allowlist = os.environ.get("TOOL_ALLOWLIST")
    os.environ["TOOL_ALLOWLIST"] = "ambush-streams"
    try:
        scripts = installer._discover_scripts([ROOT / "tools"])
    finally:
        if old_allowlist is None:
            os.environ.pop("TOOL_ALLOWLIST", None)
        else:
            os.environ["TOOL_ALLOWLIST"] = old_allowlist

    _require(set(scripts) == {"ambush-streams"}, "Centaur did not discover the tool")
    tool = scripts["ambush-streams"]
    _require(tool["project_dir"] == str(TOOL_ROOT), "unexpected project directory")
    _require(tool["client_module"] == "client.py", "unexpected client module")
    _require(
        tool["entrypoint"] == "centaur_tool_ambush_streams.cli:app",
        "unexpected CLI entrypoint",
    )

    with tempfile.TemporaryDirectory(prefix="ambush-centaur-smoke-") as temp_dir:
        temp_root = Path(temp_dir)
        bin_dir = temp_root / "bin"
        installer._install_tool_shims([ROOT / "tools"], bin_dir, refresh=False)
        catalog_run = subprocess.run(
            [str(bin_dir / "centaur-tools"), "json"],
            check=False,
            capture_output=True,
            text=True,
        )
        _require(
            catalog_run.returncode == 0,
            f"generated Centaur catalog failed: {catalog_run.stderr}",
        )
        catalog = json.loads(catalog_run.stdout)
        _require(
            [entry["name"] for entry in catalog] == ["ambush-streams"],
            "generated Centaur catalog is missing the tool",
        )
        shim_run = subprocess.run(
            [str(bin_dir / "ambush-streams"), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        _require(
            shim_run.returncode == 0,
            f"generated Centaur tool shim failed: {shim_run.stderr}",
        )
        _require(
            "Create and manage shared Ambush news streams" in shim_run.stdout,
            "generated Centaur tool shim returned unexpected help",
        )

        skills_dir = temp_root / "workspace-skills"
        copied = installer._copy_skill_dir(ROOT / ".agents/skills", skills_dir)
        _require(copied == 1, "Centaur did not copy exactly one overlay skill")
        _require(
            (skills_dir / "manage-ambush-streams/SKILL.md").is_file(),
            "Centaur did not install the Ambush Streams skill",
        )

    import centaur_sdk
    from centaur_sdk import secret
    from centaur_tool_ambush_streams.client import _client

    sdk_path = Path(centaur_sdk.__file__).resolve()
    _require(
        sdk_path.is_relative_to(centaur_checkout),
        f"Centaur SDK was not installed from the checkout: {sdk_path}",
    )

    old_key = os.environ.pop("AMBUSH_API_KEY", None)
    try:
        _require(
            secret("AMBUSH_API_KEY", "") == "AMBUSH_API_KEY",
            "Centaur SDK did not return the iron-proxy placeholder",
        )
        client = _client()
        try:
            _require(
                client.api_key == "AMBUSH_API_KEY", "tool did not use the placeholder"
            )
            _require(
                str(client._http.base_url) == "https://api.ambush.ai/api/v1/",
                "tool is configured for an unexpected API URL",
            )
        finally:
            client._close()
    finally:
        if old_key is not None:
            os.environ["AMBUSH_API_KEY"] = old_key

    cli = subprocess.run(
        ["ambush-streams", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    _require(cli.returncode == 0, f"CLI failed to start: {cli.stderr}")
    _require(
        "Create and manage shared Ambush news streams" in cli.stdout, "bad CLI help"
    )

    print(
        "Centaur compatibility smoke test passed "
        f"at {centaur_revision} with SDK at {sdk_path}"
    )


if __name__ == "__main__":
    main()
