# Protected operator service API

Task 3a direct Python contract, version 1 (2026-11-01). HTTP adapters and UI are a separate gate. Import `Workspace` from `pentest.workspace`; expected errors are `WorkspaceError` from `pentest.workspace_store` with safe `.code` and `.message`. No raw exception details, credentials, bodies, prompts or reasoning are returned. Names provide attribution; the future HTTP layer supplies authentication.

## Lifecycle and data access

`Workspace(root, *, models_root=None, models=None, resolver=None, clock=time.time, max_active=2)` takes trusted controller paths/injections, never HTTP fields. Linux `flock` exclusively owns the root until `close()`. Constructor performs no target, DNS or model calls. `.store` is the frozen WorkspaceStore API in [OPERATOR-DATA.md](OPERATOR-DATA.md); `.models` is ModelProfiles. Injected models/resolver are fixture/controller objects only. Default profiles live under root/models unless a separate protected models_root is supplied. Default maximum two simultaneous jobs; each run has one job and one RLock. Request/model I/O occurs outside that lock. Core target execution is sequential per run; the frozen parallel allowance remains an upper bound.

Use as a context manager or call `close()`. Close requests pause, waits at most 135 seconds for the currently bounded operations, and releases the root lock after all worker threads exit. It retains the lock and returns a safe conflict if a trusted injected implementation violates bounds. It neither refunds allowances nor restarts work. Public mutations reject a closed instance. `wait(run_id, timeout=30)` is a trusted test/controller helper, accepts 0..300 seconds, returns the run record after its job exits or raises TimeoutError; do not expose it as a blocking HTTP route.

## Run methods

| Method | Inputs and return | Effect |
|---|---|---|
| `prepare(draft_id, expected_revision)` | Store draft UUIDhex and strict revision; returns newly created public run record | Checks job capacity before creating a run; starts explicit preflight and planning asynchronously. |
| `snapshot(run_id)` | UUIDhex; public snapshot below | Read-only current provenance, no projection, recovery, model calls or target hits. Corruption raises a safe error. |
| `approve(run_id, plan_revision, action_ids, actor)` | Current strict positive plan revision; nonempty unique list of up to500 current action UUIDhex IDs; nonempty actor<=160; returns run record | Inactive run only. Grants exact core ledger approvals for pending actions; exact existing grants are reused. Stale revision/foreign IDs/invalid state denied. Zero target hits. |
| `start(run_id)` | Returns running run record | Inactive ready/awaiting_approval/completed run with eligible approved work; asynchronous execution. No implicit approval. |
| `pause(run_id)` | Returns run record | While a job is active: pause_requested until its current operation completes. Otherwise paused. |
| `resume(run_id)` | Returns running run record | Explicitly continues paused/blocked known remaining work or a known failed model turn. Failed initial planning retries on the same frozen run. Every actual retry is a new charged attempt. Completed target tasks never replay. |
| `cancel(run_id)` | Returns run record | Active job: cancel_requested then cancelled. Revokes remaining grants after the current bounded operation. No refund; no resume. |
| `message(run_id, data)` | Store message schema below; returns message record | Persists first, then dispatches typed effects. Never authorizes a target. |
| `report(run_id, format)` | format exactly markdown/html/json; returns UTF-8 text | Assembles fresh public report; no calls, grants or execution. |

Service statuses are preparing, awaiting_approval, ready, running, pause_requested, paused, cancel_requested, cancelled, blocked, completed, failed, needs_attention. Every run has `engagement_complete=false`. `completed` means the current planned batch finished, with manual/untested coverage still visible. A partial plan can finish its batch without covering all imported assets. `stop_reason` distinguishes exact approval, operator pause/cancel, model failure, execution budget/scope/dependency denial, restart and internal state failure. `blocked` is known recoverable work; `needs_attention` is uncertain outcome or incomplete/corrupt local state.

On startup, active run records become needs_attention and reserved model attempts become uncertain, permanently charged. Queued messages remain queued on this restart path. Resume of a restarted run marks its protected running workers lost and invokes core Watchdog reconciliation; a verified terminal receipt can finish its existing task without egress. Pending, unknown, unavailable receipts, uncertain model attempts and internal persistence failures block resume. There is no automatic replay. Cancel or create a new explicitly scoped run for unresolved outcomes; this API does not pretend to resolve uncertain model side effects.

## UI state/action mapping

