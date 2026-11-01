# Operator Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task, with task review and whole-branch review.

**Goal:** Replace the read-only deployment entry point with a usable Chinese operator workspace: configure models, create tasks from batch assets and requirements, approve and observe execution, contribute guidance, inspect evidence-backed findings, and export reports.

**Architecture:** A new localhost operator service wraps the existing protected campaign runtime. Durable workspace records contain drafts, runs, model selections, interventions and narrative finding details; the existing policy, ledger, facts and coverage remain authoritative for execution and evidence. Models produce bounded data proposals, never executable commands or approvals.

**Tech Stack:** Python 3.12/3.13 standard library, SQLite, native HTML/CSS/JavaScript, Linux Docker, PowerShell deployment, real browser acceptance.

## Global Constraints

- Work only on feature/operator-workspace, based on cbaa6e45fabfff0b8746398d3ff12e83040847a8; never modify master or erase previous deployment records.
- No real target tests or real model calls during development. Use isolated loopback HTTP/model fixtures, synthetic keys and offline Docker tests. The user will enter their own API keys in the UI; never request them in chat or read ARTEX credentials.
- Preserve Commander/Scout/Soldier/General, Watchdog, fact provenance, dependency invalidation, independent review, scope enforcement and durable budgets. An observation is not automatically a vulnerability; a finished run is not acceptance of the engagement.
- Execution supports only existing bounded http_get/http_head and explicit manual coverage assessments. No arbitrary shell, plugins, redirect following, credential injection into targets or model-controlled network access.
- Model profiles are operator-configured OpenAI-compatible HTTPS endpoints, with independent key storage, redacted APIs, no raw key logging/export, no automatic provider fallback or retries. A different endpoint cannot silently inherit a key. Save does not call a provider; Test and planning/analyzing do.
- Models never approve their own actions, widen scope, change budgets or confirm findings. Both model input and output are untrusted data. Guidance that cannot change a hard constraint is labelled accordingly.
- Persist input and acknowledgement separately. Messages must show queued/consumed/failed, and expose which planning/action consumer handled them; recording a message is not claiming it affected execution.
- Draft import does not resolve DNS or contact targets. Preflight resolution is explicit and bounded; execution uses frozen validated IP answers and exact action approvals. Scope and budgets are immutable during a run.
- HTTP service exposes only localhost in deployment; authenticated mutations require exact Host/Origin and CSRF protection. No CORS, no raw filesystem routes, no unsafe HTML insertion. Do not expose secrets through exceptions or status endpoints.
- Python application dependencies remain standard library. Keep each new module focused. Windows host automation is PowerShell; Bash only inside confirmed Linux containers.
- Retain the current 8765 service until a replacement passes browser acceptance; stop only verified owned resources when switching. No Docker socket, privileged or host-network containers.

## Product acceptance journeys

1. Model settings: save two profiles, refresh, select one per task (optional role overrides), edit without displaying the saved key, test connection with a visible success/error. Endpoint edits require re-entering a key. No key appears in snapshots or reports.
2. New task: name, objective, context, text guidance, explicit exclusions, request/response/time/model-call budgets, batch pasted assets or UTF-8 CSV. Preview shows normalized rows, duplicates and errors; invalid rows are not silently dropped. Save and reopen the draft without network calls.
3. Plan: resolve domains explicitly, display frozen scope and model-proposed GET/HEAD actions or a deterministic observation plan; show unsupported requested capabilities as gaps. Approval covers the exact plan revision. No target requests before approval.
4. Process: start, show actual worker/action/evidence events, pause/resume/cancel without refund or replay. Add guidance during execution; queued versus consumed status survives restart. Priority/retest requests create explicit effects or pending plans, not fake chat responses.
5. Coverage: assets and check cells distinguish observation success, failed, blocked, manual, N/A and untested. Coverage does not imply vulnerability absence.
6. Findings: open a full case (affected target, severity, description, impact, reproduction, remediation, evidence, origin, review history); create a candidate from an actual fact, retest through a new approved action, submit independent review, invalidate provenance and see stale status.
7. Report: preview and export escaped HTML, Markdown and JSON with constraints, coverage, findings and evidence references, unfinished checks and stop reason. Errors are visible, not empty reports. Report generation does not grant or execute work.
8. Restart: drafts, runs, keys, evidence and input survive; uncertain in-flight operations are not retried automatically. UI reconnects without losing session on ordinary reload.

## Task 1: Model profiles and bounded provider client

**Files:** lib/pentest/models.py, lib/pentest/model_transport.py, tests/test_pentest_models.py, docs/MODEL-CONFIGURATION.md.

**Interface:** `ModelProfiles(root: Path, *, allow_http_loopback=False)`; `list() -> list[dict]`, `get(profile_id) -> dict` return only public metadata; `save(data: dict, *, profile_id=None) -> dict`, `delete(profile_id) -> None`; `complete(profile_id, messages: list[dict], *, max_output_tokens=None) -> dict` returns `{content: str, usage: dict, model: str}`; `test(profile_id) -> dict` calls a minimal bounded prompt and returns safe status/latency/usage. Raise `ModelError` with a safe human-readable code/message.

