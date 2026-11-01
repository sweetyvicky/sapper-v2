# Model configuration

`pentest.models.ModelProfiles(root: Path, *, allow_http_loopback=False)` stores
operator-selected OpenAI-compatible Chat Completions profiles. Saving, listing,
editing and deleting profiles makes no network request. Only `complete()` and
`test()` call the explicitly selected profile. There is no retry or fallback.

## Public interface

- `list() -> list[dict]` and `get(profile_id) -> dict` return public metadata only.
- `save(data, *, profile_id=None) -> dict` creates or replaces a profile. Supply
  name, provider, base_url and model. Optional timeout_seconds defaults to 45
  (integer 5–120), max_output_tokens to 2048 (integer 64–8192), and api_key supplies
  a new secret. Unknown fields, booleans in integer fields and invalid types fail.
- `delete(profile_id)` removes the profile and its active key file.
- `complete(profile_id, messages, *, max_output_tokens=None)` returns only
  `{content, usage, model}`. An override must be 64–8192 and cannot increase the
  saved output limit. Messages contain exactly role and string content; roles
  are system/user/assistant. Limit: 64 messages, 262144 characters per content,
  1 MiB serialized UTF-8 request and 1 MiB response.
- `test(profile_id)` uses a minimal prompt with a 64-token cap and returns
  `{status: "ok", latency_ms, usage}` without generated text. Failure raises the
  same safe `ModelError` as completion; callers display its code/message.

Public metadata fields are id, name, provider, base_url, model, timeout_seconds,
max_output_tokens, has_key, revision, created_at and updated_at. IDs are canonical
lowercase hyphenated UUID strings. Revisions start at 1 and increment per save;
timestamps are Unix seconds. Passing public metadata wholesale to save is
rejected: supply only the supported editable fields. The saved key never appears
in metadata or connection-test output. Completion also redacts an exact echo of
the active key in returned content or model name.

## Endpoints and key binding

The editable `PRESETS` mapping has provider keys deepseek/glm/longcat/custom and
`base_url` values. Official endpoint documentation checked 2026-11-01:

| Provider | Base URL | Documentation |
| --- | --- | --- |
| DeepSeek | https://api.deepseek.com | [Official API documentation](https://api-docs.deepseek.com/) |
| GLM | https://open.bigmodel.cn/api/paas/v4 | [OpenAI compatibility](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction) |
| LongCat | https://api.longcat.chat/openai/v1 | [Official API documentation](https://longcat.chat/platform/docs/APIDocs.html) |

Model IDs remain operator-editable. Each base URL gets exactly
`/chat/completions` appended after removing trailing slashes. Canonicalization
lowercases/IDNA-encodes hosts and removes the default port. HTTPS is required;
URL credentials, queries, fragments, control characters, backslashes and dot
segments are rejected. Only explicit fixture mode permits HTTP with a numeric
loopback IP. It is not a production setting.

Omitting api_key or supplying an empty string retains a key only when both
provider and canonical endpoint are unchanged. Changes to either require a new
key. No endpoint can inherit a key from another profile.

## Transport and errors

A fixed Python child script handles one JSON-only request. It receives the key
through a private stdin pipe, never through command arguments or environment
variables. Parent-enforced wall time covers child startup, DNS, TLS, connection
and continuous response reads. Timeout kills and reaps the child; socket idle
timeouts alone are not the boundary. TLS verification stays enabled. Proxy
environment settings and redirects are disabled. No streaming, tools, function
calls, browsing or response_format assumption is used.

`ModelError.code` is a static classified cause: invalid_profile, invalid_fields,
invalid_endpoint, key_required, storage_error, invalid_messages,
invalid_output_limit, timeout, transport_error, tls_error, redirect_refused,
response_too_large, invalid_response or http_NNN. Messages never contain provider
bodies, credentials, model text or internal tracebacks. Usage retains only
prompt_tokens/completion_tokens/total_tokens when present; each must be a
nonnegative integer at most 2^63−1. Reasoning and arbitrary response fields are
discarded. Callers must treat content as untrusted data, never as authorization.

## Local secret protection and limitations

Public metadata resides in `root/models.sqlite3`. Independent UUID-named key
files reside in `root/secrets`; this directory can be a separately protected
persistent mount. POSIX directory/file permissions are 0700/0600. Keys are plain
local files, **not encrypted**. Windows deployment must restrict the secret
directory ACL to the operator/service account; Python's POSIX mode flags do not
establish Windows ACL protection. Never export or serve the secret directory.
Back it up only under the same access protection as credentials.

SQLite transactions publish metadata only after writing a replacement key.
An abrupt process/system crash between those steps can leave an unused secret
file; it is never selected as a fallback. Operators should protect the entire
state tree from local modification. This module does not defend against an
attacker who already controls local state or the Python interpreter. It does
not impose provider concurrency or campaign model-call budgets: orchestration
must reserve budget before invoking it and avoid automatic retries of uncertain
calls. Task context and evidence excerpts passed to complete are sent to the
selected provider; saving configuration sends nothing.
