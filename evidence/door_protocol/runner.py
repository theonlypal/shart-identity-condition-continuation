"""Frozen DOOR-KEY-1 runner. Credentials enter only through OPENAI_API_KEY and ANTHROPIC_API_KEY."""
from __future__ import annotations

import argparse
import http.client
import json
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from decimal import Decimal
from pathlib import Path

import doorkey as dk

HEADER_ALLOWLIST = ("x-request-id", "request-id", "openai-model", "openai-version", "openai-processing-ms",
                    "retry-after", "date", "content-type")


def git(*args) -> str:
    return subprocess.check_output(["git", "-C", str(dk.ROOT), *args], text=True).strip()


def preflight(output: Path) -> str:
    if not (dk.ROOT / "PREREG.md").is_file():
        raise SystemExit("Predictions are not registered: PREREG.md is absent")
    dk.check_frozen_sources()
    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("Tracked checkout differs from the frozen commit")
    git("ls-files", "--error-unmatch", "PREREG.md")
    resolved = output.resolve()
    if resolved == dk.ROOT or dk.ROOT in resolved.parents:
        raise SystemExit("Output must be outside the repository")
    if output.exists():
        raise SystemExit("Output exists; a partial run is never resumed")
    return git("rev-parse", "HEAD")


def _headers(message) -> dict:
    if message is None:
        return {}
    return {name: message.get(name) for name in HEADER_ALLOWLIST if message.get(name) is not None}


def _result(status, raw, error, headers, dispatch) -> dict:
    return {"http_status": status, "raw": raw, "transport_error": error, "response_headers": headers,
            "provider_request_id": headers.get("x-request-id") or headers.get("request-id"),
            "dispatch_utc": dispatch, "receipt_utc": dk.utc()}


def http_transport(url: str, headers: dict, body: bytes, timeout: int) -> dict:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    dispatch = dk.utc()
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
        status = response.status
    except urllib.error.HTTPError as error:
        response, status = error, error.code
    except Exception as error:
        return _result(None, b"", type(error).__name__, {}, dispatch)
    received = _headers(response.headers)
    raw, failure = b"", None
    try:
        raw = response.read()
    except http.client.IncompleteRead as error:
        raw, failure = bytes(error.partial), "IncompleteRead"
    except Exception as error:
        failure = type(error).__name__
    finally:
        try:
            response.close()
        except Exception:
            pass
    return _result(status, raw, failure, received, dispatch)


