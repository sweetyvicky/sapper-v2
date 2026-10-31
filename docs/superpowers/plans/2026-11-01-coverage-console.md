# Asset and Test Coverage Console Implementation Plan

> **For agentic workers:** Use subagent-driven-development with focused task briefs, independent reviews, and a whole-branch review. Keep the current user's autonomous delivery preference; no repeated workflow-choice question is needed.

**Goal:** Provide a Chinese daily-engagement workspace showing asset coverage, explicit test-plan coverage, execution progress, and evidence drill-down, informed by the recorded ARTEX study and implemented independently.

**Architecture:** Extend existing controller models with genuinely read-only views and a versioned coverage plan. Derive every coverage cell from persisted runtime/evidence records or attributed operator assessment. Serve an offline-capable vanilla HTML/CSS/JS workspace from a host-loopback read-only HTTP viewer (native loopback or explicit isolated-container mode); export self-contained snapshots and recorded deterministic lab replay.

**Tech Stack:** Existing Python 3.12+ stdlib and SQLite on Linux; native browser JavaScript, no frontend build/runtime dependencies; local Playwright CLI for real-browser verification; pinned offline Python 3.12/3.13 Docker tests.

## Global Constraints

- Base is d471de5e824091d740703e6d5384089a9d1d9e12. Work on feature/coverage-console; preserve feature/authorized-pentest and master. Deliver a separate PR targeting feature/authorized-pentest so the iteration is reviewable independently.
- Independently implement all code, styles and assets. ARTEX is an architectural reference only; record immutable source links and decisions in docs/ARTEX-REFERENCE.md.
- Preserve Commander/Scout/Soldier/General, Watchdog, existing fact graph, exact approvals, persistent budgets, execution deadlines, receipt integrity and invalidation.
- Plan membership or UI interaction never grants execution authority. Worker JSON cannot import a coverage plan, issue an assessment, approve or execute via the viewer.
- Only mock/isolated loopback activity, no real target tests, model calls, passwords or API keys. Existing numeric-IP bounded HTTP behavior remains unchanged.
- A successful HTTP response can complete a matching observation item, not a manual security assessment. Coverage is not a claim of no vulnerabilities.
- Viewer requests must not modify databases, recover leases, project graph state, approve, run tasks, or contact target assets. No raw response bodies or controller filesystem paths in the browser payload.
- Explicit denominators: zero applicable items yield null percentages, never 100%; invalid/revoked/expired evidence removes completion credit. Parent/structural nodes do not inherit completion credit automatically.
- Browser renders all imported labels, notes and evidence text as inert text; no untrusted innerHTML, external resources, remote asset loads or clickable target navigation.
- Keep runtime dependencies in Python stdlib and browser native APIs. Test-only browser tooling must not become an application dependency.

## Task 1: Read-only observation and provenance-aware coverage

**Files:** lib/pentest/{ledger,evidence,runtime}.py (minimal read-only support), new lib/pentest/coverage.py, tests/test_pentest_coverage.py. No CLI or web changes in this task.

**Interfaces:**

```python
Campaign(root, policy, *, read_only=False, **existing_options)
Campaign.snapshot() -> dict  # only on a read-only Campaign; includes evidence and safe runtime metadata
CoverageStore(campaign, *, read_only=False)
CoverageStore.import_plan(plan: dict, actor: str) -> dict
CoverageStore.assess(asset_id, check_id, *, outcome, actor, note, fact_ids=()) -> dict
CoverageStore.snapshot() -> dict
```

The task brief defines exact schemas, limits, state rules, API error behavior, and version semantics. Read-only mode opens existing SQLite files with mode=ro and never executes schema/initialization/mutation; writes fail closed. Existing default mutable APIs keep their behavior. Strict plan import is one atomic revision and exact repeat is idempotent. Assessments bind the current plan revision; a changed plan retains history and conservatively resets manual assessments.

- [ ] Write RED tests with real existing Campaign/Ledger/EvidenceStore fixtures: read-only reopen leaves all source files byte-identical, rejects mutations and missing/corrupt state; GET-style snapshots do not recover expired pending leases.
- [ ] Implement read-only constructors/connectors and shared status serialization without duplicating validation or creating a second authority for receipts.
- [ ] Write RED tests for duplicate/cyclic assets, target/intent/tool mismatches, exact denominators, zero denominator, explicit last-attempt ordering, manual assessment rules, revisions, evidence invalidation and no authority from plan fields.
- [ ] Implement strict coverage-plan storage, attributed assessments, stable matrix states, asset hierarchy and metadata-only task/receipt/fact/finding links.
- [ ] Verify concrete examples such as:

