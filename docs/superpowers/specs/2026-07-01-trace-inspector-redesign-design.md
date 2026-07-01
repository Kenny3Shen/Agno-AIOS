# Trace Inspector Redesign Design

## Goal

Make the Trace page match the compact reference-style inspector: a dense copyable trace header, a left span hierarchy, and a right detail pane where Info contains only input/output and Metadata contains span facts plus raw database-backed attributes.

## Product Context

The target user is an AgentOS operator debugging agent runs. Their job is to quickly identify the selected trace, inspect the span tree, read input/output payloads, and fall back to raw metadata when extracted fields are not enough.

## Design Direction

Subject: trace observability console for Agno-powered AgentOS runs.

Audience: SOC operators, platform engineers, and agent developers.

Single job: reduce visual weight while making trace identity, input/output, and metadata faster to scan.

Color token system:

- Ink `#12151D`
- Paper `#F7F9FC`
- Slate `#D3DBE6`
- Violet `#8A63FF`
- Cyan `#2DC8D2`
- Rose `#F05D5E`

Type:

- Keep the existing Inter / Fira Sans / Microsoft YaHei stack for product consistency.
- Use JetBrains Mono / Fira Code for ids, JSON, durations, and telemetry chips.

Layout:

```text
Trace header
┌ run name/status/actions                                      ┐
│ Created At · Trace ID · Run ID · Session ID · Agent · ...    │
└──────────────────────────────────────────────────────────────┘

Body
┌ Span hierarchy ┬ Selected span detail                         ┐
│ tree/fallback  │ title/status/latency                         │
│                │ Info | Metadata                              │
│                │ Info: Input, Output                          │
│                │ Metadata: span facts, parsed metadata, attrs │
└────────────────┴──────────────────────────────────────────────┘
```

Signature:

The page uses a compact "evidence strip" of copyable chips for trace identity. This replaces large Session/Run/Agent/Workflow cards and mirrors the reference image's Created At / Trace ID / Run ID / Session ID rhythm.

Self-critique:

The generic approach would shrink the existing cards and call it done. This design changes the information hierarchy instead: identity moves to compact chips, input/output become the default working area, and everything diagnostic moves behind Metadata.

## Scope

In scope:

- Replace the large selected trace fact cards with compact copyable evidence chips.
- Add Info/Metadata tab state in the selected span detail.
- Keep Info limited to Input and Output.
- Move start offset, parent, event count, span id, status, duration, parsed metadata, events, and raw attributes into Metadata.
- Render JSON payloads as formatted code blocks, while preserving Markdown rendering for Markdown/text payloads.
- Make Trace styling follow global light/dark tokens.

Out of scope:

- Backend tracing schema changes.
- New trace filtering behavior.
- New persistence or database migrations.
- Replacing the existing span tree with a virtualized tree.

## Data Flow

The frontend continues to consume `/api/traces/{trace_id}`.

`selectedTraceEvidence` derives compact header chips from `TraceItem`: created/start time, trace id, run id, session id, agent/team id, workflow id, and optional user id.

`spanMetadataItems` derives the Metadata ledger from `selectedSpan`, `parsedSpan.metadata`, and `parsedSpan.events`. Raw database-backed attributes remain available in the Attributes JSON block.

Input and output use `ParsedSpanPayload.format` and `ParsedSpanPayload.data`. JSON payloads render as escaped `<pre>` text, not Markdown HTML, so formatted JSON is readable and safe.

## Testing

- Extend `frontend/src/uiShell.test.mjs` with source-level assertions for the evidence strip, tab state, JSON payload rendering, and Metadata ledger.
- Run `cd frontend && npm run test:shell`.
- Run `cd frontend && npm run build`.
- Run repository Python checks:
  - `uv run ruff check .`
  - `uv run ty check .`
- Use Playwright to inspect the Trace page in browser after build/dev server startup.

## Acceptance Criteria

- The selected trace header no longer shows large Session/Run/Agent/Workflow cards.
- Created At, Trace ID, Run ID, Session ID, Agent, Workflow, and User ID when present are compact and copyable.
- The right detail pane has working Info and Metadata tabs.
- Info shows only Input and Output.
- Metadata shows span identity/timing fields, parser metadata, events, and raw attributes.
- JSON input/output is formatted as code, not rendered through Markdown.
- Trace page remains readable in both light and dark modes.
