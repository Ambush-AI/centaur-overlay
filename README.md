# Ambush Streams for Centaur

The official [Ambush Streams](https://ambush.ai) overlay for
[Centaur](https://centaur.run). It lets a Centaur agent create, inspect,
update, pause, resume, and permanently delete shared news streams, and review
their emitted news items.

## What gets installed

```text
tools/productivity/ambush-streams/       Python tool and CLI
.agents/skills/manage-ambush-streams/    Agent workflow and safety guidance
examples/centaur-values.yaml             Mergeable Helm-values example
```

The tool calls `https://api.ambush.ai/api/v1` over HTTPS. Centaur's iron-proxy
injects `AMBUSH_API_KEY` only for requests to `api.ambush.ai`; the raw key is
not placed in the agent workspace.

## Install

### 1. Create a dedicated Ambush key

Sign in to [Ambush Developers](https://app.ambush.ai/developers?tab=keys) with the
account that should own this Centaur installation's streams. Create a key named
something recognizable, such as `centaur-acme-production`.

Treat this as a shared integration identity:

- Everyone granted the tool sees and manages the same Ambush streams.
- Do not use a personal account if the tool will be available in shared Slack
  or Teams channels.
- Prefer a dedicated Ambush account containing only the streams intended for
  that Centaur installation.

### 2. Add the overlay source

Merge the following source into `overlays.sources` in the Centaur Helm values.
Keep the base Centaur source first and any organization-specific overlay last,
so the organization can override shared integrations deliberately.

```yaml
overlays:
  sources:
    - repo: paradigmxyz/centaur
      ref: <your-pinned-centaur-ref>

    - repo: Ambush-AI/centaur-overlay
      ref: main
      visibility: public
      toolsSubdir: tools
      workflowsSubdir: ""
      skillsSubdir: .agents/skills

    - repo: your-org/centaur-overlay
      ref: main
```

For a reproducible production rollout, replace `main` with a release tag or
commit SHA. See [`examples/centaur-values.yaml`](examples/centaur-values.yaml)
for a copyable fragment.

### 3. Store the credential

Add the key as `AMBUSH_API_KEY` using the secret source already configured for
Centaur:

- With `ironProxy.secretSource: env`, add `AMBUSH_API_KEY` to the Kubernetes
  Secret selected by `secretManager.existingSecretName`.
- With 1Password-backed secret resolution, create the corresponding
  `AMBUSH_API_KEY` item or field using the deployment's existing naming policy.

Never commit the key to this repository, Helm values, or an agent prompt.

### 4. Allow and grant the tool

If the deployment sets `TOOL_ALLOWLIST`, append `ambush-streams` without
removing its existing entries:

```yaml
sandbox:
  extraEnv:
    TOOL_ALLOWLIST: linear,github,ambush-streams
```

Then register the tool and grant its generated `tool-ambush-streams` role to
the users or channels that should share the Ambush account. From a Centaur
checkout, point `TOOL_DIRS` at both the base tools and this overlay and use
`centaur-perms`:

```sh
export TOOL_DIRS=/path/to/centaur/tools:/path/to/centaur-overlay/tools

cargo run -p centaur-perms -- \
  principals grant slack-channel-c123 \
  --tool ambush-streams
```

Use a Slack user principal instead when the integration should be available
only in that person's direct messages. Centaur's Console can be used to inspect
the resulting role, secret grant, and effective permissions.

### 5. Verify from a fresh sandbox

```sh
centaur-tools list
ambush-streams health
ambush-streams list --limit 1
```

`health` performs the read-only `/me` request and returns the Ambush user ID.
It never prints the API key.

## Example requests

- "Create a shared stream for material cybersecurity incidents affecting
  Canadian banks."
- "Pause the AI regulation stream."
- "Show the five latest items from our semiconductor supply-chain stream."

The bundled skill resolves names to IDs, handles pagination, avoids repeating
uncertain creates, and requires exact-stream confirmation before deletion.

## CLI reference

```text
ambush-streams health
ambush-streams whoami
ambush-streams list [--limit 20] [--cursor CURSOR]
ambush-streams get STREAM_ID
ambush-streams create --prompt PROMPT [--name NAME]
ambush-streams update STREAM_ID [--prompt PROMPT] [--name NAME] [--status active|paused]
ambush-streams pause STREAM_ID
ambush-streams resume STREAM_ID
ambush-streams emissions STREAM_ID [--limit 20] [--cursor CURSOR]
ambush-streams delete STREAM_ID --confirm-stream-id STREAM_ID
```

Commands emit JSON so both agents and operators can inspect exact API results.
The production API still uses legacy field names such as `feed_id`; the CLI and
skill call those resources streams everywhere user-facing.

## Development

Run the repository tests:

```sh
uv run --no-project \
  --with pytest \
  --with httpx \
  --with typer \
  --with rich \
  pytest -q
```

Build the installable tool package:

```sh
uv run --no-project --with build \
  python -m build tools/productivity/ambush-streams
```

Test the CLI locally with an explicitly supplied environment credential:

```sh
uv tool install --editable tools/productivity/ambush-streams
export AMBUSH_API_KEY='<development key>'
ambush-streams health
```

Do not paste an Ambush key into a Centaur conversation. Local environment use
is only for operator development; deployed sandboxes should receive a Centaur
placeholder and rely on iron-proxy injection.