```python
view = coverage.snapshot()
assert view['metrics']['assets'] == {'covered': 1, 'total': 3, 'ratio': 1 / 3}
assert view['metrics']['tests']['covered'] == 1
assert view['metrics']['tests']['total'] == 4
campaign.evidence.invalidate(fact_id, 'retracted fixture', 'operator')
assert coverage.snapshot()['metrics']['tests']['covered'] == 0
```

- [ ] Run focused coverage and existing boundary/evidence/runtime tests in pinned offline Linux Docker, commit, freeze exact public output contract in the task report, and resolve independent review findings.

## Task 2: Visual workspace, read-only local API and repeatable demo

**Files:** new lib/pentest/{dashboard,dashboard_demo}.py, lib/pentest/web/{index.html,app.css,app.js}; small cli.py registration; tests/test_pentest_dashboard.py; examples/pentest/coverage-plan.json; docs/COVERAGE-CONSOLE.md; README links; existing CI extends only appropriate offline tests/demo commands.

**Interfaces:** Trusted operator commands under `python lib/sapper.py pentest`:

```text
coverage-import --state DIR --plan FILE --actor NAME
coverage-assess --state DIR --asset-id ID --check-id ID --outcome completed|not_applicable --actor NAME --note TEXT [--fact-id ID ...]
coverage-status --state DIR
dashboard --state DIR --port 0 [--container-listen]
dashboard-export --state DIR --output FILE
dashboard-demo --output FILE
```

- [ ] RED real-entrypoint/API tests: no-traceback malformed input, coverage plan/assessment commands, default loopback binding, explicit Docker-only listener validation, Host/Origin/session capability checks, GET-only whitelist, no traversal, no mutation after page/API refresh, no body or path leakage, escaped malicious metadata, corrupt-state errors and expired-evidence refresh.
- [ ] Build a Chinese light workspace with project/refresh header, two separately explained coverage metrics, backlog/evidence gaps, asset tree, asset×check matrix, task timeline, worker states, detail pane and findings/review status. Implement search, status/type filters, tabs, drill-down, refresh, stale/error state and snapshot download. Maintain keyboard/accessibility labels and responsive layout.
- [ ] Implement local viewer with stdlib ThreadingHTTPServer bound by default to 127.0.0.1 (explicit Docker-only mode binds inside an internal network, with a PowerShell launcher publishing only host 127.0.0.1), exact route/Host checks, unguessable viewer-only capability for API, no CORS, no-store, restrictive CSP and no-referrer. Do not expose write/run/approve endpoints. Static files are fixed packaged assets, never arbitrary paths.
- [ ] Export standalone HTML embedding safely escaped snapshot data and local application assets. It must open from file without a server or internet, with explicit captured-at/snapshot labeling. Provide a recorded demo replay with play/pause/step controls; frames come from actual deterministic loopback actions and snapshots, never fabricated successes.
- [ ] Demo covers planned but untested assets, queued/blocked work, running request, successful observation, manual assessment pending/completed, failed attempt, a justified not-applicable cell, later invalidated evidence, and all four roles. Only its own ephemeral local HTTP fixture is contacted. Capture a current state and a sequence of real snapshots; clean up processes, sockets and state.
- [ ] Real-browser verification using Playwright CLI: open exported demo, inspect desktop/mobile layout, filter matrix, select a cell/asset, inspect evidence, switch tabs, replay steps, verify no unexpected browser requests/errors and malicious labels remain inert. Parent owns screenshots and browser acceptance; implementer owns reusable backend tests and final report.
- [ ] Run full pinned offline Python3.12/3.13 suite plus existing demo/manual and new dashboard-demo. Resolve task and whole-branch review findings; publish the new branch/PR, verify CI, and save Chinese acceptance/handover plus a clickable offline HTML demo in outputs.

## Verification

All application tests run inside the established container flags: `--network none --cpus 2 --memory 512m --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp:rw,nosuid,nodev,size=128m`, source mounted read-only, no published target ports. Browser acceptance uses a local snapshot file or loopback-only viewer. The viewer never drives test traffic.

Pinned images remain `python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159` and `python:3.13-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb`. Baseline already verified:152 tests on both versions and GitHub CI; do not rerun unchanged baseline before work.

## Windows Docker viewer refinement

The selected development environment is Linux Docker on Windows. Binding only container loopback prevents normal published-port access. Keep native binding at 127.0.0.1 and add explicit Docker-only --container-listen for this deployment, requiring a fixed port. The provided launcher uses a dedicated internal network, read-only mount, and host-loopback publication; it never exposes a public host port. This is a local usability refinement, not execution authority. Browser acceptance must verify the real Windows endpoint and stale refresh behavior.