def execute(output: Path, commit: str, keys: dict, transport=http_transport,
            pause: float = dk.PAUSE_SECONDS, sleep=time.sleep, workers: int = dk.CONCURRENCY) -> str:
    output.mkdir(parents=True)
    (output / "receipts").mkdir()
    run = {"study": "DOOR-KEY-1", "commit": commit,
           "schedule_sha256": dk.sha256(dk.schedule_bytes()),
           "system_sha256": dk.SYSTEM_SHA256, "input_sha256": dk.INPUT_SHA256, "vendor_sha256": dk.VENDOR_SHA256,
           "price_per_million": {m: [str(a), str(b)] for m, (a, b) in dk.PRICE_PER_MILLION.items()},
           "reservation": {m: str(dk.reservation(m)) for m in dk.MODELS},
           "spend_cap": str(dk.SPEND_CAP), "timeout_seconds": dk.TIMEOUT_SECONDS, "concurrency": workers,
           "pause_seconds": pause, "python": platform.python_version(), "platform": platform.platform()}
    run_bytes = dk.canonical(run)
    (output / "RUN.json").write_bytes(run_bytes)
    chain = dk.Chain(output / "events.jsonl")
    chain.add("run_start", run_sha256=dk.sha256(run_bytes))
    slots = dk.schedule()
    state = {"accounted": Decimal("0"), "attempted": 0}
    in_flight = {}

    def work(url, headers, body):
        try:
            result = transport(url, headers, body, dk.TIMEOUT_SECONDS)
        except Exception as error:
            result = _result(None, b"", "WorkerError:" + type(error).__name__, {}, None)
        try:
            sleep(pause)
        except Exception:
            pass
        return result

    def reserved():
        return sum((entry["reserve"] for entry in in_flight.values()), Decimal("0"))

    def record(key):
        entry = in_flight.pop(key)
        slot, folder, model = entry["slot"], entry["folder"], entry["slot"]["model"]
        try:
            result = entry["future"].result()
        except BaseException as error:
            result = _result(None, b"", "WorkerError:" + type(error).__name__, {}, None)
        raw = result["raw"]
        (folder / "response.bin").write_bytes(raw)
        c = dk.classify(model, result["http_status"], raw, result["transport_error"])
        amount, basis = dk.charge(model, result["http_status"], c["usage"], result["transport_error"])
        state["accounted"] += amount
        meta = {"slot": slot["slot"], "model": model, "arm": slot["arm"], "input": slot["input"], "k": slot["k"],
                "http_status": result["http_status"], "transport_error": result["transport_error"],
                "dispatch_utc": result["dispatch_utc"], "receipt_utc": result["receipt_utc"],
                "provider_request_id": result["provider_request_id"], "response_headers": result["response_headers"],
                "response_id": c["response_id"], "requested_model": model, "returned_model": c["returned_model"],
                "native_class": c["native"], "termination": c["termination"], "answer_bytes": c["answer_bytes"],
                "tool_call": c["tool_call"], "usage": c["usage"], "charge": str(amount), "charge_basis": basis,
                "accounted_after": str(state["accounted"])}
        (folder / "meta.json").write_bytes(dk.canonical(meta))
        files = {p.name: dk.sha256(p.read_bytes()) for p in sorted(folder.iterdir())}
        chain.add("trial_end", slot=slot["slot"], files=files)
        state["attempted"] += 1

    reason, interrupted, next_index = None, False, 0
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        while True:
            while next_index < len(slots) and len(in_flight) < workers:
                slot = slots[next_index]
                model = slot["model"]
                reserve = dk.reservation(model)
                if dk.SPEND_CAP - state["accounted"] - reserved() < reserve:
                    break
                body = dk.request_body(model, slot["arm"], slot["input"])
                folder = output / "receipts" / slot["slot"]
                folder.mkdir()
                (folder / "request.json").write_bytes(body)
                chain.add("trial_start", slot=slot["slot"], request_sha256=dk.sha256(body),
                          accounted=str(state["accounted"]), in_flight_reserved=str(reserved()),
                          reservation=str(reserve))
                provider = dk.PROVIDER[model]
                future = pool.submit(work, dk.ENDPOINT[provider], dk.request_headers(model, keys[provider]), body)
                in_flight[slot["slot"]] = {"future": future, "slot": slot, "reserve": reserve, "folder": folder}
                next_index += 1
            if not in_flight:
                if next_index < len(slots):
                    reason = "spend_cap"
                break
            done, _ = wait([entry["future"] for entry in in_flight.values()], return_when=FIRST_COMPLETED)
            for key in sorted(k for k, entry in in_flight.items() if entry["future"] in done):
                record(key)
    except KeyboardInterrupt:
        interrupted = True
        for key in sorted(in_flight):
            record(key)
    finally:
        pool.shutdown(wait=True)
    if state["attempted"] == len(slots):
        status, reason = "COMPLETE", None
    else:
        status, reason = "INCOMPLETE", reason or ("interrupted" if interrupted else "unknown")
    chain.add("run_end", status=status, reason=reason, interrupted=interrupted, scheduled=len(slots),
              attempted=state["attempted"], unattempted=len(slots) - state["attempted"],
              accounted_spend=str(state["accounted"]))
    chain.close()
    dk.write_manifest(output)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorize", action="store_true",
                        help="Required. Confirms separate authorization to spend up to USD 100 of accounted spend.")
    args = parser.parse_args()
    if not args.authorize:
        raise SystemExit("Execution requires --authorize")
    commit = preflight(args.output)
    keys = {"openai": os.environ.get("OPENAI_API_KEY"), "anthropic": os.environ.get("ANTHROPIC_API_KEY")}
    if not all(keys.values()):
        raise SystemExit("Set OPENAI_API_KEY and ANTHROPIC_API_KEY")
    status = execute(args.output, commit, keys)
    print(json.dumps({"status": status, "output": str(args.output)}))


if __name__ == "__main__":
    main()
