# Synthetic operator browser fixture v1

This trusted test entry point runs the actual protected Workspace, HTTP adapter,
ModelProfiles transport, Broker, ledger, evidence and coverage. Browser journeys
must use the real authenticated HTTP API and resulting receipts. Only the target
and Chat Completions provider responses are synthetic. No real keys, providers,
targets or external DNS belong in this environment.

The source is a live **read-only** bind mount: later UI files appear immediately.
This is a browser development fixture, not an immutable production deployment.
Workspace and model state persist at `/state/workspace` and `/state/models`.
Independent fixture counters persist at `/state/fixture` across process restarts.

## Lifecycle on Windows 11 / PowerShell 7

Run from the repository root. Choose a new dedicated absolute directory for a new
scenario. The helper refuses nonempty unowned homes and never resets stored data.
The default alternate port is 8876; 8765 is forbidden and remains unrelated.

```powershell
$fixtureHome = 'C:\absolute\path\operator-browser-fixture'
& .\tests\browser\operator-workspace-fixture.ps1 -Action Start -FixtureHome $fixtureHome
& .\tests\browser\operator-workspace-fixture.ps1 -Action Status -FixtureHome $fixtureHome
& .\tests\browser\operator-workspace-fixture.ps1 -Action Arm -FixtureHome $fixtureHome
& .\tests\browser\operator-workspace-fixture.ps1 -Action Release -FixtureHome $fixtureHome
& .\tests\browser\operator-workspace-fixture.ps1 -Action FailNext -Purpose plan -FixtureHome $fixtureHome
& .\tests\browser\operator-workspace-fixture.ps1 -Action Restart -FixtureHome $fixtureHome
& .\tests\browser\operator-workspace-fixture.ps1 -Action Stop -FixtureHome $fixtureHome
```

`Start -Port 8877` selects an alternate port when first creating a home. Later
commands use the stored port. Stop retains both containers, dedicated labelled
networks and all state. Start reuses the same owned resources. Lifecycle commands
verify exact resource IDs, labels, home/source, mounts, port and resource bounds
before operating. Do not manually reuse these resources for other work.

The helper uses the pinned Linux image
`python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159`.
The application container has only a dedicated `--internal` bridge, two CPUs, 1 GiB RAM,
128 PIDs, dropped capabilities, no-new-privileges, read-only root and source,
writable dedicated state and `/tmp` tmpfs. No Docker socket, host network or
privileged container is provided. A second relay container joins that internal
bridge and a separate owned ordinary ingress bridge. Only the relay publishes
`127.0.0.1:<port>:<port>`. It has 0.5 CPU, 128 MiB RAM, 64 PIDs, the same capability,
read-only-root and tmpfs restrictions, and only a read-only relay source file
mount. It has no state/model mount or Docker socket. The helper derives a numeric
application peer from owned-network inspection, assigns it to the application,
and verifies the actual attachment/IP before operating. Relay forwards opaque
TCP to only that peer and port, without DNS, URL routing or traffic/header/token
logging. It allows eight connections, 64 KiB pending buffers per direction,
32 MiB total transfer per connection, a five-second connect timeout and a
150-second total connection deadline (long enough for the 120-second provider
test bound). Application authentication and CSRF checks see the original bytes.

