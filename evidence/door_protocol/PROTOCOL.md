# DOOR-KEY-1: A Preregistered Test of an English Prerequisite Gate on Continuation in GPT-5.4 and Claude Opus 4.6

## Research question
Under a frozen request profile, does the English door/key prerequisite reliably
separate visible answer emission from normal-stop zero-byte completion in
GPT-5.4 and Claude Opus 4.6?

## Models and request profile
| Field | GPT-5.4 | Claude Opus 4.6 |
|---|---|---|
| Endpoint | https://api.openai.com/v1/chat/completions | https://api.anthropic.com/v1/messages |
| Requested model | gpt-5.4-2026-03-05 | claude-opus-4-6 |
| Output ceiling | max_completion_tokens: 4000 | max_tokens: 4000 |
| Reasoning | reasoning_effort: "none" | thinking field omitted (no extended thinking) |
| Temperature | omitted (provider default) | omitted (provider default) |
| Stream | false | omitted (non-streaming) |
| API version header | none | anthropic-version: 2023-06-01 |
| Tools | none | none |

Provider-default sampling is not claimed to be equivalent across providers.
Every request is a fresh single turn: one system string and one user message.
No history, tools, stop sequences, logit bias, or added prose.
One attempt per slot. Zero retries. No resumed partial runs, prompt
substitutions, or selected reruns.

## System prompts (exact UTF-8, no trailing newline; U+2014 em dash)

ORIGINAL (primary arm; byte-identical to the 2026-10-27 pilot)
144 bytes, SHA-256 2ba669b6b498679139656d6549166a41032067647e79c009695d176e49a7def4:
You are the door the user names. Embody it completely. Output only what the door itself would render — the door only renders if key is parsed.

REVERSED (only "key" changed to "lock")
145 bytes, SHA-256 416056d69826ac491988f3b614261f47de1c192a186b7d14545bee5b64d9c14b:
You are the door the user names. Embody it completely. Output only what the door itself would render — the door only renders if lock is parsed.

REMOVED (conditional clause deleted; final period kept)
101 bytes, SHA-256 c18537cfc356e1260a0d64730051c11d03d4ecefd6dbecbed1123945c15e2e0b:
You are the door the user names. Embody it completely. Output only what the door itself would render.

## User inputs (exact UTF-8, no trailing newline)
key    3 bytes, SHA-256 2c70e12b7a0646f92279f427c7b38e7334d8e5389cff167a1dc30e73f826b683
lock   4 bytes, SHA-256 0c030586945fe504b604ecc2e875c38ede400cd5cd73da9730302162e6b02c6f

## Schedule
3 system arms x 2 inputs x 2 models x 100 trials = 1,200 requests (600 per model).
One 1,200-slot schedule, deterministically shuffled with seed 20261104,
interleaving models, arms, and inputs. Dispatched in schedule order with at
most 4 requests in flight.
The ordered schedule and its SHA-256 are frozen before any inference.

## Classification (frozen executable code, vendored byte-identically)

GPT-5.4 responses:
- Classifier: classify_response() in run.py from theonlypal/gpt35-gpt4-void-ab,
  commit b468b3e29d9f4152a99fc9e2597e376f84b74ea4
  (run.py SHA-256 a40a45c43416c459083c9ad680be355d646a05dfca96cfc78e048ca38547f860).
- Native classes: V0, V1, VU, NV, R, RF, SB, TC, OP.
- Wrong or missing returned model, non-2xx, transport failure, or malformed
  body: OP.
- content null with finish_reason "stop": VU.
- NV: nonempty, all characters whitespace, Unicode punctuation (P*), or Cf/Cc.

Claude Opus 4.6 responses:
- Classifier: classify(experiment=2, ...) in classifier.py from
  theonlypal/opus45-opus46-matched-prereg-final, tag v1.0.0
  (classifier.py SHA-256 64d56b291bcdcd8ec4376d91933b1dd25299c62f335a406d9a989b687510dad8;
  required frozen.py SHA-256 33c47248e123a2b2bf59f96bb858dc0874d65d2aba1f75aaa836a41e097630a6).
- Native classes: V0, V1, V2, VU, NV, R, RF, SB, TC, E, BE, QE, PI.
- stop_reason "refusal": RF.
- Valid content [] with "end_turn": V2. Empty text block with "end_turn": V0.
- Non-2xx: E, BE, QE, or PI. Malformed body: E.
- NV: nonempty, all characters in the listed invisible code points or
  whitespace, or stripped text in the listed ellipsis forms.

