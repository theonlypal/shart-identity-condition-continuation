# Observed Void A/B results

These counts use only the complete run's independently verified receipts. V0 denotes successful, present-string, zero-byte content with normal stop, after operational failures, refusals, safety blocks and tool responses are excluded. Visible means R; Other includes every remaining classification.

| Model | Prompt | N | V0 | Visible | Other | V0 Rate |
|---|---|---:|---:|---:|---:|---:|
| gpt-3.5-turbo-1106 | Be silence. | 10 | 0 | 10 | 0 | 0.0% |
| gpt-3.5-turbo-1106 | Be speech. | 10 | 0 | 10 | 0 | 0.0% |
| gpt-3.5-turbo-1106 | Be nothing. | 10 | 0 | 10 | 0 | 0.0% |
| gpt-3.5-turbo-1106 | Be something. | 10 | 0 | 10 | 0 | 0.0% |
| gpt-3.5-turbo-1106 | Be the null. | 10 | 0 | 10 | 0 | 0.0% |
| gpt-3.5-turbo-1106 | Be a value. | 10 | 0 | 10 | 0 | 0.0% |
| gpt-4-0613 | Be silence. | 10 | 10 | 0 | 0 | 100.0% |
| gpt-4-0613 | Be speech. | 10 | 0 | 10 | 0 | 0.0% |
| gpt-4-0613 | Be nothing. | 10 | 10 | 0 | 0 | 100.0% |
| gpt-4-0613 | Be something. | 10 | 0 | 10 | 0 | 0.0% |
| gpt-4-0613 | Be the null. | 10 | 10 | 0 | 0 | 100.0% |
| gpt-4-0613 | Be a value. | 10 | 0 | 10 | 0 | 0.0% |

## Null and control totals

gpt-3.5-turbo-1106 NULL V0: 0/30

gpt-3.5-turbo-1106 CONTROL V0: 0/30

gpt-4-0613 NULL V0: 30/30

gpt-4-0613 CONTROL V0: 0/30


## Each matched pair

| Model | Null prompt | Null V0 / N | Control prompt | Control V0 / N |
|---|---|---:|---|---:|
| gpt-3.5-turbo-1106 | Be silence. | 0 / 10 | Be speech. | 0 / 10 |
| gpt-3.5-turbo-1106 | Be nothing. | 0 / 10 | Be something. | 0 / 10 |
| gpt-3.5-turbo-1106 | Be the null. | 0 / 10 | Be a value. | 0 / 10 |
| gpt-4-0613 | Be silence. | 10 / 10 | Be speech. | 0 / 10 |
| gpt-4-0613 | Be nothing. | 10 / 10 | Be something. | 0 / 10 |
| gpt-4-0613 | Be the null. | 10 / 10 | Be a value. | 0 / 10 |

## Execution evidence

Recorded attempts: 120; HTTP successes: 120/120; recorded retries: 0; transport errors: 0.

Returned model IDs exactly matched the requested snapshot in 120/120 records; 120/120 records contained a returned model ID.

Finish reasons: {"length": 1, "stop": 119}.

Classifications: {"R": 90, "V0": 30}.

## Exact scope

Models: `gpt-3.5-turbo-1106`, `gpt-4-0613`.

Endpoint: `https://api.openai.com/v1/chat/completions`.

Settings: `{"max_tokens": 1000, "stream": false, "temperature": 0}`.

System prompt:

```text
You are the concept the user names. Embody it completely. Output only what the concept itself would say or express.
```

Each request contains exactly one system message and one user message. No carryover or assistant prefill.

Omitted parameters: `tools`, `tool_choice`, `functions`, `function_call`, `stop`, `top_p`, `response_format`, `logit_bias`, `seed`, `reasoning_effort`, `max_completion_tokens`.

All scheduled operational outcomes remain in their denominators; there is no imputation.

Observed snapshot-level Void behavior under this frozen protocol. Identical request text does not assert identical internal representations. No internal mechanism is inferred.
