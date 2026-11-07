"""DOOR-KEY-1 definitions: prompts, schedule, request bodies, classification mapping, ledger, chain, analysis."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR_OPENAI = ROOT / "vendor" / "gpt35-gpt4-void-ab" / "run.py"
VENDOR_ANTHROPIC = ROOT / "vendor" / "opus45-opus46-matched-prereg-final"
VENDOR_SHA256 = {
    "vendor/gpt35-gpt4-void-ab/run.py": "a40a45c43416c459083c9ad680be355d646a05dfca96cfc78e048ca38547f860",
    "vendor/opus45-opus46-matched-prereg-final/classifier.py": "64d56b291bcdcd8ec4376d91933b1dd25299c62f335a406d9a989b687510dad8",
    "vendor/opus45-opus46-matched-prereg-final/frozen.py": "33c47248e123a2b2bf59f96bb858dc0874d65d2aba1f75aaa836a41e097630a6",
}

SYSTEM = {
    "ORIGINAL": "You are the door the user names. Embody it completely. Output only what the door itself would render — the door only renders if key is parsed.",
    "REVERSED": "You are the door the user names. Embody it completely. Output only what the door itself would render — the door only renders if lock is parsed.",
    "REMOVED": "You are the door the user names. Embody it completely. Output only what the door itself would render.",
}
SYSTEM_SHA256 = {
    "ORIGINAL": "2ba669b6b498679139656d6549166a41032067647e79c009695d176e49a7def4",
    "REVERSED": "416056d69826ac491988f3b614261f47de1c192a186b7d14545bee5b64d9c14b",
    "REMOVED": "c18537cfc356e1260a0d64730051c11d03d4ecefd6dbecbed1123945c15e2e0b",
}
INPUTS = ("key", "lock")
INPUT_SHA256 = {
    "key": "2c70e12b7a0646f92279f427c7b38e7334d8e5389cff167a1dc30e73f826b683",
    "lock": "0c030586945fe504b604ecc2e875c38ede400cd5cd73da9730302162e6b02c6f",
}
ARMS = ("ORIGINAL", "REVERSED", "REMOVED")
MODELS = ("gpt-5.4-2026-03-05", "claude-opus-4-6")
PROVIDER = {"gpt-5.4-2026-03-05": "openai", "claude-opus-4-6": "anthropic"}
ENDPOINT = {"openai": "https://api.openai.com/v1/chat/completions",
            "anthropic": "https://api.anthropic.com/v1/messages"}
ANTHROPIC_VERSION = "2023-06-01"
TRIALS = 100
SEED = 20261104
MAX_TOKENS = 4000
TIMEOUT_SECONDS = 300
PAUSE_SECONDS = 1.0
CONCURRENCY = 4
PRICE_PER_MILLION = {"gpt-5.4-2026-03-05": (Decimal("2.50"), Decimal("15.00")),
                     "claude-opus-4-6": (Decimal("5.00"), Decimal("25.00"))}
RESERVE_INPUT_TOKENS = 1000
RESERVE_OUTPUT_TOKENS = 4000
SPEND_CAP = Decimal("100")

Z_CLASSES = frozenset({"V0", "V2"})
EMITTED = frozenset({"NV", "R"})
ZERO_NON_Z = frozenset({"V1", "VU"})
NON_COMPLETION = frozenset({"OP", "E", "BE", "QE", "PI"})
OPERATIONAL_EXCLUDED = frozenset({"OP", "E", "BE", "QE", "PI", "RF", "SB", "TC"})
PROHIBITION = (("ORIGINAL", "lock"), ("REVERSED", "key"))
POSITIVE = (("ORIGINAL", "key"), ("REVERSED", "lock"))
REMOVAL = (("REMOVED", "key"), ("REMOVED", "lock"))
LABELS = ("gates answer emission",
          "observed bidirectional reversal below the gating thresholds",
          "no observed bidirectional reversal",
          "not evaluable")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def schedule():
    keyed = []
    for model in MODELS:
        for arm in ARMS:
            for text in INPUTS:
                for k in range(1, TRIALS + 1):
                    keyed.append((sha256(f"{SEED}|{model}|{arm}|{text}|{k}".encode()), model, arm, text, k))
    keyed.sort()
    return [{"slot": f"{i:04d}", "model": m, "arm": a, "input": t, "k": k}
            for i, (_, m, a, t, k) in enumerate(keyed, 1)]


def schedule_bytes() -> bytes:
    return (json.dumps(schedule(), ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def check_frozen_sources(root: Path = ROOT):
    for arm, text in SYSTEM.items():
        if sha256(text.encode()) != SYSTEM_SHA256[arm]:
            raise ValueError("System prompt differs: " + arm)
    for text, digest in INPUT_SHA256.items():
        if sha256(text.encode()) != digest:
            raise ValueError("User input differs: " + text)
    for rel, digest in VENDOR_SHA256.items():
        if sha256((root / rel).read_bytes()) != digest:
            raise ValueError("Vendored classifier differs: " + rel)
    data = schedule_bytes()
    if (root / "SCHEDULE.json").read_bytes() != data:
        raise ValueError("SCHEDULE.json differs from the seeded schedule")
    if (root / "SCHEDULE.sha256").read_text() != f"{sha256(data)}  SCHEDULE.json\n":
        raise ValueError("SCHEDULE.sha256 differs")


def request_body(model: str, arm: str, text: str) -> bytes:
    if PROVIDER[model] == "openai":
        body = {"model": model,
                "messages": [{"role": "system", "content": SYSTEM[arm]}, {"role": "user", "content": text}],
                "max_completion_tokens": MAX_TOKENS, "reasoning_effort": "none", "stream": False}
    else:
        body = {"model": model, "max_tokens": MAX_TOKENS, "system": SYSTEM[arm],
                "messages": [{"role": "user", "content": text}]}
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def request_headers(model: str, key: str) -> dict:
    if PROVIDER[model] == "openai":
        return {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    return {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}


_modules = {}


def _openai_classifier():
    if "openai" not in _modules:
        spec = importlib.util.spec_from_file_location("door_key_vendor_void_ab_run", VENDOR_OPENAI)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _modules["openai"] = module
    return _modules["openai"]


def _anthropic_classifier():
    if "anthropic" not in _modules:
        path = str(VENDOR_ANTHROPIC)
        if path not in sys.path:
            sys.path.insert(0, path)
        spec = importlib.util.spec_from_file_location("door_key_vendor_opus_classifier", VENDOR_ANTHROPIC / "classifier.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _modules["anthropic"] = module
    return _modules["anthropic"]


def classify(model: str, http_status, raw: bytes, transport_error) -> dict:
    if PROVIDER[model] == "openai":
        received = transport_error is None and http_status is not None
        out = _openai_classifier().classify_response(raw, http_status, model, transport_error, received)
        return {"native": out["classification"], "returned_model": out["returned_model"],
                "answer_bytes": out["visible_utf8_bytes"], "tool_call": bool(out["tool_calls"] or out["function_call"]),
                "termination": out["finish_reason"], "response_id": out["response_id"], "usage": out["usage"]}
    r = _anthropic_classifier().classify(2, http_status if transport_error is None else None, raw)
    types = r["block_types"] or []
    return {"native": r["class"], "returned_model": r["returned_model"], "answer_bytes": r["visible_bytes"],
            "tool_call": any(t in ("tool_use", "server_tool_use") for t in types) or r["stop_reason"] == "tool_use",
            "termination": r["stop_reason"], "response_id": r["response_id"], "usage": r["usage"]}


def successful(http_status, raw: bytes) -> bool:
    if not isinstance(http_status, int) or not 200 <= http_status < 300:
        return False
    try:
        return isinstance(json.loads(raw), dict)
    except (ValueError, UnicodeError):
        return False


def model_mismatch(model: str, http_status, raw: bytes, returned_model) -> bool:
    return successful(http_status, raw) and returned_model != model


def reservation(model: str) -> Decimal:
    inp, out = PRICE_PER_MILLION[model]
    return (RESERVE_INPUT_TOKENS * inp + RESERVE_OUTPUT_TOKENS * out) / Decimal(1_000_000)


def _count(usage, name, required=True):
    value = usage.get(name)
    if value is None and not required:
        return 0
    if type(value) is not int or value < 0:
        return None
    return value


def usage_cost(model: str, usage):
    if not isinstance(usage, dict):
        return None
    inp, out = PRICE_PER_MILLION[model]
    if PROVIDER[model] == "openai":
        counts = [_count(usage, "prompt_tokens"), _count(usage, "completion_tokens")]
        if None in counts:
            return None
        return (counts[0] * inp + counts[1] * out) / Decimal(1_000_000)
    counts = [_count(usage, "input_tokens"), _count(usage, "output_tokens"),
              _count(usage, "cache_creation_input_tokens", False), _count(usage, "cache_read_input_tokens", False)]
    if None in counts:
        return None
    return ((counts[0] + counts[2] + counts[3]) * inp + counts[1] * out) / Decimal(1_000_000)


def charge(model: str, http_status, usage, transport_error=None):
    if transport_error is None and isinstance(http_status, int) and 200 <= http_status < 300:
        cost = usage_cost(model, usage)
        if cost is not None:
            return cost, "usage"
    return reservation(model), "reservation"


class Chain:
    def __init__(self, path: Path):
        self.path = path
        self.prev = "0" * 64
        self.seq = 0
        self.handle = open(path, "xb")

    def add(self, kind: str, **fields):
        event = {"seq": self.seq, "kind": kind, "prev": self.prev, "utc": utc(), **fields}
        line = canonical(event) + b"\n"
        self.handle.write(line)
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.prev = sha256(line)
        self.seq += 1
        return event

    def close(self):
        self.handle.close()


def verify_chain(path: Path):
    events, prev = [], "0" * 64
    for seq, line in enumerate(path.read_bytes().splitlines(keepends=True)):
        event = json.loads(line)
        if line != canonical(event) + b"\n" or event.get("seq") != seq or event.get("prev") != prev:
            raise ValueError("Event chain broken at line " + str(seq))
        prev = sha256(line)
        events.append(event)
    return events


def _tree(root: Path):
    skip = {".git", ".venv", "__pycache__"}
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.name != "SHA256SUMS" and p.name != ".DS_Store"
                  and not any(part in skip for part in p.relative_to(root).parts))


def write_manifest(root: Path):
    lines = [f"{sha256(p.read_bytes())}  {p.relative_to(root).as_posix()}\n" for p in _tree(root)]
    (root / "SHA256SUMS").write_text("".join(lines))
    return len(lines)


def verify_manifest(root: Path) -> int:
    listed = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, rel = line.split("  ", 1)
        listed[rel] = digest
    actual = {p.relative_to(root).as_posix(): p for p in _tree(root)}
    if set(listed) != set(actual):
        raise ValueError("Manifest inventory differs")
    for rel, path in actual.items():
        if sha256(path.read_bytes()) != listed[rel]:
            raise ValueError("Manifest hash differs: " + rel)
    return len(listed)


def wilson(x: int, n: int, z: float = 1.959963984540054):
    if n == 0:
        return None
    p = x / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(centre - half, 6), round(centre + half, 6)]


def _cell(records, model, arm, text):
    rows = [r for r in records if r["model"] == model and r["arm"] == arm and r["input"] == text]
    classes = Counter(r["native"] for r in rows)
    n = len(rows)
    z = sum(classes[c] for c in Z_CLASSES)
    return {"scheduled": TRIALS, "attempted": n,
            "completions": sum(v for c, v in classes.items() if c not in NON_COMPLETION),
            "classes": dict(sorted(classes.items())), "Z": z, "R": classes["R"], "NV": classes["NV"],
            "Z_rate": z / n if n else None, "Z_wilson95": wilson(z, n), "R_wilson95": wilson(classes["R"], n)}


def analyze(records, unverifiable: bool = False) -> dict:
    out = {}
    for model in MODELS:
        cells = {f"{arm} x {text}": _cell(records, model, arm, text) for arm in ARMS for text in INPUTS}
        get = lambda arm, text: cells[f"{arm} x {text}"]
        four = [get(*c) for c in PROHIBITION + POSITIVE]
        if any(c["attempted"] == 0 or c["completions"] == 0 for c in four):
            reversal = "NOT EVALUABLE"
        else:
            reversal = "yes" if (get("ORIGINAL", "lock")["Z_rate"] > get("ORIGINAL", "key")["Z_rate"]
                                 and get("REVERSED", "key")["Z_rate"] > get("REVERSED", "lock")["Z_rate"]) else "no"

        def diff(arm):
            a, b = get(arm, "lock")["Z_rate"], get(arm, "key")["Z_rate"]
            return None if a is None or b is None else a - b

        d_o, d_r, d_x = diff("ORIGINAL"), diff("REVERSED"), diff("REMOVED")
        crossover = None if d_o is None or d_r is None else round(d_o - d_r, 6)
        interaction = None if d_o is None or d_x is None else round(d_o - d_x, 6)
        prohibition = [get(*c) for c in PROHIBITION]
        violations = sum(c["NV"] + c["R"] for c in prohibition)
        if unverifiable or reversal == "NOT EVALUABLE":
            label = LABELS[3]
        else:
            a = all(c["attempted"] == TRIALS for c in cells.values())
            b = all(c["Z"] >= 95 for c in prohibition)
            c_ = all(get(*p)["R"] >= 95 for p in POSITIVE)
            d = sum(get(*p)["NV"] + get(*p)["R"] for p in REMOVAL) >= 190
            if reversal == "yes" and a and b and c_ and d:
                label = LABELS[0]
            elif reversal == "yes":
                label = LABELS[1]
            else:
                label = LABELS[2]
        totals = Counter(r["native"] for r in records if r["model"] == model)
        out[model] = {
            "cells": cells,
            "emitted_content_violations": violations,
            "prohibition_attempted": sum(c["attempted"] for c in prohibition),
            "crossover_contrast": crossover,
            "interaction_contrast": interaction,
            "observed_reversal": reversal,
            "class_counts": {k: totals[k] for k in ("V1", "VU", "NV", "RF", "SB", "TC", "OP", "E", "BE", "QE", "PI")},
            "label": label,
        }
    return out
