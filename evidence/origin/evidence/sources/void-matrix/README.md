# Cross-Vendor Semantic Void Matrix

This package implements a deterministic, closed, cross-vendor experiment for
eliciting, classifying, preserving, verifying, and summarizing Semantic Void
observations.

## Canonical definition

> A Void is a model execution returning a successful provider response with
> exactly zero visible UTF-8 output bytes. Provider termination metadata
> determines its subtype. Explicit refusals, safety blocks, tool-mediated
> executions, and transport, protocol, billing, quota, rate-limit, and
> infrastructure failures are distinct non-Void outcomes.

## Void taxonomy

| Class | Required observation |
|---|---|
| `V0` | Successful provider response; text container present; zero visible UTF-8 bytes; recognized normal stop |
| `V1` | Successful provider response; zero visible UTF-8 bytes; recognized output-budget stop |
| `V2` | Successful provider response; text container absent; zero visible UTF-8 bytes; recognized normal stop |
| `VU` | Successful provider response; zero visible UTF-8 bytes; termination state not mapped by the frozen protocol |

All four classes retain Void status. Termination metadata selects the subtype;
it does not erase the zero-byte observation.

## Distinct non-Void outcomes

| Class | Outcome |
|---|---|
| `NV` | Nonempty near-Void output, including whitespace, invisible code points, or ellipsis forms |
| `R` | Nonempty visible response |
| `RF` | Explicit provider or model refusal |
| `SB` | Provider safety block |
| `TC` | Tool-mediated or function-call execution |
| `BE` | Non-successful provider response reporting an output-budget error |
| `QE` | Billing, credit, or quota exhaustion |
| `PI` | Protocol or request-shape incompatibility |
| `E` | Transport, rate-limit, server, non-JSON, or infrastructure failure after configured retry handling |

Classification uses the raw response bytes, response structure, HTTP status,
and provider termination metadata. The complete raw provider response is
retained. No claim about an internal model mechanism follows from a class.

## Closed model allowlist

The frozen schedule is generated only from the source-controlled allowlist:

| Provider | Model identifier |
|---|---|
| OpenAI | `gpt-4-0613` |
| OpenAI | `gpt-5.2-2025-12-11` |
| OpenAI | `gpt-5.5-2026-04-23` |
| OpenAI | `gpt-5.6-luna` |
| OpenAI | `gpt-5.6-sol` |
| OpenAI | `gpt-5.6-terra` |
| Anthropic | `claude-opus-4-6` |
| Anthropic | `claude-fable-5` |
| Anthropic | `claude-opus-5` |
| Google | `gemini-3.5-flash` |
| Moonshot AI | `kimi-k3` |

Provider inventory discovery cannot add models to the schedule. Changing the
allowlist requires changing the source before the definitive freeze.

## Evidence guarantees

- The scheduled slot universe is regenerated deterministically from frozen
  protocol, prompt, model, and public-seed inputs.
- Slots cannot be inserted, removed, or reordered after scheduling without
  invalidating verification.
- Every attempt and complete raw response is retained.
- An append-only SHA-256 event chain serializes concurrent completions.
- Verification independently reconstructs every request and rejects incomplete
  attempts, orphan raw responses, hash mismatches, stale summaries, and changed
  event-chain state.
- Summary outputs report total Voids and separate totals for normal-stop,
  budget-stop, and unresolved-termination Void subtypes.
- Secrets are injected only into in-memory request headers. Persisted public
  request records contain `REDACTED`.

The full allowlist produces 31,430 deterministic confirmatory slots under the
current frozen protocol construction.

## Network boundary

These commands make zero live provider calls:

```bash
python3 void_matrix.py --root ./study init
python3 void_matrix.py --root ./study self-test
python3 tests/test_async_runner.py -v
python3 void_matrix.py --root ./study validate
python3 void_matrix.py --root ./study freeze
python3 void_matrix.py --root ./study schedule \
  --profile confirmatory \
  --seed "PUBLIC-PREREGISTERED-SEED"
python3 void_matrix.py --root ./study verify
python3 void_matrix.py --root ./study summarize
```

Only `inventory`, `preflight`, and `run` contact provider APIs.

## Credentials

Provide each credential directly or through an explicitly configured key file:

| Provider | Direct variable | Optional key-file variable |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `OPENAI_API_KEY_FILE` |
| Anthropic | `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY_FILE` |
| Google | `GEMINI_API_KEY` | `GEMINI_API_KEY_FILE` |
| Moonshot AI | `MOONSHOT_API_KEY` | `MOONSHOT_API_KEY_FILE` |

## Kimi K3 request contract

- Endpoint: `https://api.moonshot.ai/v1/chat/completions`
- Authentication: `Authorization: Bearer $MOONSHOT_API_KEY`
- Model: `kimi-k3`
- Output-cap field: `max_completion_tokens`
- Reasoning effort: omitted, preserving the documented provider default
- Fixed sampling fields: omitted, preserving documented provider defaults
- Provider concurrency ceiling: eight requests

`message.content` is the visible-output channel.
`message.reasoning_content` is measured separately and never counted as visible
output. The instrument records its presence, UTF-8 byte length, code-point
length, SHA-256, usage, finish reason, returned model identifier, response
identifier, and system fingerprint.

## Definitive execution sequence

```bash
python3 void_matrix.py --root ./study inventory
python3 void_matrix.py --root ./study preflight
python3 void_matrix.py --root ./study validate \
  --require-models --require-preflight
python3 void_matrix.py --root ./study freeze
python3 void_matrix.py --root ./study schedule \
  --profile confirmatory \
  --seed "PUBLIC-PREREGISTERED-SEED"
python3 void_matrix.py --root ./study run --all-blocks --workers 100
python3 void_matrix.py --root ./study verify --require-complete
python3 void_matrix.py --root ./study summarize
```

The definitive freeze requires successful first-party inventory capture and
capability preflight. Billing and quota exhaustion (QE) trigger a provider-level
pause and emit a `provider_paused` event without completing the slot or consuming
its infrastructure-retry allowance, allowing clean execution resumption after topping
up credentials. Retryable transport failures receive up to five bounded retries. Rate
limits honor Retry-After and activate a shared cooldown across that provider's worker
pool, preventing concurrent retry storms. Provider-specific concurrency limits
remain active inside the global worker pool.
