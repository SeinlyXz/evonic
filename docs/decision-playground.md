---
title: Decision Playground
description: Safely test a Decision Profile or a compatible model without changing production configuration.
sidebar:
  order: 5
---

# Decision Playground

Open **System Settings → Decision Models → Playground** to run one structured, inference-only decision test at a time.

## Safety and privacy

The Playground **does not execute** shell commands, Python, tools, webhooks, or any other side effect. It does not save a test as a Decision Profile or update any model/profile configuration.

- Requests are limited to 64 KiB; schemas are limited to the runtime field, choice, description, timeout, and attempt bounds.
- Secret-like keys and values (for example, passwords, tokens, authorization headers, and API keys) are rejected before a provider is contacted.
- Tests are rate-limited and provider work is time-bounded.
- Raw input, prompts, credentials, and raw provider responses are not stored. The activity record retains only bounded normalized outcome metadata.
- Provider logits are shown only if the adapter genuinely supplies them. Otherwise the result says they are unavailable.

## Test modes

### Saved Profile Test

Select an enabled Decision Profile to exercise its saved schema, policy version, primary/fallback model, timeout, retry, and confidence configuration. The Playground reads this configuration; it never changes it. Its activity source is recorded as **Profile Test**.

### Direct Model Test

Choose a decision-capable model and create a temporary schema. This configuration exists only for the single request and is never persisted as a profile. Its activity source is **Playground**.

## Building a schema

Use the visual builder or edit **Schema JSON** directly. Both remain synchronized. Version 1 permits only:

- `choice` — two or more named values, optionally with a field description;
- `boolean` — true/false, optionally nullable;
- `score` — a numeric value with finite inclusive `minimum` and `maximum` bounds.

For example, choose **Outage preset** to create a multi-field incident decision:

```json
{
  "version": "decision-schema/v1",
  "fields": [
    {
      "key": "priority",
      "kind": "choice",
      "description": "Operational priority",
      "choices": ["HIGH", "LOW"]
    },
    {
      "key": "requires_review",
      "kind": "boolean",
      "description": "Whether a human should review this incident"
    }
  ]
}
```

Enter synthetic, non-sensitive JSON input and select **Run safe test**. Validation failures identify the invalid field or property before invocation when possible.

## Reading results

The result panel separates:

- normalized per-field values and confidence;
- normalized candidate probabilities/scores, when the adapter provides them;
- genuine provider logits, when reported by the adapter (otherwise unavailable);
- execution details including adapter/model, attempts, latency, fallback state/reason, warnings, profile/policy version; and
- a copyable normalized JSON envelope.

Timeouts, malformed provider output, unsupported models/schemas, secret redaction, and rate limits are returned as actionable errors. Correct the reported issue and run a new test; sensitive inputs are not restored automatically.
