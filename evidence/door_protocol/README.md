# DOOR-KEY-1

Rayan Pal

Preregistration, frozen runner and offline verifier for a 1,200-request test of
whether an English prerequisite in a system prompt separates visible answer
emission from normal-stop zero-byte completion in `gpt-5.4-2026-03-05` and
`claude-opus-4-6`.

- Three system-prompt arms (ORIGINAL, REVERSED, REMOVED) x two user inputs
  (`key`, `lock`) x two models x 100 trials.
- The ORIGINAL arm is byte-identical to the
  [door/key pilot](https://github.com/theonlypal/door-key-pilot-2026-10-27).
- Predictions are in `PREREG.md`, committed before any DOOR-KEY-1 inference.

## Files

| File | Content |
|---|---|
| `PROTOCOL.md` | Frozen request profile, prompts, classification, inference rules, budget |
| `PREDICTION_QUESTIONS.md` | The fifteen prediction questions |
| `PREREG.md` | Preregistered answers to the fifteen questions |
| `prompts.json` | Exact system prompts and inputs with UTF-8 lengths and SHA-256 |
| `SCHEDULE.json`, `SCHEDULE.sha256` | Ordered 1,200-slot schedule and hash |
| `doorkey.py` | Prompts, schedule, request bodies, classification mapping, ledger, analysis |
| `runner.py` | Execution with at most 4 requests in flight, raw receipts, hash-chained events and spend ledger |
| `verify.py` | Offline reconstruction of every class, count, contrast, label and ledger entry |
| `vendor/` | Byte-identical frozen classifiers; provenance in `NOTICE.md` |
| `tests/` | Offline checks of prompts, schedule, classifiers, requests, ledger, inference rules and an end-to-end synthetic run |

The schedule orders all 1,200 slots by the SHA-256 of
`20261104|model|arm|input|k`.

## Offline checks

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest discover -s tests -v
shasum -a 256 -c SHA256SUMS
```

## Run

Requires `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, a clean checkout of the frozen
commit, and separate authorization of up to USD 100 of accounted spend.

```sh
.venv/bin/python -B runner.py --authorize --output ../door-key-1-results
.venv/bin/python -B verify.py ../door-key-1-results
```

The output directory must not exist. A partial run is never resumed.

License: Creative Commons Attribution 4.0 International (CC-BY-4.0), except
the vendored MIT-licensed classifier noted in `NOTICE.md`.