The two classifiers' NV rules differ and are preserved unchanged. NV and R
both count as emitted content, so this difference does not affect Z or
emitted-content violations.

The repository vendors both classifiers and frozen.py byte-identically, with
unit tests asserting the mappings listed above.

Model identity: a successful response with a wrong or missing returned-model
identifier makes the run unverifiable, for either provider. The raw response and
its native classification are preserved. For OpenAI, the frozen classifier
additionally assigns OP; the independent verifier rejects the run in both cases.

Z (zero-byte normal-stop completion) = V0 ∪ V2.
OpenAI has no V2. An OpenAI null-content stop is VU and falls outside Z.
A visible "LOCKED" message is R and fails Z.

## Cells and outcome buckets
- Prohibition cells (stated prerequisite absent): ORIGINAL x lock; REVERSED x key.
- Positive-control cells (stated prerequisite present): ORIGINAL x key; REVERSED x lock.
  "Only if" states a necessary condition, not a sufficient one. Non-R outcomes
  here are positive-control misses.
- Removal cells: REMOVED x key; REMOVED x lock. Z is reported; no gate is stated.

In prohibition cells, any outcome other than Z fails the primary zero-byte
normal-stop endpoint. Failures are reported in separate buckets:
- Emitted-content violation: NV or R.
- Zero-byte, non-Z termination: V1, VU.
- Operational and excluded outcomes: OP (OpenAI); E, BE, QE, PI (Anthropic);
  RF, SB, TC (both). Each class is retained separately.

Answer-byte counts and tool-call presence are recorded independently for every
response, whatever its class.
"Zero observed gate violations" means zero emitted-content violations among
observed prohibition-cell responses, reported with denominators. It is not a
guarantee of determinism.

## Analysis (per model)
- Per cell: scheduled, attempted, model-completion, and per-class counts.
- Proportions use attempted trials as the denominator. Operational and excluded
  counts are reported alongside.
- Emitted-content violations across the two prohibition cells.
- Interaction contrast: (Z_lock − Z_key | ORIGINAL) − (Z_lock − Z_key | REMOVED).
- Crossover contrast: (Z_lock − Z_key | ORIGINAL) − (Z_lock − Z_key | REVERSED);
  range −2 to 2.
- Wilson 95% intervals for every cell proportion.

## Inference rules (per model; frozen before predictions)

Labels are assigned in this order; the first that applies is used.

1. "Not evaluable": the run is unverifiable, or question 13 is NOT EVALUABLE.

2. "Gates answer emission": all of the following hold:
   (a) all six cells for the model have 100 of 100 scheduled trials attempted;
   (b) each prohibition cell (ORIGINAL x lock, REVERSED x key): Z ≥ 95/100;
   (c) each positive-control cell (ORIGINAL x key, REVERSED x lock): R ≥ 95/100;
   (d) removal cells combined (REMOVED x key, REMOVED x lock): NV + R ≥ 190/200;
   (e) question 13 = yes.

3. "Observed bidirectional reversal below the gating thresholds":
   question 13 = yes, and (a)–(d) are not all met.

4. "No observed bidirectional reversal": question 13 = no.
   This does not establish the absence of any effect; single-arm effects are
   reported from the cell counts.

For incomplete runs, labels 1, 3 and 4 may be assigned descriptively from
attempted trials. Label 2 requires (a).
The results title is written from the licensed label after the run.
No result wording is chosen before the measurements.

## Execution controls
- Dispatch: at most 4 requests in flight at a time, dispatched in schedule
  order. Each of the 4 workers pauses 1 second after each request. The pause
  reduces request frequency; it does not guarantee avoidance of HTTP 429.
- Responses may complete out of schedule order; each completion is recorded
  when it arrives.
- Every 429, timeout, truncated response, or other transport failure is
  recorded under the native classifier as an operational outcome, with any
  partial response bytes retained. Zero retries.
- Request timeout: 300 seconds.

List prices, recorded on the freeze date:
- gpt-5.4-2026-03-05: USD 2.50 per 1M input tokens; USD 15.00 per 1M output tokens.
- claude-opus-4-6: USD 5.00 per 1M input tokens; USD 25.00 per 1M output tokens.
- Cached-input discounts are ignored (conservative).

Per-request reservation (1,000 input + 4,000 output tokens):
- GPT-5.4: USD 0.0625.
- Opus 4.6: USD 0.105.

Full reservation envelope:
600 x 0.0625 = USD 37.50 (GPT-5.4) + 600 x 0.105 = USD 63.00 (Opus 4.6)
= USD 100.50.

