---
name: manage-ambush-streams
description: Manage the shared Ambush news streams configured for this Centaur installation when a human explicitly asks to create, list, inspect, rename, change, pause, resume, or permanently delete a stream, or review a stream's emitted news items.
---

# Manage Ambush Streams

Use the `ambush-streams` tool for explicit human requests to manage the Ambush
Streams account configured by this Centaur installation's operator.

The credential is normally shared by the Centaur principals that receive its
tool role. These are installation-owned streams, not necessarily the
requester's personal Ambush streams. Do not create or mutate a stream merely
because an automated alert, workflow, pull request, or news discussion mentions
a topic that could be monitored.

The production REST API retains legacy resource fields such as `feed_id` and
`base_feed_id`. Use those returned fields exactly, but call the resources
streams when speaking with the requester.

## Tool shape

The CLI emits JSON and provides these commands:

- `ambush-streams health`
- `ambush-streams whoami`
- `ambush-streams list --limit 20`
- `ambush-streams get <stream-id>`
- `ambush-streams create --name <name> --prompt <prompt>`
- `ambush-streams update <stream-id> --status paused`
- `ambush-streams pause <stream-id>`
- `ambush-streams resume <stream-id>`
- `ambush-streams emissions <stream-id> --limit 20`
- `ambush-streams delete <stream-id> --confirm-stream-id <same-stream-id>`

Use `ambush-streams --help` and `ambush-streams <command> --help` when an
argument is unclear. A nonzero exit or an `ok: false` error payload means the
operation failed. A `401` normally means the operator must replace, restore, or
grant the configured `AMBUSH_API_KEY`. Never ask someone to paste a key into a
conversation.

## Operating rules

- Start with `ambush-streams list` when the requester supplied a name instead
  of an ID. Follow `next_cursor` only when the target may be on another page or
  the requester asks for every stream.
- Resolve a stream by its returned `feed_id`. If names are duplicated or the
  request is ambiguous, show the matching names, prompt excerpts, and IDs and
  ask the requester to choose.
- Never invent a stream ID, base stream ID, cursor, prompt, status, emission,
  or tool result.
- Report every mutation with the returned `feed_id` and status. Do not repeat a
  non-idempotent create after an uncertain failure.
- Do not use curl, generic HTTP tools, browser OAuth, or another Ambush
  credential when the installed tool is unavailable. Report the missing
  capability to the operator.

## Create or update

Translate an explicit request into one focused monitoring prompt, preserving
entities, event types, geography, urgency, and exclusions. Ask one concise
question only if ambiguity would materially change the stream. Create one
stream unless the requester explicitly asks for separate streams.

For changes, resolve the exact stream first and send only requested fields.
Use `pause` or `update --status paused` to pause it and `resume` or
`update --status active` to resume it.

## Review emissions

Use `get` for current stream details and recent emissions. Use `emissions` for
the complete or paginated history. Follow `next_cursor` until null only when
the requester asks for all emissions. Distinguish an empty history from a
failed request.

## Delete

Deletion is permanent.

1. Resolve the exact stream and state its name or prompt excerpt and ID.
2. Obtain explicit confirmation to permanently delete that exact stream. A
   vague cleanup request is not confirmation.
3. Pass the same returned UUID as both the positional stream ID and
   `--confirm-stream-id`.
4. Report the deleted stream ID. Never claim deletion can be undone.

## Boundaries

- Use this capability only for Ambush stream lifecycle and emission requests,
  not unrelated news research, generic RSS work, or delivery-channel setup.
- Do not imply a stream guarantees a particular story or delivery time.
- If Ambush rejects a prompt, explain the returned restriction and help
  reframe a legitimate monitoring request without trying to bypass policy.
