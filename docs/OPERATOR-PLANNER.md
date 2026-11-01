# Operator planner and DNS contract

Frozen for Task 3a planner/DNS integration, 2026-11-01. Standard library only.
`pentest.workspace_planner` exports `response_excerpt`, `prepare_call`,
`execute_call`, `validate_plan`, `validate_analysis`, `validate_review`.
Expected failures are safe `WorkspaceError(code, message)` values. No target
requests, approvals, authoritative findings/reviews or message acknowledgements
occur in this module.

## Prepare, execute, consume

```python
prepared = prepare_call(store, models, run, role='Commander', purpose='plan',
                        guidance=queued_guidance, observations=public_observations,
                        findings=(), clock=time.time)
result = execute_call(models, prepared)
```

Call `prepare_call` under the service per-run lock with current full run data.
It performs no network operation. Role selection uses `draft.role_profiles[role]`
then `draft.model_profile_id`; absent/unavailable configuration fails visibly.
The public profile must have a key, positive integer revision, timeout 5..120 and
output limit 64..8192. Run `policy.expires_at` must allow the entire profile timeout.
No-model mode is an explicit engine decision outside these functions.

The two Chat Completions messages contain a strict output schema/instructions and
one complete JSON context: `role,purpose,draft,scope,policy,guidance,observations,findings`.
The full frozen draft includes all original assets, goal, context, initial guidance,
exclusions, budgets and tools. Supplied queued guidance records are included whole.
All supplied guidance IDs are reserved together; accepted records must belong to
the run and have kind guidance/status queued, unique UUIDhex IDs and text1..4000.
No assets, text, cases or evidence are silently dropped. The request uses exactly
ModelProfiles serialization (`ensure_ascii=True`, whole body <=1MiB,
<=64 messages, content <=262144 characters each). Oversize contexts fail with a size
message before reservation. Local profile/expiry/context errors consume no call.

After all prechecks, `store.reserve_model_call` reserves the attempt. Returned
trusted ephemeral dictionary has `call,profile,messages,run,valid_fact_ids,
observations,findings`, with independent context copies. Never accept this object
from HTTP or expose it publicly: it contains the complete transient prompt.

Call `execute_call` outside the service lock. It invokes `models.complete` exactly
once with the frozen profile ID and `expected_revision=profile.revision`. The new
optional ModelProfiles argument accepts None for backward compatibility or a
strict positive int; mismatch raises safe `ModelError('profile_changed')` before
reading the key or starting transport. There is no retry/fallback. Result is
`{'proposal': validated_object, 'metadata': {'profile': public_profile,
'model': returned_model, 'usage': validated_usage}}`. Raw content and reasoning are
absent. Plan/analyze/guidance/review select their respective validators; guidance
uses the analysis schema.

After transport, the engine must reacquire its lock and recheck run state, current
facts, exact scope, provenance and persistence limits before applying proposals.
The engine owns action IDs/limits, derived coverage assets, candidate attribution,
source events, `finish_model_call` and exact-call `finish_message` acknowledgement.
Only acknowledge consumed after safe application; failure marks the call and its
participating messages failed. Crash reservations remain uncertain without retry
or refund. The planner performs no result persistence.

**Persistence size:** WorkspaceStore call results are <=32768 bytes, smaller than
accepted model proposals. The engine must choose a bounded result shape and
precheck serialization before side effects. Plans and candidate narratives have
separate native records; full review suggestions must fit their persisted call
result or fail visibly. Never truncate proposals or apply a partial result merely
to fit this limit.

## Strict model data

All validators accept <=2MiB UTF-8 JSON, optionally one complete lowercase `json`
or unlabelled triple-backtick fence. Duplicate keys, extra text, nonfinite numbers,
invalid Unicode, unsupported fields and nested executable/controller fields fail.
Every schema has nonempty summary<=8000 and gaps<=100, each nonempty<=1024;
multiline prose follows intake text/control rules. Results are fresh objects.

Plan schema is exactly `summary,gaps,actions`, <=500 actions. Each action has exactly
`asset_id,target,tool,role,description,risk,evidence_gap`. Asset IDs must reference
an original enrolled draft asset, and target must have that asset's exact canonical
origin. New paths/query strings on that origin are allowed. Role Scout/Soldier/
General, description1..1024 with no controls, finite non-bool risk0..10 and
finite non-bool evidence_gap0..1. Scope is frozen
`{origins,pinned,excluded_origins,denied_networks,enrollment:'whole-origin'}`.
Every address in the entire pinned mapping is checked against policy networks,
scope/policy denyCIDRs and numeric hard constraints, even for an empty plan.
A proposed host must have a nonempty pin and allowed/nonexcluded origin. A temporary
controller-only Action with policy request/response limits undergoes
`Policy.validate_action`; no temporary/action/approval ID is returned.