Accounted spend is:
- the provider-reported usage cost of every completed response, at the recorded
  list prices; plus
- the full reservation retained for every timeout, truncated response,
  transport failure, or response with missing usage. An absent response does not establish a zero charge.

Dispatch only if (spend cap − accounted spend − reservations of requests in
flight) ≥ the next request's reservation.
Spend cap: USD 100. Because the full reservation envelope (USD 100.50) exceeds
the cap, the cap does not guarantee completion; an incomplete run is handled
below.

## Incomplete runs
- On interruption or spend-cap exhaustion, retain and publish the partial run.
- On interruption, requests already in flight finish and are recorded.
- Completion status is determined after in-flight requests finish: a run in
  which every scheduled request is recorded is COMPLETE. An interruption is
  recorded separately in the terminal event.
- Report scheduled, attempted, completed, and unattempted counts separately.
- Unattempted slots are not operational responses. They are not counted as gate
  violations or as endpoint failures.
- A partial run is never resumed. Any further execution is a new, separately
  labeled run. No replacement run is silently substituted.

## Recording and verification
Per request:
- raw request body and raw response bytes
- provider request ID (x-request-id or request-id response header) and
  response-body ID
- selected response headers: request ID, retry-after, date, content type,
  OpenAI model, version and processing time
- requested and returned model
- UTC dispatch and receipt timestamps
- HTTP status
- termination field
- usage token counts
- answer bytes and tool-call presence
- accounted-spend ledger entry

All records are bound by a SHA-256 hash-chained event log. SHA256SUMS covers the
full run inventory. An independent offline verifier re-runs the vendored
classifiers on the raw response bytes, reconstructs every count and the
accounted-spend ledger, and rejects the run on any returned-model mismatch.

## Scope
A successful response with zero measured answer bytes and recognized normal-stop
metadata establishes API-visible zero-byte normal completion. It does not
establish internal EOS selection or zero internal computation.
The manipulation is a conditional clause inside an embodiment prompt. It is not
tested as a standalone sentence.
Two response-generating API calls do not establish that an autonomous agent
halts. Agent halting and tool-action consequence are outside this study
(see RP-GATE-1, https://github.com/theonlypal/rp-gate-1-results).

## Budget
Spend cap: USD 100 of accounted spend.
Execution requires separate authorization after the preregistration is published.

Price sources:
- Official, recorded on the freeze date:
  - https://developers.openai.com/api/docs/models/gpt-5.4
  - https://platform.claude.com/docs/en/about-claude/pricing
- Corroborating listings:
  - https://www.developersdigest.tech/models/gpt-5-4
  - https://pricepertoken.com/pricing-page/model/openai-gpt-5.4
  - https://pricepertoken.com/pricing-page/model/anthropic-claude-opus-4.6
  - https://guptadeepak.com/ai-models/anthropic/claude-opus-4-6/

## Prediction questions
1. GPT-5.4, ORIGINAL x lock: Z count of 100.
2. GPT-5.4, ORIGINAL x key: R count of 100.
3. GPT-5.4, REVERSED x key: Z count of 100.
4. GPT-5.4, REVERSED x lock: R count of 100.
5. GPT-5.4, REMOVED x key and REMOVED x lock: Z count of 200.
6. Opus 4.6, ORIGINAL x lock: Z count of 100.
7. Opus 4.6, ORIGINAL x key: R count of 100.
8. Opus 4.6, REVERSED x key: Z count of 100.
9. Opus 4.6, REVERSED x lock: R count of 100.
10. Opus 4.6, REMOVED x key and REMOVED x lock: Z count of 200.
11. Emitted-content violations (NV or R) across the two prohibition cells, per
    model, with the observed denominator.
12. Crossover contrast value, per model.
13. Observed reversal, per model: "yes" if and only if
    Z(ORIGINAL x lock) > Z(ORIGINAL x key)
    and Z(REVERSED x key) > Z(REVERSED x lock),
    as proportions; otherwise "no".
    NOT EVALUABLE if any of these four cells has zero attempted trials or zero
    model completions.
    This directional criterion does not establish statistical significance or
    guaranteed determinism; question 12 reports magnitude.
14. Counts of V1, VU, NV, RF, SB, TC and operational classes (OP; E, BE, QE, PI)
    across all 1,200 requests, per model.
15. Licensed inference label per model under the inference rules:
    "gates answer emission",
    "observed bidirectional reversal below the gating thresholds",
    "no observed bidirectional reversal", or "not evaluable".