| Current state | Appropriate next operator action |
|---|---|
| preparing/running | Poll snapshot; pause/cancel or send queued guidance. No approval while job active. |
| pause_requested/cancel_requested | Show request outstanding until bounded call completes; do not claim immediate stop. |
| awaiting_approval | Review current plan revision, approve explicit pending IDs, then start. An approved subset may execute. |
| ready | Start existing approved work, or approve additional pending IDs first. |
| paused | Approve pending IDs if needed, then resume eligible work; model-only guidance may create new pending actions without resuming execution. |
| blocked with model failure | Fix the referenced profile/context, then explicit resume for initial plan or pending analysis/review. A failed guidance message requires a new guidance request. Budgets/expiry cannot be reset. |
| blocked with execution allowance/dependency failure | Inspect limits and fact validity; resume only if the original frozen conditions can still allow remaining work. Otherwise cancel/new run. |
| completed | Inspect remaining coverage/manual gaps; create findings, request a new retest or guidance plan. New actions need approval and start. |
| needs_attention after restart | Explicit resume attempts protected receipt reconciliation only; unresolved unknown receipts or uncertain model attempts remain blocked. |
| needs_attention after internal persistence failure / failed / cancelled | Inspect safe diagnostics; no automatic retry. Cancelled is terminal. Internal incomplete state is not resumed through ordinary model retry. |

## Scope, plans and execution

Preflight derives exact enrolled origins from every frozen asset, skips excluded origins, resolves each included hostname once with <=5 seconds per host and <=30 seconds total, validates **all** answers, and freezes them. Scope authority is the whole origin, not only the initially listed paths. All-excluded scope fails visibly. Policy expiry is run creation plus frozen expiry_seconds; DNS or resume never extends it. Networks are constructed from /32 and /128 pins (the core may canonically collapse adjacent networks without adding addresses). Full pins remain public. The execution resolver validates all pins again, then returns a deterministic IPv4 peer if available, otherwise IPv6. No retry/fallback, fresh DNS, redirect following, credential injection or shell occurs.

Without a Commander profile, preparation explicitly makes one GET observation per included asset (HEAD if only HEAD allowed; no automatic action if tools empty). With a profile, validated model plans are mandatory; errors block, never fall back. Worker-role overrides select actual analysis/review profiles, otherwise the task default is used. Profile metadata/revision is recorded for the actual call. Full context includes the frozen draft, scope, prior consumed guidance, current queued guidance and bounded verified evidence; oversize context fails visibly without silently dropping text/assets.

Plan shape:

```text
{revision, source, summary, gaps, priority:[action_id], model_pending:null|{role,purpose,finding_id,message_ids},
 actions:[{id,asset_id,parent_asset_id,target,tool,role,description,risk,evidence_gap,
           check_id,timeout_seconds,max_bytes,depends_on,approval_id,finding_id}]}
```

Top-level snapshot.plan adds each action's derived `state`: pending, approved, queued, running, succeeded or failed. Run status and policy expiry additionally govern whether an action can start. IDs, request limits, provenance dependencies and grants are controller fields; model output cannot set them. Plans append actions and preserve prior actions/approvals/receipts. Revision changes require a fresh displayed revision for pending approvals. Model new paths create derived endpoint assets with an original parent. Caps:500 cumulative run actions,500 total coverage assets,50 checks,5000 cells,20 attempts per cell. Exceeding a cap fails the entire proposal before effects. Every imported asset remains visible, including excluded and unplanned ones. Included assets have separate GET/HEAD observation cells and manual security-assessment cells.

The runner lazily submits the next selected approved task. Explicit pending priorities take precedence; otherwise existing risk/coverage/evidence-gap/cost ranking applies. Core Campaign, Broker, Ledger, EvidenceStore, CoverageStore and Watchdog remain authoritative. Commander is persistent; Scout/Soldier/General are real protected logical workers. The historical core `adapter='mock'` means inert JSON proposal transport, not a claim that external model agents are simulated. Actual model attempts appear separately in model_calls; no fake agent processes exist.

Budget usage is **reserved allowance**, including maximum bytes/time for each attempted request; failures/cancellation do not refund it. Retests share the original policy, expiry and persistent target/model budgets. A missing approval, invalid dependency or exhausted allowance prevents dispatch.

## Messages

`data` is exactly the WorkspaceStore message schema: required `request_id` UUIDhex, `kind` guidance/prioritize/retest, `text`1..4000; optional `action_ids=[]` and `finding_id=null`. Identical request retries return the same queued/terminal record; different payload for that request conflicts. `queued`, `consumed`, `failed` are distinct. Returned `consumer` and `result` describe the actual effect.

- guidance requires no action_ids/finding_id. Configured Commander receives it in a **plan** turn, with current observations and all previously consumed guidance history. New validated actions are appended pending approval with conservative dependencies on every valid observation in that context. A completed/paused run may run this model-only job; it performs zero target requests. During execution, guidance waits for a separate planning turn, never gets consumed merely by observation analysis. Without Commander profile it is consumed by `operator-record` with a truthful recorded-only result. After model/state failure, unsent queued messages explicitly fail; they are not claimed to have reached a model. Submit a new request after correction. A retry of an already failed message never replays it.
- prioritize requires nonempty pending/approved action_ids and no finding_id. It updates pending selection only; no approval or immutable core task is rewritten. Consumed by scheduler or explicitly failed.
- retest requires finding_id and empty action_ids on an inactive run. It appends a General exact-target independent observation linked to the finding, with empty original-claim dependencies to preserve independent evidence. It becomes awaiting_approval. Original evidence and previous attempts remain. A new approval and start are required. Message consumer identifies the new retest action.

