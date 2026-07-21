# CodeScope Email-Validation Video Script

Target duration: 2 minutes 40 seconds. Hard limit: 2 minutes 59 seconds.

This script describes the reproducible email-validation judge route. It does not describe the
separately supplied routing-ownership recording. A final video must use audible narration, readable
1080p capture, no private paths or account details, and no copyrighted music or third-party assets
without permission. An Unlisted YouTube video is acceptable only when anyone with the link can view
it without signing in.

## 0:00–0:15 — The problem

**Visual:** CodeScope cover, then a repository with an email-validation task.

**Narration:** “AI coding agents can generate plausible code before they understand what a
repository already contains. That can create duplicate validators, helpers, and services—and more
maintenance work.”

## 0:15–0:30 — What CodeScope is

**Visual:** Cover transitions to REUSE / EXTEND / CREATE.

**Narration:** “I built CodeScope, a local-first MCP preflight for Python repositories. It helps a
coding agent gather implementation evidence first, then make an explicit REUSE, EXTEND, or CREATE
decision.”

## 0:30–0:50 — Architecture

**Visual:** `assets/submission/architecture.png`.

**Narration:** “CodeScope securely discovers contained Python files, extracts Tree-sitter symbols,
creates model-budgeted chunks, embeds them locally, and stores vectors and metadata in local
Chroma. QueryEngine powers a Rich CLI and exactly four read-only MCP tools. Indexed source is
untrusted evidence: CodeScope never executes it or uploads it to a cloud embedding service.”

## 0:50–1:15 — CLI

**Visual:** Run `codescope status`, then `codescope search "email validation"` against the committed
sample fixture. Keep the terminal free of host paths.

**Narration:** “The local index contains four files, eleven symbols, and sixteen chunks. A semantic
search for email validation returns the existing `validate_email` function at
`validators.py`, lines six through nine.”

## 1:15–1:50 — MCP preflight

**Visual:** Show the four tools, then the preflight evidence flow.

**Narration:** “Through local MCP stdio, CodeScope exposes `list_indexed_files`, `search_code`,
`find_symbol`, and `find_similar`. The repository skill inventories first, gathers behavioral,
exact-symbol, and similar-code evidence, and compares ownership, differences, confidence, and
uncertainty. Similarity is evidence—not proof—and the coding agent makes the final decision.”

## 1:50–2:15 — Result

**Visual:** Run `python scripts/demo.py`, then show the demo-result asset.

**Narration:** “For the fixed signup-validation task, every read-only check converges on
`validate_email` at `validators.py`, lines six through nine. CodeScope recommends REUSE. Exact
source hashes remain unchanged, and the duplicate helper is avoided.”

## 2:15–2:35 — Codex, GPT-5.6, and owner decisions

**Visual:** Build Week changelog, selected tests, security documentation, and Git history.

**Narration:** “I used Codex with GPT-5.6 for architecture exploration, implementation, tests,
security review, MCP integration, release verification, and documentation. I remained responsible
for the product positioning, phase scope, local-first architecture, safety policy, evidence rules,
and every owner approval.”

## 2:35–2:50 — Evidence and close

**Visual:** README evidence block and public repository.

**Narration:** “The project records ninety-one percent production coverage, a verified clean
candidate path, and measured small-fixture performance. The source is public under MIT. CodeScope
helps coding agents understand before they generate.”

## Recording checklist

- Record the real CLI and MCP workflow; do not substitute mock results.
- Keep total duration below 2:59 and target 2:20–2:50.
- Explain what was built and how both Codex and GPT-5.6 were used.
- Distinguish owner decisions from AI assistance.
- Confirm audio clarity and readable 1080p output.
- Remove usernames, home paths, tokens, account identities, and private configuration.
- Use no unauthorized music or visual assets.
- Upload to YouTube as Public or Unlisted—not Private.
- Verify the final URL in an incognito/private browser without signing in.
- Record the verified duration and URL in the final release checklist and submission draft.
