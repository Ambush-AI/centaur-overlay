from __future__ import annotations

from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]
TOOL_ROOT = ROOT / "tools/productivity/ambush-streams"


def test_centaur_metadata_is_installable_and_host_scoped() -> None:
    config = tomllib.loads((TOOL_ROOT / "pyproject.toml").read_text())

    assert config["project"]["scripts"] == {
        "ambush-streams": "centaur_tool_ambush_streams.cli:app"
    }
    assert config["tool"]["centaur"]["module"] == "client.py"
    assert config["tool"]["centaur"]["hosts"] == ["api.ambush.ai"]
    assert config["tool"]["centaur"]["secrets"] == [
        {
            "type": "http",
            "name": "AMBUSH_API_KEY",
            "mode": "inject",
            "inject_header": "Authorization",
            "inject_formatter": "Bearer {{ .Value }}",
            "hosts": ["api.ambush.ai"],
        }
    ]


def test_overlay_contains_tool_skill_and_no_global_prompt() -> None:
    assert (TOOL_ROOT / "client.py").is_file()
    assert (TOOL_ROOT / "cli.py").is_file()
    assert (ROOT / ".agents/skills/manage-ambush-streams/SKILL.md").is_file()
    assert not (ROOT / "services/sandbox/SYSTEM_PROMPT.md").exists()


def test_install_docs_cover_credential_allowlist_grant_and_verification() -> None:
    readme = (ROOT / "README.md").read_text()
    values = (ROOT / "examples/centaur-values.yaml").read_text()

    for required in (
        "AMBUSH_API_KEY",
        "TOOL_ALLOWLIST",
        "tool-ambush-streams",
        "centaur-perms",
        "ambush-streams health",
    ):
        assert required in readme
    assert "repo: Ambush-AI/centaur-overlay" in values
    assert 'workflowsSubdir: ""' in values
    assert "skillsSubdir: .agents/skills" in values


def test_skill_requires_exact_confirmation_and_shared_identity_language() -> None:
    skill = (ROOT / ".agents/skills/manage-ambush-streams/SKILL.md").read_text()

    assert "--confirm-stream-id" in skill
    assert "explicit confirmation" in skill
    assert "installation-owned streams" in skill
    assert "Never ask someone to paste a key" in skill