Profile public schema: id, name, provider (`deepseek`, `glm`, `longcat`, `custom`), base_url, model, timeout_seconds (5..120, default45), max_output_tokens (64..8192, default2048), has_key, revision, created_at, updated_at. Save input additionally api_key; omitted/empty on update retains an existing key only for unchanged provider and canonical endpoint. Unknown fields and type confusion fail. Secrets are separate private files with UUID names, 0600/0700 on Linux, never embedded in metadata, argv, exported errors or ordinary logs. Document local-file protection honestly rather than claiming encryption. The deployment task must restrict Windows secret-directory ACLs.

`PRESETS` provides editable URLs from verified official documentation: DeepSeek https://api.deepseek.com, GLM https://open.bigmodel.cn/api/paas/v4, LongCat https://api.longcat.chat/openai/v1; append exactly `/chat/completions`. Model identifier remains user-editable (do not rely on a fixed catalogue). Primary docs checked 2026-11-01: https://api-docs.deepseek.com/ ; https://docs.bigmodel.cn/cn/guide/develop/openai/introduction ; https://longcat.chat/platform/docs/APIDocs.html .

- [ ] Write failing unittest scenarios for save/update/reopen/redaction, endpoint-key binding, invalid URLs/fields, successful fixture completion, provider HTTP failure/malformed response/oversize/whole-call timeout/redirect refusal and resource cleanup. A failure must be observed before implementation.
- [ ] Implement storage and JSON-only Chat Completions. No streaming, tools, function calling or provider-native browsing. At most 1 MiB request and response, at most64 messages, content lengths bounded; explicit output limit and `stream:false`; no response_format assumption. Disable proxies and redirects; TLS verification remains enabled. Enforce a whole-operation timeout including DNS/TLS/read, not only per-socket idle time, using a bounded child transport if necessary. Fixed Python module invocation only; never use a shell. Child input carries secrets privately, not argv or environment.
- [ ] Errors never echo response bodies, caller keys, URL credentials, model output or traceback. Keep safe HTTP status codes and classified cause. No retry. Results exclude reasoning content and arbitrary response fields; usage is validated integer metadata.
- [ ] Run offline fixture tests in the pinned Python3.12 container, record RED/GREEN evidence; run existing complete suite once before task commit. Update docs and report actual limitations.

## Task 2: Durable intake, interventions and rich report data

**Files:** lib/pentest/workspace_store.py, lib/pentest/workspace_intake.py, lib/pentest/workspace_reports.py, tests/test_workspace_store.py, docs/OPERATOR-WORKSPACE.md.

**Interface:** persisted versioned drafts/runs/events/messages/finding narratives; pure `parse_assets(text, format='lines')` and `validate_draft(data)`; store APIs and record schemas must be documented in a task contract before Task3. Import supports explicit http/https URLs, bare host/IP defaults to https with preview, CSV target/name/group/notes. Maximum500 assets/1MiB input; reject credentials, fragments, control characters, wildcards, CIDRs (unsupported as request targets), unsupported protocols and ambiguous entries. Report renderer consumes a fully assembled public snapshot and escapes all untrusted text.

- [ ] RED tests cover mixed valid/invalid/duplicate inputs and no DNS; save/reopen/revision-conflict; path traversal; idempotent intervention submission with distinct consumption; independent narrative revisions; report inclusion of gaps, stale findings and malicious HTML escaped.
- [ ] Implement SQLite transactions, validated UUID paths and bounded schemas. Draft fields: name, goal, context, guidance, assets, exclusions, allowed_tools, budgets, expiry_seconds, model_profile_id and optional role_profiles. Keep policy fields distinct from guidance. Runs refer to a frozen draft revision and immutable policy/plan snapshots, with append-only events. No direct mutations of core ledger/evidence tables.
- [ ] Report schema includes project/run identity, scope/goal/constraints, budgets/usage, worker events, asset/check coverage, finding narrative + effective provenance state/reviews, guidance state, stop reason and unfinished checks. Export Markdown/HTML/JSON; no secrets or automatic vulnerability confirmation. HTML has no remote assets or active untrusted content.
- [ ] Focused tests and complete offline suite; commit and write interface contract + evidence for Task3.

## Task 3: Protected execution, model planning and authenticated operator API

**Files:** lib/pentest/workspace.py (service orchestration), workspace_runner.py, workspace_planner.py, workspace_http.py, dns_resolve.py; tests/test_workspace_runtime.py, test_workspace_http.py.

**Interfaces:** consume Task1 ModelProfiles and frozen Task2 store contract; `create_server(root, port=0, *, container_listen=False, ...)` follows existing dashboard test pattern. `python -m pentest.workspace --root /state --port 8765 --container-listen` runs owned persistent local service. Publish documented typed API routes used by Task4, not generic database/command endpoints.

