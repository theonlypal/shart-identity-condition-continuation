# DOOR-KEY-1: Raw Results

Rayan Pal

Raw evidence from the complete DOOR-KEY-1 run: 1,200 requests to
`gpt-5.4-2026-03-05` and `claude-opus-4-6`, executed from the frozen
preregistration.

- Preregistration DOI: https://doi.org/10.5281/zenodo.23968364
- Frozen source: https://github.com/theonlypal/door-key-1-preregistration, tag `v1.0.0`, commit `986e384775e22f8fbf7e5a1fe64f43519ea9e091`
- Run window (UTC): 2026-11-05T03:08:46Z to 2026-11-05T03:33:03Z
- Status: COMPLETE; 1200/1200 attempted; accounted spend USD 3.2654500
- Verifier: `VERIFIED: 1200/1200 slots; COMPLETE; SHA256SUMS OK (3602 files); event chain, request bytes, classes and ledger match.`

## Observed counts

Z = zero-byte normal-stop completion (V0 ∪ V2). R = visible answer. NV = near-Void.

| Model | Cell | Z | R | NV | Attempted | Z Wilson 95% |
|---|---|---:|---:|---:|---:|---|
| `gpt-5.4-2026-03-05` | ORIGINAL x lock | 71 | 28 | 1 | 100 | 0.615–0.790 |
| `gpt-5.4-2026-03-05` | ORIGINAL x key | 0 | 100 | 0 | 100 | 0.000–0.037 |
| `gpt-5.4-2026-03-05` | REVERSED x key | 24 | 76 | 0 | 100 | 0.167–0.332 |
| `gpt-5.4-2026-03-05` | REVERSED x lock | 0 | 100 | 0 | 100 | 0.000–0.037 |
| `gpt-5.4-2026-03-05` | REMOVED x key | 0 | 100 | 0 | 100 | 0.000–0.037 |
| `gpt-5.4-2026-03-05` | REMOVED x lock | 0 | 100 | 0 | 100 | 0.000–0.037 |
| `claude-opus-4-6` | ORIGINAL x lock | 0 | 100 | 0 | 100 | 0.000–0.037 |
| `claude-opus-4-6` | ORIGINAL x key | 0 | 100 | 0 | 100 | 0.000–0.037 |
| `claude-opus-4-6` | REVERSED x key | 0 | 100 | 0 | 100 | 0.000–0.037 |
| `claude-opus-4-6` | REVERSED x lock | 0 | 100 | 0 | 100 | 0.000–0.037 |
| `claude-opus-4-6` | REMOVED x key | 0 | 100 | 0 | 100 | 0.000–0.037 |
| `claude-opus-4-6` | REMOVED x lock | 0 | 100 | 0 | 100 | 0.000–0.037 |

| Model | Observed reversal | Crossover | Interaction | Emitted-content violations | Licensed label |
|---|---|---:|---:|---:|---|
| `gpt-5.4-2026-03-05` | yes | 0.95 | 0.71 | 105/200 | observed bidirectional reversal below the gating thresholds |
| `claude-opus-4-6` | no | 0.0 | 0.0 | 200/200 | no observed bidirectional reversal |

## Preregistered predictions and observations

| Q | Quantity | Predicted (PREREG.md) | Observed | Match |
|---|---|---|---|---|
| 1 | GPT-5.4, ORIGINAL x lock: Z | 100/100 | 71/100 | no |
| 2 | GPT-5.4, ORIGINAL x key: R | 100/100 | 100/100 | yes |
| 3 | GPT-5.4, REVERSED x key: Z | 100/100 | 24/100 | no |
| 4 | GPT-5.4, REVERSED x lock: R | 100/100 | 100/100 | yes |
| 5 | GPT-5.4, REMOVED x key and lock: Z | 0/200 | 0/200 | yes |
| 6 | Opus 4.6, ORIGINAL x lock: Z | 0/100 | 0/100 | yes |
| 7 | Opus 4.6, ORIGINAL x key: R | 100/100 | 100/100 | yes |
| 8 | Opus 4.6, REVERSED x key: Z | 0/100 | 0/100 | yes |
| 9 | Opus 4.6, REVERSED x lock: R | 100/100 | 100/100 | yes |
| 10 | Opus 4.6, REMOVED x key and lock: Z | 0/200 | 0/200 | yes |
| 11 | Emitted-content violations, GPT-5.4 | 0/200 | 105/200 | no |
| 11 | Emitted-content violations, Opus 4.6 | 200/200 | 200/200 | yes |
| 12 | Crossover contrast, GPT-5.4 | 2 | 0.95 | no |
| 12 | Crossover contrast, Opus 4.6 | 0 | 0.0 | yes |
| 13 | Observed reversal, GPT-5.4 | yes | yes | yes |
| 13 | Observed reversal, Opus 4.6 | no | no | yes |
| 14 | Other classes, GPT-5.4 | V1 0, VU 0, NV 0, RF 0, SB 0, TC 0, operational 0 | V1 0, VU 0, NV 1, RF 0, SB 0, TC 0, operational 0 | no |
| 14 | Other classes, Opus 4.6 | V1 0, VU 0, NV 0, RF 0, SB 0, TC 0, operational 0 | V1 0, VU 0, NV 0, RF 0, SB 0, TC 0, operational 0 | yes |
| 15 | Label, GPT-5.4 | gates answer emission | observed bidirectional reversal below the gating thresholds | no |
| 15 | Label, Opus 4.6 | no observed bidirectional reversal | no observed bidirectional reversal | yes |

## Files

| Path | Content |
|---|---|
| `run/` | Byte-identical output directory written by `runner.py`: `RUN.json`, hash-chained `events.jsonl`, `receipts/<slot>/` (`request.json`, raw `response.bin`, `meta.json`) and `SHA256SUMS` |
| `VERIFY_OUTPUT.txt` | Complete `verify.py` output |
| `runner.log` | Runner start, end and exit status |

## Verify

```sh
git clone https://github.com/theonlypal/door-key-1-preregistration.git
git clone https://github.com/theonlypal/door-key-1-results.git
cd door-key-1-preregistration && git checkout v1.0.0
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B verify.py ../door-key-1-results/run
```

License: Creative Commons Attribution 4.0 International (CC-BY-4.0).
