# CEASER Chat Continuity Frontend Handoff

Backend continuity is now prepared for richer follow-up handling without changing the current frontend contract.

## Available request fields

Frontend can optionally send these fields with chat requests:

- `conversation_id`
- `request_id`
- `parent_message_id`

All three are backward-compatible. Existing requests still work.

## Available suggestion fields

Each suggestion now supports these optional fields in addition to the existing ones:

- `label`
- `prompt`
- `conversation_id`
- `parent_message_id`
- `topic`

## Recommended frontend follow-up wiring

When a suggestion card is clicked:

1. Send `suggestion.prompt` as the actual message when present.
2. Preserve `conversation_id`.
3. Send `parent_message_id` from the suggestion object.
4. Use the same normal chat send pipeline as manually typed messages.

## Why this matters

This prevents:

- vague follow-ups running without topic context;
- stale suggestions being used in another conversation;
- "Summarize this" behaving like a fresh blank prompt.