Analysis/guidance schema is exactly `summary,gaps,findings`, <=50 candidates.
Each candidate has exactly `fact_id,title,severity,description,impact,reproduction,
remediation,cwe,operator_note`. Fact ID must be in the supplied current valid list
(UUIDhex). Title1..1024 with no controls, severity info/low/medium/high/critical;
four required narratives1..8000 each; optional-value cwe<=80, operator_note<=4000.
No status, reporter, review, approval, provider or command field is accepted.
The engine creates candidates only, attributed to the exact model profile/call.

Observations have exactly `fact_id,valid,description,evidence`, <=10000 distinct
UUIDhex facts, strict bool valid, description1..8000. Evidence is <=10000 public
records per fact with exactly `id,receipt_id,target,tool,status,http_status,
started_at,finished_at,body_sha256,excerpt`. IDs/receipt IDs1..128, canonical exact
URL, supported HTTP tool, bounded status text, HTTP status null or100..599,
finite ordered timestamps, lowercase SHA256 and sanitized excerpt<=4096. A valid
fact requires at least one evidence record. No raw body or arbitrary fields.
Only entries explicitly `valid=True` contribute valid fact IDs. The engine
verifies actual receipt/fact integrity before supplying these public records.

Review schema is exactly `summary,gaps,review_suggestions`, <=100 suggestions.
Each suggestion has exactly `finding_id,evidence_id,outcome,note`; outcome confirmed/
rejected/inconclusive and nonempty note<=1024 without controls. Findings are
explicit supplied full cases with UUIDhex ID and original `evidence` metadata.
Suggested evidence must come from a supplied valid observation and match every
original case evidence target exactly, differ from every original receipt and
start at/after all original finished_at timestamps. Missing originals,
foreign/stale supplied evidence and multi-target claims fail. Positive confirmation
advice additionally needs nonstale case status, empty invalid_reasons and a current
valid supplied backing fact; rejected/inconclusive cases may be reconsidered.

These are advisory suggestions only. The engine must expose them as suggested/
unapplied; this module never calls EvidenceStore.review. Only explicit operator
review applies authoritative independent-actor/provenance checks.

## Bounded DNS and excerpts

`pentest.dns_resolve.resolve_host(host, *, timeout=5.0) -> list[str]` accepts a
strict hostname or numeric IP and positive finite timeout<=5 seconds. Numeric
addresses bypass the child. Otherwise it invokes the fixed absolute module script
with the current Python interpreter and `-I`, no shell/injectable executable.
Host passes through bounded stdin JSON, not executable arguments. Child environment
is empty on Linux; Windows preserves only SYSTEMROOT/WINDIR. No credentials/proxy
variables are inherited. Fixed child emits at most64 addresses/8192 JSON bytes;
parent uses a temporary-file sink and reads at most8193 bytes, rejecting excess.
Whole-call timeout includes child startup and DNS; timeout kills/reaps the child.
Duplicates collapse after validation. Empty/excessive/malformed answers and
unspecified, mapped, multicast or scoped addresses fail the entire operation.
No network occurs at import. The service owns total preflight timing (<=30s),
per-host remaining deadlines, denyCIDR validation for all addresses and /32 or /128
policy pins. It skips excluded origins and deduplicates origin/hostname resolution.

`response_excerpt(body: bytes)` inspects a bounded 65536-byte prefix, replaces
invalid UTF-8/unsafe controls and masks common Authorization/Bearer, Cookie/
Set-Cookie, API key, password, secret, access/refresh/session/CSRF token text/JSON
forms before the final <=4096-character cut. This is common-pattern masking,
not universal secret/PII redaction. Arbitrary sensitive prose and unusual encodings
can remain. Engine/views own receipt verification and protected body selection.

## Offline verification boundary

Tests use synthetic keys, a real isolated loopback Chat Completions fixture,
localhost-only DNS and numeric fixtures. Trusted test substitutions run a fixed
fixture child to simulate malformed/oversize answers or blocked DNS; production
has no configurable command hook. No external providers, targets or DNS are used.
