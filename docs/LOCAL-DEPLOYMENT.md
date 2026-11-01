# Persistent local protected Mock deployment

This launcher runs the already implemented protected Mock controller. Commander is the deterministic trusted controller, and Scout, Soldier and General are logical roles executing approved bounded HTTP observations. These are not real model agents. Watchdog only restores a lost idle role; it never creates work or authority. Live-model legion, model API calls and competition mode are unsupported here.

On Windows 11 with PowerShell 7 and Docker Desktop in Linux-container mode, run from the repository after committing the deployment files:

```powershell
$deployment = Join-Path (Get-Location).Path 'work/local-legion'
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Start -HomeDirectory $deployment -Port 8765
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Status -HomeDirectory $deployment
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Open -HomeDirectory $deployment
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Stop -HomeDirectory $deployment
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Start -HomeDirectory $deployment
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Replay -HomeDirectory $deployment -Port 8765
```

Use an absolute dedicated `-HomeDirectory`. Add `-NoBrowser` to Start/Open/Replay for automation. Start is idempotent and waits only for viewer readiness. The finite exercise runs in the background for roughly twenty seconds. Status shows actual container state and exit code, plus the source commit/tree and retained directories. Exit code zero from Start indicates readiness, not exercise completion: inspect Status and `artifacts/summary.json`. A successful finite exercise explicitly has `exercise_complete=true` and `engagement_complete=false`; remaining unapproved work stays blocked. This is not engagement acceptance or a real vulnerability finding.

Open retrieves the current per-process fragment credential from its viewer's own logs. The full URL is private: do not publish it or paste it into reports. Status omits the credential. The viewer is read-only and has no execution endpoint. Its dedicated ordinary bridge has network capability; only its Windows publication is loopback-bound. It is not egress-isolated.

Stop only removes resources whose recorded ID, exact name, owner label and run label match this deployment. It preserves all state, artifacts and local diagnostic logs (which may include the private URL). It works after the exercise exits. Start after Stop opens the same retained state without rerunning a consumed exercise. Replay stops only the current owned instance and creates a new run, policy, ledger and budget. It never refunds an old campaign or overwrites prior records. An interrupted exercise remains consumed; use Replay. No OS-start registration is installed.

`deployment.json` records the current run; `owner.txt` is the persistent ownership marker. A file lock serializes operations. `releases/<commit>/` is extracted exclusively from Git-committed source. `runs/<run-id>/source.json` records the source commit, tree and pinned image. Each run has its own `state/` and `artifacts/` including `summary.json`, safe `status.json` and standalone `coverage-demo.html` recorded from actual snapshots. Preserve the deployment directory and ownership metadata for safe management. Treat it as trusted operator-owned storage.

Every container uses 2 CPUs, 512 MiB, 128 PIDs, all capabilities dropped, no-new-privileges, a read-only root and source, and a 128 MiB `/tmp` tmpfs. The image is `python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159`. No Docker socket or host networking is mounted. Prepare/exercise use `--network none`, writable dedicated `/state` and `/artifacts`. Viewer mounts `/state` read-only and publishes `127.0.0.1:8765:8765` by default. Container state always binds at `/state`, even if the Windows base path changes. The operator fixture binds only `127.0.0.1:18080` inside its isolated container. There is no user target option.

The policy expires after 30 minutes, caps parallelism at one, and allows at most eight requests, 8000 body bytes and 32 reserved seconds. The scenario makes four actual requests: three successful role observations and one deliberately oversized failure without a successful fact. It records zero-hit approval denial, an actual running snapshot, the step-limit stop, synthetic manual and separate N/A decisions, evidence invalidation, Watchdog recovery and duplicate-task refusal. `--pace-seconds` for direct exercise is finite and limited to 0–3; default 2. Failure emits machine-readable JSON, preserves state and closes all fixture/execution threads.

Direct Linux entrypoints (within the same resource boundaries) are:

```text
python examples/pentest/local_legion.py prepare --state /state --artifacts /artifacts
python examples/pentest/local_legion.py exercise --state /state --artifacts /artifacts --pace-seconds 2
```

A fresh empty state is required for prepare. Each exercise can start only once, including after failure. The launcher requires the pinned image locally or Docker's normal image acquisition; no credentials, passwords or environment secrets are imported by this script.
