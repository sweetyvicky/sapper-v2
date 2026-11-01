# Local protected legion deployment implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install and exercise the already-developed protected Mock version on the user's Windows Docker, with persistent state and a real live coverage viewer.

**Architecture:** One bounded offline operator/exercise container initializes and drives actual Commander/Scout/Soldier/General runtime roles against its own loopback fixture. A separate read-only viewer publishes only host 127.0.0.1. The exercise container exits after finite checks; the viewer stays available. This is not the legacy live-model legion and does not spawn real model processes.

**Tech Stack:** PowerShell7, Docker Linux, pinned Python3.12 stdlib; existing protected CLI/runtime/coverage/viewer unchanged.

## Global Constraints

- Preserve master and prior feature branches; work only on feature/local-legion-deployment based on f525b07ae7304c14ed6854968890ca6f3fba4f79.
- No passwords, API keys, model calls, competition mode, host-network execution, external targets or general executable tools.
- Fixed Python image: python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159.
- Operator execution: --network none, 2 CPUs, 512MiB, pids128, cap-dropALL, no-new-privileges, read-only root and source, writable dedicated state/artifact directories, /tmp tmpfs128MiB. No Docker socket in any container.
- Viewer: same resource bounds, read-only source/state, dedicated ordinary bridge, publish127.0.0.1:8765:8765 by default. Viewer has network capability; do not claim egress isolation. It has no execution endpoint.
- New independent exercise per Replay; never reset/refund an old campaign or delete its files. State root inside containers must always be /state. Source snapshot is Git-committed and version recorded.
- Shutdown only containers/networks with this deployment's verified names, IDs and labels. Never remove unrelated resources. Preserve state on stop or failure. No automatic OS-start registration.
- Normal Start is idempotent; Open retrieves current viewer URL from its own logs, including per-process fragment credential. Do not publish that credential to GitHub/report logs. Status returns bounded metadata and actual exit status, not all environment variables.
- User-facing text must distinguish logical Mock roles from real model agents and finite exercise completion from engagement acceptance.

## Task 1: Persistent local installation, finite scenario and operator controls

**Files:**
- Create examples/pentest/local_legion.py: prepare and exercise subcommands using existing APIs; bounded synthetic loopback fixture, actual receipts/state, status/summary/export artifacts.
- Create scripts/local-legion.ps1: Start, Status, Open, Stop, Replay commands; deployment base passed as absolute -HomeDirectory (not $HOME), optional -Port8765, -NoBrowser for automation. Default deployment path may be under workspace work/local-legion, never user home root.
- Create tests/test_local_legion.py: meaningful real Linux integration of scenario prepare/exercise, repeated exercise rejection and records/stop boundaries. No new product algorithms.
- Create docs/LOCAL-DEPLOYMENT.md: exact Windows instructions, role semantics, lifecycle, source/state paths, limits and honest current unsupported live-model legion.

**Interfaces:**
`python examples/pentest/local_legion.py prepare --state /state --artifacts /artifacts` initializes fresh state only, exact127.0.0.1:18080 scope, finite policy <=30minutes and budgets <=8requests/8000bodybytes/32reservedseconds/parallel1. Spawn Scout/Soldier/General; import explicit Chinese plan with observation/manual/N-A/blocked cells.

`python examples/pentest/local_legion.py exercise --state /state --artifacts /artifacts --pace-seconds 2` reopens the prepared state, refuses repeated exercise, binds only127.0.0.1:18080, runs bounded controlled stages through runtime APIs, writes safe summary.json and standalone recorded coverage-demo.html. Pace bounded0..3seconds; no user target argument. All execution threads/servers close on completion/failure. Exit0 only if real assertions pass; emit machine-readable failure otherwise. Persistent state remains.

`pwsh -NoProfile -File scripts/local-legion.ps1 -Action Start -HomeDirectory ABSOLUTE_PATH -Port 8765 -NoBrowser` snapshots committed source to a release directory, prepares new state, starts persistent viewer and bounded exercise. It returns local viewer URL and owned resource info; waits only for viewer readiness, not indefinitely. Failures preserve diagnostic state, stop only partial owned resources. Ownership must survive stop/restart safely. Replay stops only its own current instance, creates new state/run ID and starts fresh; it must not overwrite the prior run's records. Stop/Status/Open do not require an active exercise process. Open may launch the default browser; Start default may open as requested by user deployment, -NoBrowser suppresses this.

**Required scenario evidence:** no-approval blocked with zero fixture hits; actual running state; Scout/Soldier/General each executes an approved observation (General can independently re-observe same target); a deliberately failed bounded response produces no successful fact; max-steps reason; remaining unapproved work stays blocked with engagement_complete=false; manual decision is explicitly synthetic; N/A separately counted; original-fact invalidation retracts coverage/related finding; Watchdog recovers one lost idle role without issuing new work; no extra request on repeated task ID. At most8actualrequests. Record assertions and per-role actual results; do not fabricate counters or directly write product SQLite rows.

- [ ] Write real integration acceptance before implementation; run and retain failing output proving missing scenario entrypoint.
- [ ] Implement scenario with existing initialize/reopen, Campaign.run_once/run_campaign, Ledger.approve, CoverageStore.import_plan/assess, EvidenceStore and dashboard snapshot/render_html. Implement deployment controls using native PowerShell arrays; no shell-built commands, destructive recursive operations or environment credential import.
- [ ] Run focused tests offline: `python -W error::ResourceWarning -m unittest discover -s tests -p test_local_legion.py -v`; verify artifact assertions, no replay of consumed campaign and clean fixture shutdown.
- [ ] Parse/check PowerShell, then exercise actual Start/Status/Stop/Start/Replay with an isolated agent-owned test deployment root and a non-user port; validate source tree ID, label ownership, network/mount/publication, finite exit0 and preserved previous state. Clean only test containers/networks; keep logs.
- [ ] Run complete existing+new suite once in pinned3.12 offline container, plus existing demos/manual/syntax as relevant; commit changed files; write full task report with commands/exitcounts/limitations.
- [ ] Independent task review of diff and evidence; repair findings and re-review. Final whole-change review after integration evidence.

## Parent deployment acceptance

- [ ] Actually deploy final committed source at workspace work/local-legion with host port8765 (choose free local port if unavailable; report exact URL).
- [ ] Use real browser to observe live metrics and four tabs; capture running and terminal evidence where feasible, actual screenshot, no console errors.
- [ ] Confirm no unauthenticated API snapshot, onlyloopback host publication, operator networknone, viewerreadonly state/source; verify finite exercise result and newsource binding.
- [ ] Provide outputs/local-deployment/ Chinese start/open/stop/replay entrypoints, usage and acceptance report, sanitized Docker metadata and exercise artifacts. Leave viewer running for user's local inspection; exercise must end. No autostart or real model usage.
- [ ] Publish support scripts on independent branch/PR with exact Git tree, preserve prior artifacts, record handover and unresolved live-model capability separately.
