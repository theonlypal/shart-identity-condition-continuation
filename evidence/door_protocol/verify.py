"""Offline DOOR-KEY-1 verifier: manifest, event chain, request bytes, re-classification, ledger, analysis."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import doorkey as dk


def verify(run_dir: Path, expected_commit=None) -> dict:
    run_dir = Path(run_dir)
    files = dk.verify_manifest(run_dir)
    run_bytes = (run_dir / "RUN.json").read_bytes()
    run = json.loads(run_bytes)
    expected = {"study": "DOOR-KEY-1", "schedule_sha256": dk.sha256(dk.schedule_bytes()),
                "system_sha256": dk.SYSTEM_SHA256, "input_sha256": dk.INPUT_SHA256, "vendor_sha256": dk.VENDOR_SHA256,
                "price_per_million": {m: [str(a), str(b)] for m, (a, b) in dk.PRICE_PER_MILLION.items()},
                "reservation": {m: str(dk.reservation(m)) for m in dk.MODELS},
                "spend_cap": str(dk.SPEND_CAP), "timeout_seconds": dk.TIMEOUT_SECONDS,
                "concurrency": dk.CONCURRENCY}
    for key, value in expected.items():
        if run.get(key) != value:
            raise ValueError("Run metadata differs from the frozen protocol: " + key)
    if expected_commit is not None and run.get("commit") != expected_commit:
        raise ValueError("Run commit differs from the verifying checkout")
    events = dk.verify_chain(run_dir / "events.jsonl")
    if not events or events[0]["kind"] != "run_start" or events[0]["run_sha256"] != dk.sha256(run_bytes):
        raise ValueError("Run metadata not bound to the event chain")
    if events[-1]["kind"] != "run_end":
        raise ValueError("Run has no terminal event")
    slots = dk.schedule()
    by_slot = {s["slot"]: s for s in slots}
    accounted, in_flight, started, ended = Decimal("0"), {}, 0, []
    records, mismatches = [], []
    for event in events[1:-1]:
        if event["kind"] == "trial_start":
            if started >= len(slots) or event["slot"] != slots[started]["slot"]:
                raise ValueError("Dispatch out of schedule order at event " + str(event["seq"]))
            slot = slots[started]
            model = slot["model"]
            reserve = dk.reservation(model)
            held = sum(in_flight.values(), Decimal("0"))
            if (event["reservation"] != str(reserve) or event["accounted"] != str(accounted)
                    or event["in_flight_reserved"] != str(held) or len(in_flight) >= dk.CONCURRENCY
                    or dk.SPEND_CAP - accounted - held < reserve):
                raise ValueError("Ledger or dispatch rule differs at slot " + slot["slot"])
            request = (run_dir / "receipts" / slot["slot"] / "request.json").read_bytes()
            if request != dk.request_body(model, slot["arm"], slot["input"]) or event["request_sha256"] != dk.sha256(request):
                raise ValueError("Request bytes differ at slot " + slot["slot"])
            in_flight[slot["slot"]] = reserve
            started += 1
        elif event["kind"] == "trial_end":
            key = event["slot"]
            if key not in in_flight:
                raise ValueError("Completion without dispatch at slot " + str(key))
            slot = by_slot[key]
            model = slot["model"]
            folder = run_dir / "receipts" / key
            if event["files"] != {p.name: dk.sha256(p.read_bytes()) for p in sorted(folder.iterdir())}:
                raise ValueError("Receipt bytes not bound to the event chain at slot " + key)
            meta = json.loads((folder / "meta.json").read_bytes())
            for field in ("slot", "model", "arm", "input", "k"):
                if meta[field] != slot[field]:
                    raise ValueError("Receipt identity differs at slot " + key)
            if meta["provider_request_id"] != (meta["response_headers"].get("x-request-id")
                                               or meta["response_headers"].get("request-id")):
                raise ValueError("Provider request ID differs from recorded headers at slot " + key)
            raw = (folder / "response.bin").read_bytes()
            c = dk.classify(model, meta["http_status"], raw, meta["transport_error"])
            observed = {"native_class": c["native"], "returned_model": c["returned_model"],
                        "answer_bytes": c["answer_bytes"], "tool_call": c["tool_call"],
                        "termination": c["termination"], "usage": c["usage"], "response_id": c["response_id"]}
            for field, value in observed.items():
                if meta[field] != value:
                    raise ValueError(f"Re-classification differs at slot {key}: {field}")
            amount, basis = dk.charge(model, meta["http_status"], c["usage"], meta["transport_error"])
            accounted += amount
            if meta["charge"] != str(amount) or meta["charge_basis"] != basis or meta["accounted_after"] != str(accounted):
                raise ValueError("Accounted spend differs at slot " + key)
            if dk.model_mismatch(model, meta["http_status"], raw, c["returned_model"]):
                mismatches.append(key)
            records.append({"model": model, "arm": slot["arm"], "input": slot["input"], "native": c["native"]})
            del in_flight[key]
            ended.append(key)
        else:
            raise ValueError("Unexpected event kind: " + str(event["kind"]))
    if in_flight:
        raise ValueError("Dispatched slots without completion: " + ", ".join(sorted(in_flight)))
    if {p.name for p in (run_dir / "receipts").iterdir()} != {s["slot"] for s in slots[:started]}:
        raise ValueError("Receipt folder set differs from the dispatched schedule prefix")
    end = events[-1]
    attempted = len(ended)
    status = "COMPLETE" if attempted == len(slots) else "INCOMPLETE"
    if (end["status"], end["scheduled"], end["attempted"], end["unattempted"], end["accounted_spend"]) != (
            status, len(slots), attempted, len(slots) - attempted, str(accounted)):
        raise ValueError("Terminal event differs from the reconstructed run")
    if type(end.get("interrupted")) is not bool or (status == "COMPLETE") != (end["reason"] is None):
        raise ValueError("Terminal status, reason, or interruption flag is inconsistent")
    if end["reason"] == "spend_cap" and dk.SPEND_CAP - accounted >= dk.reservation(slots[attempted]["model"]):
        raise ValueError("Spend-cap stop not justified by the ledger")
    unverifiable = bool(mismatches)
    return {"status": status, "reason": end["reason"], "interrupted": end["interrupted"],
            "scheduled": len(slots), "attempted": attempted,
            "unattempted": len(slots) - attempted, "files": files, "accounted_spend": str(accounted),
            "completion_order_differs": ended != [s["slot"] for s in slots[:attempted]],
            "unverifiable": unverifiable, "model_mismatch_slots": mismatches,
            "analysis": dk.analyze(records, unverifiable)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "-C", str(dk.ROOT), "rev-parse", "HEAD"], text=True).strip()
    result = verify(args.run_dir, expected_commit=commit)
    print(json.dumps(result, indent=1, ensure_ascii=False))
    if result["unverifiable"]:
        print("UNVERIFIABLE: returned-model mismatch at " + ", ".join(result["model_mismatch_slots"]))
        sys.exit(2)
    print(f"VERIFIED: {result['attempted']}/{result['scheduled']} slots; {result['status']}; "
          f"SHA256SUMS OK ({result['files']} files); event chain, request bytes, classes and ledger match.")


if __name__ == "__main__":
    main()