Known model errors preserve `plan.model_pending` (or null plan for initial planning), allowing explicit resume after profile correction without target replay. A failed guidance turn with message IDs requires a new explicit guidance message; failed messages are never silently re-reserved. Profile/context prechecks that fail before dispatch consume no model attempt; reserved failed/uncertain calls count permanently. Call result is prechecked <=32768 UTF-8 bytes before plan/finding/suggestion side effects. Large native plan/finding content uses its native records and compact result references; oversized review suggestions or analysis summary/gaps fail visibly, never truncate or apply partially.

## Findings, coverage and review

`create_finding(run_id,data)` accepts exactly fact_id,title,severity,reporter,description,impact,reproduction,remediation,cwe,operator_note. All fields are required by this service; cwe/operator_note may be empty. Four narratives are nonempty<=8000; title/reporter follow core <=1024 bounds; severity info/low/medium/high/critical; fact must be a current valid actual protected observation. Returns full case. It creates only candidate status. Model candidates use reporter `model:<profile-id>:<call-id>` and source event/call references. Core finding then narrative are separate durable writes; failure exposes `narrative_incomplete=true` and a finding_narrative_incomplete event, never false confirmation. Internal job persistence failures become needs_attention.

`update_finding(run_id,finding_id,narrative,expected_revision)` changes only the six narrative fields and returns full case. Existing narrative requires current revision; missing narrative can be repaired with expected_revision=None. `finding(run_id,finding_id)` returns the same full case shape used by snapshot. Narrative history remains available.

`review_finding(run_id,finding_id,*,reviewer,evidence_id,outcome,note)` invokes authoritative EvidenceStore.review; outcome confirmed/rejected/inconclusive. Reviewer must differ from original reporter and fact creators. Review evidence must have a later independent receipt and match every original exact target. Returns current full case. A General retest's actual model review can only produce `review_suggestions`, visibly suggested/unapplied. It never invokes this method automatically; suggested `confirmed` is not finding status. Suggestions show current finding status and whether their independent evidence still has valid observation provenance.

`invalidate_fact(run_id,fact_id,*,actor,reason)` invokes transitive core invalidation and returns affected fact IDs. Findings become stale and dependent planned actions cannot dispatch. `assess_coverage(run_id,*,asset_id,check_id,outcome,actor,note,fact_ids)` delegates the core assessment API and returns its assessment. outcome is **completed** or **not_applicable**; only manual checks accept completed, with exact valid matching evidence. A coverage plan revision establishes a new assessment context; old assessments remain in coverage.history rather than silently transferring to changed plans.

Full case fields: core id,fact_id,title,severity,reporter,created_at,status,reviews,invalid_reasons plus target,description,impact,reproduction,remediation,cwe,operator_note,narrative_revision,narrative_incomplete,narrative_history,evidence. Each evidence record is exactly id,receipt_id,target,tool,status,http_status,started_at,finished_at,body_sha256,excerpt. Excerpt<=4096 characters uses common credential/cookie masking; it is neither full HTTP traffic nor universal secret/PII removal. Arbitrary sensitive prose may remain.

## Snapshot and report shape

```text
{version:1, generated_at, run:<full public store run>, draft:<frozen draft>,
 plan:<derived public plan|null>, scope, policy,
 runtime:{commander,workers,tasks,ranking,ledger,evidence:{facts,evidence,findings},audit,...},
 budget:{limits:<all frozen budgets>,usage:{requests,bytes,seconds},model_calls:[<call records>]},
 coverage:{version,configured,captured_at,plan,metrics,assets,checks,cells,history},
 findings:[<full cases>],messages:[<message records>],model_calls:[<call records>],
 review_suggestions:[{finding_id,evidence_id,outcome,note,call_id,state:'suggested',
                     evidence_current_valid,current_finding_status}],
 events:[<most recent <=200 events>],event_cursor:<latest global sequence>,
 observations:[{fact_id,valid,description,evidence:[<public evidence>]}]}
```

`runtime` is a read-only core snapshot without server/graph paths or raw bodies. Receipts/evidence are verified even if no finding uses them. Expired/revoked facts and cases remain visible as invalid/stale; integrity corruption raises WorkspaceError rather than exporting missing/false evidence. Before policy initialization, runtime/coverage have empty activity sections and original assets remain visible. The event cursor is a polling watermark; snapshot always returns the most recent bounded events. Clients must not treat absent older events as no prior work.

Reports whitelist task/run/budget/coverage/findings/messages/events, plus scope/plan/model_calls/review_suggestions. Markdown and HTML explicitly include plan summary/gaps and unapplied model review advice with call/evidence references. JSON preserves the entire service-assembled report, not arbitrary private controller objects. Rendering escapes untrusted content and retains literal evidence. Reports are generated fresh from current validity; HTTP observation coverage never establishes absence of vulnerabilities or engagement acceptance.