- [ ] RED integration tests use real loopback fixtures and cover zero target hits before exact plan approval, bounded DNS/frozen peer selection, model calls producing validated plans/candidates, model error no fallback, target response cannot grant scope, persistent message consumption, pause/cancel/restart, invalid/stale review rejection and report download.
- [ ] Implement preflight as explicit bounded operation and pending plan revision. Bind exact targets/tools/limits, normalized origins and frozen IPs. Reject excluded destinations and policy widening. Model-proposed paths may only belong to enrolled origins and must be visible before approval. Generate coverage plan and action-to-cell links; lazy submit actions preserves priority control. No endpoint bypasses broker.
- [ ] Model tasks send objectives, immutable scope/tool limits, bounded evidence excerpts and persisted human guidance. Separate per-run model-call budget from target ledger; reserve before calls and do not refund uncertain calls. A call must be consumed/failed durably. Model text may propose candidates with real fact IDs and full narratives; never automatic confirmed status. General independent review uses a later independently approved execution and operator decision; same evidence cannot self-confirm.
- [ ] Run scheduler selects pending approved steps; spawn logical protected workers through existing runtime. Show true role/model involvement, Watchdog and receipt events. Stop on budget/expiry/no approved work/no remaining plan/model failure/cancel, with precise reason and engagement_complete=false. A new suggestion goes to plan approval rather than silently extending a run.
- [ ] Human guidance is durable and sent at the next explicit model planning/analysis turn; no-model mode labels recorded-only notes. Prioritize pending action, pause, and request retest are typed commands with visible applied/result or rejection. Retest retains the same run budget; hard-scope edits require an explicit new run. Resume cannot revive cancelled/uncertain work.
- [ ] Auth uses per-process random bootstrap fragment -> HttpOnly SameSite=Strict session cookie plus CSRF token held by same-origin UI; exact Host and Origin validation and no CORS. Enforce body limits/content type, reject malformed/unknown routes/fields, escape errors, no raw tracebacks. Token/session values are not report data. GET routes cannot trigger target/model calls.
- [ ] Expose model settings/list/save/delete/test, draft import/save/list/get, preflight/plan/approve/start/pause/resume/cancel, intervention, finding/detail/review/invalidate, snapshot and report routes. Test UI-request shapes via HTTP. Record API contract, focused/full suite evidence and commit.

## Task 4: Complete operator UI, deployment and product acceptance

**Files:** lib/pentest/operator_web/index.html, app.css, app.js; scripts/operator-workspace.ps1; docs/OPERATOR-WORKSPACE.md, docs/ARTEX-REFERENCE.md; tests/browser/operator-workspace acceptance; targeted deployment tests.

- [ ] Before UI implementation write real-browser acceptance scenarios for the eight journeys above against a fixture-backed owned service. Test actual clicks, form submissions, navigation, reload and downloads, not only static text.
- [ ] Implement Chinese workspace with navigation Tasks / Model Settings; task intake and import preview; draft editing; plan review and real start; process timeline with input composer; assets/coverage; findings list with separate full detail and evidence/review; report preview/export. Show errors and actionable empty states, disable illegal actions with reasons. Poll bounded snapshots while preserving focus, typed input and selected finding. Use native accessible labels and keyboard controls, textContent for untrusted strings.
- [ ] Model settings provide presets, custom URL/model, password input, has-key indicator, update-without-exposure, delete and connection test. Task can select profile and optional per-role override. Never place keys in localStorage, query strings, logs or exports. Tell users model calls send task context/evidence excerpts to selected provider.
- [ ] Deploy snapshot of committed source with existing ownership/snapshot verification patterns. New persistent writable workspace state and separate protected secret mount; readonly source/root; no socket or privileges, resource bounds. Network bridge permits configured provider and policy-controlled target requests; describe software boundary honestly. Existing state remains archived, not treated as a fresh writable campaign. Status/Open/Stop/Start preserve drafts and approvals and only touch owned resources.
- [ ] Exercise browser fixtures including bad profile, batch errors, approval, intervention consumption, live process, full finding/retest/review/stale propagation, report exports and restart. No real keys/models/targets. Capture user-facing screenshots and concise workflow guide in outputs/operator-workspace.
- [ ] Run pinned3.12+3.13 complete regression and real deployment checks; task review then whole-branch review and fixes. Publish PR based on feature/local-legion-deployment with exact-tree verification and GitHub CI. Switch owned localhost8765 entry to validated workspace, verify from a fresh browser, preserve prior deployment and handover records.

## Plan review

The tasks preserve the separation between model context and hard execution controls. Task1 is independently testable and its interface is fixed; later service/UI contracts are documented as each owning task completes. The implementation is continuous under existing authorization; no new user resources are required before local model configuration becomes available.