Docker Engine 29.8 suppressed effective port publication for the tested container
connected solely to an internal bridge. This behavior is also described in the
[Moby discussion](https://github.com/moby/moby/discussions/53256); see Docker's
[port publishing documentation](https://docs.docker.com/engine/network/port-publishing/).
The relay preserves the application's internal network while giving the host
browser a loopback entry point. **The relay has ordinary bridge egress capability**;
its program forwards only to the fixed app peer. Internal networking does not
imply total OS egress isolation or isolation from the host gateway. Fixture target
and model calls use loopback inside the application container.

## Authentication and private files

Ordinary helper/process output includes only the safe local origin. To open a new
browser session, read the complete private URL from
`<FixtureHome>\state\fixture\bootstrap.url` and navigate to it without printing
it, logging it, capturing the fragment in screenshots or adding it to reports.
The UI exchanges the fragment for the real HttpOnly cookie and in-memory CSRF
token. Production Host, Origin, Cookie and CSRF checks remain enabled.
Restart creates a new bootstrap/cookie/CSRF identity and invalidates the old one.

`Status` proves a real authenticated session plus inert reads of session, models
and tasks, comparing fixture counters before and after. Readiness does not create
profiles, drafts, runs, approvals, provider calls or target hits. Restart never
automatically replays target/model work. The ordinary service restart semantics
still apply to interrupted work; do not infer a clean result from a forced stop.

## Frozen files and schema

All JSON is UTF-8. These are trusted test files, **not production HTTP routes**.

| File under fixture home | Contract |
| --- | --- |
| `fixture-owner.json` | Version 2; owner UUIDhex, absolute home/source, pinned image, port, numeric peer, and `internal`, `ingress`, `app`, `relay` each `{name,id}`. Lifecycle ownership record. |
| `state/fixture/bootstrap.url` | Private current-process bootstrap URL; removed on clean stop. |
| `state/fixture/ready.json` | `{version:1,generation,authenticated:true,inert:true}`; removed on clean stop. |
| `state/fixture/metadata.json` | Safe metadata shape below; synthetic key only. |
| `state/fixture/records.json` | Durable real target hits, actual model contexts and emitted fact IDs. Synthetic test data only. |
| `state/fixture/control.json` | Helper-written `{id:UUIDhex,command:arm\|release\|fail_next,purpose:null\|purpose}`. |
| `state/fixture/control-ack.json` | `{id:UUIDhex,ok:true}` for the consumed control. Old commands are removed at startup. |

Metadata schema:

```text
{version:1, origin, generation,
 target_origin, model_good_base, model_bad_base, synthetic_key,
 targets:{alpha,beta,slow,guided,failure},
 counts:{target_total,model_total,
         target_by_path:{'/alpha','/beta','/slow','/guided','/failure'},
         model_by_purpose:{probe,plan,analyze,guidance,review}},
 barrier:{armed:boolean,pending:boolean}, fail_next:null|purpose}
```

Records schema:

```text
{version:1,generation,
 target_hits:[{sequence,generation,method:'GET'|'HEAD',path,status,at}],
 model_calls:[{sequence,generation,purpose,context:null|actualPlannerContext,
               model,status,at}],
 emitted_fact_ids:[actualUUIDhex],guided_run_ids:[actualRunUUIDhex]}
```

Sequences/counters grow across restarts, including target/provider failures.
Unknown target paths are counted as `__rejected__` with 404; they do not accept
external URL parameters or redirect. No Authorization headers or arbitrary input
keys are recorded. Planner contexts preserve actual draft/scope/policy,
observations/findings and current guidance/history IDs/text, so use synthetic
browser input only. Emitted fact IDs prevent repeated candidates for the same
actual fact; a new independent alpha fact can produce its own candidate.

## Synthetic inputs and expected browser behavior

Target origin is fixed **inside the container** at `http://127.0.0.1:9551`.
The provider accepts only `sapper-browser-synthetic-key-only`, with good base
`http://127.0.0.1:9552/good` and failing base `http://127.0.0.1:9552/bad`.
Use provider `custom`, model `fixture-model`, timeout 5 seconds and output limit
2048. Saving a profile does not call the provider. Explicit connection testing
uses the real `Reply OK.` probe; `/bad` returns finite 429 with a synthetic marker
in its body to test that safe UI errors do not expose provider response bodies.

The canonical browser task enrolls `/alpha` and `/beta`, allows `http_get` and
`http_head`, sets `max_request_seconds:30`, `max_response_bytes:8192` and budgets
`{requests:30,bytes:1048576,seconds:600,parallel:1,model_calls:40}`. Default expiry
3600 seconds is sufficient. The slow journey must retain at least 30 seconds of
visible time allowance for each remaining request. Import `/slow` for barrier
journeys and `/failure` for a finite 503 target result.

Initial preparation uses real model context and returns Scout/Soldier actions for
the enrolled fixed paths, synthetic summary and manual gaps, all pending. Prepare
and approval cause zero target hits. Explicit start executes approved work and
creates real receipts. Alpha returns the explicit synthetic exposure marker and
literal `<script>`/event-handler markup; the UI must show escaped evidence.
Analysis proposes a complete CWE-200 candidate using the actual valid alpha fact.

Guidance containing `/guided` proposes one new pending `/guided` action per run
when it has not been observed; pending/prior actions are not repeated. Guidance uses real
Commander planning, records current IDs/text and later consumed history, and
does not authorize target hits. Approve the new displayed revision and start.
Other guidance records context with an empty additional action list.

Retest a candidate through the real message API. It appends General's exact same
alpha target, requiring its own approval/start. A genuinely later different
same-target receipt produces an unapplied advisory suggestion. The original
finding remains candidate until explicit authoritative operator review.

`Arm` makes the next slow GET/HEAD wait for `Release`, up to 25 seconds.
`metadata.barrier.pending` proves it entered. Pause/cancel can therefore be shown
as requested until release. Stop releases and joins the owned target thread.
`FailNext` accepts only `probe`, `plan`, `analyze`, `guidance` or `review`; the next
matching real provider call returns 429 once. No arbitrary commands/URLs exist.
Service guidance planning uses purpose `plan`; purpose `guidance` is reserved
for callers actually using that supported planner schema.

## Focused verification

```powershell
docker run --rm --network none --mount "type=bind,source=$((Get-Location).Path),target=/src,readonly" --workdir /src --env PYTHONDONTWRITEBYTECODE=1 python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 python -W error::ResourceWarning -m unittest discover -s tests -p test_operator_fixture.py -v
```

The focused tests use real protected HTTP requests for profile/draft/preparation,
zero-hit planning, explicit approvals/start, receipts/candidates, guidance/history,
independent retest advice, bounded barrier/release, provider failure and durable
restart without replay. No UI selectors, screenshots, renderer or production
deployment are part of this fixture slice.
