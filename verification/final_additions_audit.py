"""Audit of the five additions for the final synthesis, derived from pinned sources.

Standard library only. Reads sources/ (pinned clones or links to them) and two
public archives read-only. Makes no network or model requests. Writes
verification/final_additions_audit.json with public, portable references.
"""
import collections
import glob
import hashlib
import json
import os
import re
import subprocess
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "sources"
OUT = ROOT / "verification" / "final_additions_audit.json"
RUNNER_REPO = "github.com/theonlypal/opus45-opus46-matched-prereg-final"
RUNNER_FROZEN = "1d836fa4c34cd769ba8c9b0334e7ceffa95be0ee"
RUNNER_LOCAL = Path(os.environ.get("OPUS_RUNNER_CLONE", str(Path.home() / "opus45-opus46-matched-prereg-final")))
PSR_DOI = "10.5281/zenodo.21969180"
PSR_ZIP = Path(os.environ.get("PRIMARY_SOURCE_RECORD_ZIP", str(Path.home() / "RAYAN_PAL_PRIMARY_SOURCE_RECORD_2025-12-08_TO_2026-08-15.zip")))
PSR_MD5 = "4471420191e35c495abcd225128e5d0e"

VOID = {"V0", "V1", "V2", "VU"}
INVISIBLE = {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064, 0x2066, 0x2067, 0x2068, 0x2069, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E}
ELLIPSIS = {".", "..", "...", "....", "…", "…."}


def rel(p):
    p = Path(p)
    try:
        return str(p.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        pass
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return p.name


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def pin(repo):
    remote = git(repo, "remote", "get-url", "origin").replace("https://", "").removesuffix(".git")
    return {"source": rel(repo), "repository": remote, "commit": git(repo, "rev-parse", "HEAD"), "tags": git(repo, "tag", "--points-at", "HEAD").split()}


def check_sums(repo, manifest):
    ok = bad = 0
    missing = []
    for line in open(repo / manifest, encoding="utf-8"):
        if not line.strip():
            continue
        digest, path = line.rstrip("\n").split(None, 1)
        p = repo / path.lstrip("*")
        if not p.exists():
            missing.append(path)
        elif sha256_file(p) == digest:
            ok += 1
        else:
            bad += 1
    return {"manifest": manifest, "entries_ok": ok, "entries_bad": bad, "missing": len(missing)}


def tally(classes, keys=("V0", "V1", "V2", "VU", "NV", "R", "RF", "SB", "TC")):
    c = collections.Counter(classes)
    out = {k: c.get(k, 0) for k in keys}
    out["N"] = sum(c.values())
    out["Void"] = sum(c.get(k, 0) for k in VOID)
    out["classes"] = dict(sorted(c.items()))
    return out


def near_void_matrix(text):
    if not text:
        return False
    if all(ord(ch) in INVISIBLE or ch.isspace() for ch in text):
        return True
    return text.strip() in ELLIPSIS


# ------------------------------------------------------------ 1. DOOR-KEY-1
def classify_openai(body):
    ch = body["choices"][0]
    msg = ch["message"]
    stop = ch.get("finish_reason")
    if msg.get("refusal") or stop == "refusal":
        return "RF"
    if stop == "content_filter":
        return "SB"
    if msg.get("tool_calls") or msg.get("function_call"):
        return "TC"
    content = msg.get("content")
    if content:
        near = all(c.isspace() or unicodedata.category(c).startswith("P") or unicodedata.category(c) in ("Cf", "Cc") for c in content)
        return "NV" if near else "R"
    if stop == "stop" and content is not None:
        return "V0"
    if stop == "length":
        return "V1"
    return "VU"


def classify_anthropic(body):
    blocks = body.get("content") or []
    types = [b.get("type") for b in blocks]
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    stop = body.get("stop_reason")
    if stop == "refusal":
        return "RF"
    if "tool_use" in types or stop == "tool_use":
        return "TC"
    if text:
        return "NV" if near_void_matrix(text) else "R"
    if stop == "max_tokens":
        return "V1"
    if stop in ("end_turn", "stop_sequence"):
        return "V0" if "text" in types else "V2"
    return "VU"


def door_key():
    res, pre = SRC / "door-key-1-results", SRC / "door-key-1-preregistration"
    sched = json.load(open(pre / "SCHEDULE.json"))
    prompts = json.load(open(pre / "prompts.json"))
    cells = collections.defaultdict(list)
    meta_match = http_ok = model_ok = 0
    stamps = []
    nv_receipts = []
    for slot in sorted(glob.glob(str(res / "run/receipts/*"))):
        meta = json.load(open(slot + "/meta.json"))
        body = json.loads(open(slot + "/response.bin", "rb").read())
        req = json.loads(open(slot + "/request.json", "rb").read())
        m = meta["model"]
        c = classify_openai(body) if m.startswith("gpt") else classify_anthropic(body)
        if c == meta["native_class"]:
            meta_match += 1
        if meta["http_status"] == 200:
            http_ok += 1
        if meta.get("returned_model") == meta["requested_model"] == m:
            model_ok += 1
        stamps.append((meta["dispatch_utc"], meta["receipt_utc"]))
        sys_text = req["messages"][0]["content"] if m.startswith("gpt") else req.get("system")
        if isinstance(sys_text, list):
            sys_text = "".join(b.get("text", "") for b in sys_text)
        assert sys_text == prompts["system"][meta["arm"]]["text"], slot
        if c == "NV":
            content = body["choices"][0]["message"]["content"] if m.startswith("gpt") else "".join(b.get("text", "") for b in body.get("content", []))
            nv_receipts.append({"slot": meta["slot"], "model": m, "arm": meta["arm"], "input": meta["input"], "utf8_hex": content.encode("utf-8").hex()})
        cells[(m, meta["arm"], meta["input"])].append(c)
    table = []
    for (m, arm, inp), v in sorted(cells.items()):
        t = tally(v)
        table.append({"model": m, "arm": arm, "input": inp, "N": t["N"], "Z": t["V0"] + t["V2"], "V0": t["V0"], "V2": t["V2"], "R": t["R"], "NV": t["NV"], "other": t["N"] - t["V0"] - t["V2"] - t["R"] - t["NV"], "classes": t["classes"]})
    z = {(r["model"], r["arm"], r["input"]): r["Z"] for r in table}
    contrasts = []
    for m in sorted({r["model"] for r in table}):
        d = lambda arm: (z[(m, arm, "lock")] - z[(m, arm, "key")]) / 100
        contrasts.append({"model": m, "crossover": round(d("ORIGINAL") - d("REVERSED"), 4), "interaction": round(d("ORIGINAL") - d("REMOVED"), 4), "emitted_content_violations_in_prohibition_cells": sum(r["R"] + r["NV"] for r in table if r["model"] == m and (r["arm"], r["input"]) in (("ORIGINAL", "lock"), ("REVERSED", "key"))), "prohibition_N": 200})
    zen = json.load(open(ROOT / "verification/records/zenodo-24042127.json"))
    proto = open(pre / "PROTOCOL.md", encoding="utf-8").read()
    gating = [l.strip() for l in proto.splitlines() if re.search(r"≥ ?(95|190)/", l)]
    gpt = {(r["arm"], r["input"]): r for r in table if r["model"].startswith("gpt")}
    return {
        "results_pin": pin(res), "preregistration_pin": pin(pre),
        "results_manifest": check_sums(res, "SHA256SUMS"), "preregistration_manifest": check_sums(pre, "SHA256SUMS"),
        "schedule": {"slots": len(sched), "cells": dict(collections.Counter(f"{s['model']}|{s['arm']}|{s['input']}" for s in sched))},
        "system_prompts": prompts["system"], "inputs": prompts["inputs"],
        "receipts": len(stamps), "http_200": http_ok, "returned_model_equals_requested": model_ok, "derived_class_equals_meta_native_class": meta_match,
        "dates": {"run_utc_start": min(s[0] for s in stamps), "run_utc_end": max(s[1] for s in stamps), "run_local": "2026-11-04 19:08 to 19:33 Pacific (UTC-8)", "results_repository_created_utc": "2026-11-05T03:34:36Z", "zenodo_record_created": zen["created"], "zenodo_publication_date": zen["metadata"]["publication_date"], "zenodo_title": zen["metadata"]["title"], "zenodo_doi": zen["doi"], "zenodo_related": [[x.get("identifier"), x.get("relation")] for x in zen["metadata"].get("related_identifiers", [])], "preregistration_doi": "10.5281/zenodo.23968364"},
        "protocol_gating_lines": gating,
        "contrasts": contrasts,
        "gpt54_prohibition_cells_Z": {"ORIGINAL x lock": gpt[("ORIGINAL", "lock")]["Z"], "REVERSED x key": gpt[("REVERSED", "key")]["Z"]},
        "gating_threshold_Z_per_prohibition_cell": 95,
        "label": "Both GPT-5.4 prohibition cells are below the preregistered gate (Z >= 95/100); the recorded label is observed bidirectional reversal below the gating thresholds. Opus 4.6: no observed bidirectional reversal. No deterministic claim is supported.",
        "NV_receipts": nv_receipts,
        "table": table,
        "method": "Each response.bin reclassified with provider rules equivalent to the vendored classifiers (OpenAI, following the vendored GPT-3.5/GPT-4 A/B rule: refusal, content_filter, tool, nonempty near-void or R, empty string with finish stop V0, finish length V1, any other stop or null content VU, never V2; Anthropic: refusal, tool_use, text blocks near-void or R, max_tokens V1, end_turn V0 or V2). Z = V0 + V2. NV retained separately. Crossover = (Z_lock - Z_key | ORIGINAL) - (Z_lock - Z_key | REVERSED); interaction = (Z_lock - Z_key | ORIGINAL) - (Z_lock - Z_key | REMOVED), with Z as proportions of attempted.",
    }


# ------------------------------------------------------------ 2. prompts
def prompt_row(label, text, source, kind="system"):
    b = text.encode("utf-8")
    return {"label": label, "kind": kind, "source": source, "text": text, "utf8_bytes": len(b), "words_whitespace_split": len(text.split()), "sha256": hashlib.sha256(b).hexdigest(), "utf8_hex": b.hex()}


def prompts():
    rows = []
    mp = json.load(open(SRC / "matrix-raw/void-matrix-evidence-v1.0.0/study/prompts.json"))
    for k, v in sorted(mp["systems"].items()):
        rows.append(prompt_row(f"matrix system_id={k}", v["text"] if isinstance(v, dict) else v, "sources/matrix-raw/void-matrix-evidence-v1.0.0/study/prompts.json"))
    ab = json.loads(open(SRC / "gpt35-gpt4-void-ab/records/requests/t001.attempt-1.json", "rb").read())
    rows.append(prompt_row("gpt35-gpt4-void-ab system", ab["messages"][0]["content"], "sources/gpt35-gpt4-void-ab/records/requests/t001.attempt-1.json"))
    rp = json.loads(open(SRC / "gpt4-0613-void-replay-results/records/requests/t001.attempt-1.json", "rb").read())
    rows.append(prompt_row("gpt4-0613 replay system", rp["messages"][0]["content"], "sources/gpt4-0613-void-replay-results/records/requests/t001.attempt-1.json"))
    op2 = json.loads(open(SRC / "opus45-opus46-matched-results/exp2/attempts/exp2-00001/attempt-01/request.bin", "rb").read())
    rows.append(prompt_row("Opus 4.5/4.6 experiment 2 system", op2["system"], "sources/opus45-opus46-matched-results/exp2/attempts/exp2-00001/attempt-01/request.bin"))
    systems = {}
    for slot in sorted(glob.glob(str(SRC / "opus45-opus46-matched-results/exp3/attempts/exp3-*"))):
        req = json.loads(open(slot + "/attempt-01/request.bin", "rb").read())
        systems.setdefault(req["system"], os.path.basename(slot))
    for i, (t, first) in enumerate(sorted(systems.items(), key=lambda kv: len(kv[0])), 1):
        rows.append(prompt_row(f"Opus 4.5/4.6 experiment 3 system {i} of 4", t, f"sources/opus45-opus46-matched-results/exp3/attempts/{first}/attempt-01/request.bin"))
    op1 = json.loads(open(SRC / "opus45-opus46-matched-results/exp1/attempts/exp1-00001/attempt-01/request.bin", "rb").read())
    rows.append({"label": "Opus 4.5/4.6 experiment 1 system", "kind": "system", "source": "sources/opus45-opus46-matched-results/exp1/attempts/exp1-00001/attempt-01/request.bin", "text": None, "note": "no system field in request", "max_tokens": op1.get("max_tokens")})
    cp = json.load(open(SRC / "gpt-5.4-shrt-cross-script-evidence/evidence/study/prompts.json"))
    for k in ("full_dotted", "full_undotted"):
        rows.append(prompt_row(f"GPT-5.4 cross-script {k} system", cp[k]["system"], "sources/gpt-5.4-shrt-cross-script-evidence/evidence/study/prompts.json"))
    rs = json.load(open(SRC / "gpt-5.4-shrt-prerequisite-reassignment-analysis/evidence/prompts.json"))
    for k in ("S1", "S0"):
        rows.append(prompt_row(f"GPT-5.4 reassignment {k} system", rs[k], "sources/gpt-5.4-shrt-prerequisite-reassignment-analysis/evidence/prompts.json"))
    for k in ("P1", "P0"):
        rows.append(prompt_row(f"GPT-5.4 reassignment {k} user input", rs[k], "sources/gpt-5.4-shrt-prerequisite-reassignment-analysis/evidence/prompts.json", kind="user"))
    dk = json.load(open(SRC / "door-key-1-preregistration/prompts.json"))
    for k, v in dk["system"].items():
        rows.append(prompt_row(f"DOOR-KEY-1 {k} system", v["text"], "sources/door-key-1-preregistration/prompts.json"))
    for k, v in dk["inputs"].items():
        rows.append(prompt_row(f"DOOR-KEY-1 input {k}", v["text"], "sources/door-key-1-preregistration/prompts.json", kind="user"))
    cfg = json.load(open(SRC / "pccg2/config.json"))
    rows.append(prompt_row("PCCG-2 content-side system", cfg["system"], "sources/pccg2/config.json"))
    candidates = [SRC / "zenodo-23070524/evidence/sources/Alignment-Artifact/alignment_test.py"] + sorted(ROOT.glob("evidence/**/alignment_test.py"))
    env = os.environ.get("ORIGIN_EVIDENCE_DIR")
    if env:
        candidates.append(Path(env) / "sources/Alignment-Artifact/alignment_test.py")
    jan_path = next((c for c in candidates if c.exists()), None)
    if jan_path is not None:
        jan = open(jan_path, encoding="utf-8").read()
        m = re.search(r'prompt = "(.*?)"\n', jan)
        rows.append(prompt_row("January 27 alignment_test.py user prompt", m.group(1), "10.5281/zenodo.23070524 embedded evidence.zip: sources/Alignment-Artifact/alignment_test.py", kind="user"))
    else:
        rows.append({"label": "January 27 alignment_test.py user prompt", "kind": "user", "source": "10.5281/zenodo.23070524 embedded evidence.zip: sources/Alignment-Artifact/alignment_test.py", "text": None, "note": "embedded evidence not present under sources/ or evidence/; row not derived"})
    primary = next(r for r in rows if r["label"] == "matrix system_id=primary")
    same = [r["label"] for r in rows if r.get("sha256") == primary["sha256"]]
    return {"rows": rows, "primary_embodiment": {"utf8_bytes": primary["utf8_bytes"], "words_whitespace_split": primary["words_whitespace_split"], "sha256": primary["sha256"], "byte_identical_in": same}, "note": "The frozen primary embodiment system is 115 UTF-8 bytes and 20 whitespace-separated words. The Matrix extended system (162 bytes, 29 words) appends one sentence. The four Opus experiment 3 systems are: the 108-byte prefix without a condition clause; the 163-byte reassignment S1 (condition on شَرْط); the 163-byte reassignment S0 (condition on شَمْس); and a 296-byte variant that adds a clause excluding the instructions themselves from satisfying the prerequisite."}


# ------------------------------------------------------------ 3. taxonomy
def taxonomy():
    mx = SRC / "matrix-raw/void-matrix-evidence-v1.0.0/void_matrix.FROZEN.py"
    proto = json.load(open(SRC / "matrix-raw/void-matrix-evidence-v1.0.0/study/protocol.json"))
    txt = open(mx, encoding="utf-8").read().splitlines()
    i = next(k for k, l in enumerate(txt) if l.startswith("def classify_response("))
    j = next(k for k in range(i, len(txt)) if txt[k].startswith("    evidence = text_evidence("))
    nv_i = next(k for k, l in enumerate(txt) if l.startswith("def near_void("))
    opus = SRC / "door-key-1-preregistration/vendor/opus45-opus46-matched-prereg-final/classifier.py"
    ot = open(opus, encoding="utf-8").read().splitlines()
    oi = next(k for k, l in enumerate(ot) if l.startswith("def near_void("))
    oc = next(k for k, l in enumerate(ot) if l.startswith("    if stop == \"refusal\":"))
    cs = SRC / "gpt-5.4-shrt-cross-script-evidence/evidence_core.py"
    ct = open(cs, encoding="utf-8").read().splitlines()
    ci = next(k for k, l in enumerate(ct) if l.startswith("def classify("))
    rv = SRC / "gpt-5.4-shrt-prerequisite-reassignment-analysis/independent_verifier.py"
    rt = open(rv, encoding="utf-8").read().splitlines()
    ri = next(k for k, l in enumerate(rt) if "if finish == \"content_filter\" or blocked:" in l)
    ab = SRC / "gpt35-gpt4-void-ab/run.py"
    at = open(ab, encoding="utf-8").read().splitlines()
    ai = next(k for k, l in enumerate(at) if "stop=out['finish_reason']" in l)
    dk = SRC / "door-key-1-preregistration/doorkey.py"
    return {
        "matrix": {"file": rel(mx), "sha256": sha256_file(mx), "protocol_taxonomy": proto["classification_taxonomy"], "provider_normal_stops": proto["provider_normal_stops"], "provider_budget_stops": proto["provider_budget_stops"], "classify_response": txt[i:j], "near_void": txt[nv_i:nv_i + 8], "invisible_codepoints": sorted(f"U+{c:04X}" for c in INVISIBLE), "ellipsis_forms": sorted(ELLIPSIS)},
        "opus_runner": {"file": rel(opus), "sha256": sha256_file(opus), "identity": f"{RUNNER_REPO}@{RUNNER_FROZEN}:classifier.py, vendored unchanged by door-key-1-preregistration", "near_void": ot[oi:oi + 6], "class_branch": ot[oc:oc + 18], "note": "Experiment 3 replaces NV/R with exact-target, MX and OT classes; experiments 1 and 2 use NV/R."},
        "cross_script": {"file": rel(cs), "sha256": sha256_file(cs), "near_empty_regex": next(l for l in ct if l.startswith("NEAR_EMPTY_RE")), "classify": ct[ci:ci + 36]},
        "reassignment": {"file": rel(rv), "sha256": sha256_file(rv), "class_branch": rt[ri:ri + 18]},
        "door_key": {"file": rel(dk), "sha256": sha256_file(dk), "Z_definition": "Z_CLASSES = frozenset({\"V0\", \"V2\"}); EMITTED = frozenset({\"NV\", \"R\"}); ZERO_NON_Z = frozenset({\"V1\", \"VU\"})", "openai_vendor_classifier": rel(ab), "openai_vendor_branch": at[ai:ai + 19], "anthropic_vendor_classifier": rel(opus)},
        "findings": [
            "V2 is defined by a missing text container under a recognized normal stop. Normal stops are provider-mapped: anthropic_messages end_turn, google_generate_content STOP, openai_chat and moonshot_chat stop. V2 is therefore not an Anthropic-only or end_turn-only class.",
            "V0 and V2 share the zero-byte normal-stop definition; the difference is only container presence. V1 is the recognized budget stop with zero bytes. VU is zero bytes under an unmapped stop.",
            "NV is study-specific. Matrix and Opus runner: text consisting entirely of whitespace or listed invisible code points, or a bare ellipsis form. Cross-script: full match of whitespace, punctuation, format and control characters. GPT-3.5/GPT-4 A/B (and the DOOR-KEY OpenAI arm, which vendors it): whitespace, any punctuation category, format or control characters. Reassignment verifier: the residual branch after exact targets, scripts, V0 and V1; it is not a near-void text test.",
            "Refusal (RF), safety block (SB) and tool calls (TC) precede the void test in every classifier; HTTP errors are operational classes (E, BE, QE, PI) and never Voids.",
        ],
    }


# ------------------------------------------------------------ 4. matrix
def matrix():
    study = SRC / "matrix-raw/void-matrix-evidence-v1.0.0/study"
    sched = {}
    for line in open(study / "schedule.jsonl", encoding="utf-8"):
        s = json.loads(line)
        sched[s["slot_id"]] = s
    cls = {}
    for line in open(study / "run/events.jsonl", encoding="utf-8"):
        e = json.loads(line)
        if e["event_type"] == "trial_completed":
            cls[e["slot_id"]] = e["classification"]["classification"]
    NULL = {"core_silence", "core_nothing", "core_null"}
    n2c = {"core_silence": "matched_speech", "core_nothing": "matched_something", "core_null": "matched_value"}
    key = lambda s: (s["model_id"], s["study_id"], s["system_id"], s["budget"], s["parameter_track"], s["block"], s["replicate"])
    by = collections.defaultdict(dict)
    for sid, s in sched.items():
        by[key(s)][s["prompt_id"]] = sid
    pairs = [(k[0], p[n], p[c]) for k, p in by.items() for n, c in n2c.items() if n in p and c in p]
    models = sorted({s["model_id"] for s in sched.values()})
    per = {}
    for m in models:
        ids = [sid for sid, s in sched.items() if s["model_id"] == m]
        core = {}
        for st, b, tr in sorted({(s["study_id"], s["budget"], s["parameter_track"]) for s in sched.values() if s["model_id"] == m and s["study_id"] in ("core_100", "core_4000")}):
            sel = [sid for sid in ids if sched[sid]["study_id"] == st and sched[sid]["budget"] == b and sched[sid]["parameter_track"] == tr]
            core[f"{st}|{b}|{tr}"] = {"null": tally(cls[sid] for sid in sel if sched[sid]["prompt_id"] in NULL), "control": tally(cls[sid] for sid in sel if sched[sid]["prompt_id"].startswith(("control_", "matched_")))}
        per[m] = {"strict_null": tally(cls[n] for mm, n, _ in pairs if mm == m), "strict_control": tally(cls[c] for mm, _, c in pairs if mm == m), "full_census": tally(cls[sid] for sid in ids), "core_null_total": tally(cls[sid] for sid in ids if sched[sid]["study_id"] in ("core_100", "core_4000") and sched[sid]["prompt_id"] in NULL), "core_by_study_budget_track": core, "pooled_controls_incl_logical_yes": tally(cls[sid] for sid in ids if sched[sid]["prompt_id"].startswith(("control_", "matched_")) or sched[sid]["prompt_id"] == "logical_yes")}
    all_pooled = tally(cls[sid] for sid, s in sched.items() if s["prompt_id"].startswith(("control_", "matched_")) or s["prompt_id"] == "logical_yes")
    ns_ctrl = [[sched[sid]["model_id"], sched[sid]["study_id"], sched[sid]["prompt_id"], sched[sid]["budget"]] for sid, s in sched.items() if (s["prompt_id"].startswith(("control_", "matched_")) or s["prompt_id"] == "logical_yes") and cls[sid] in ("V0", "V2")]
    return {
        "source": "sources/matrix-raw/void-matrix-evidence-v1.0.0 (10.5281/zenodo.21696066; analysis github.com/theonlypal/void-matrix-complete-analysis@3fd330869c1a4a410047bc70b3f661f1a9d69aca)",
        "scheduled": len(sched), "completed": len(cls), "strict_pairs": len(pairs),
        "models": per,
        "opus46_core_nulls": per["claude-opus-4-6"]["core_null_total"],
        "opus46_strict_null": per["claude-opus-4-6"]["strict_null"],
        "V2_by_model_full_census": {m: per[m]["full_census"]["V2"] for m in models},
        "V2_models": [m for m in models if per[m]["full_census"]["V2"] > 0],
        "pooled_controls_all_models": all_pooled,
        "pooled_control_definition": "control_cat, control_hello, matched_speech, matched_something, matched_value and logical_yes across all studies: 12,340 trials, 823 Voids, 3 normal-stop Voids, matching the published complete-analysis README. Without logical_yes: 10,140 trials, 598 Voids.",
        "pooled_control_normal_stop_voids": ns_ctrl,
        "findings": [
            "Opus 4.6 core nulls: 900/900 V2 across core_100 (provider_default 300, temperature_zero 300) and core_4000 (300). The strict matched figure 331/390 is a different denominator: 390 null slots that have a designated matched control (core_4000 300 plus equivalence_9 90), of which 331 are V2, 40 R and 19 NV.",
            "Gemini 3.5 Flash is the second V2 model: 499 V2 in the full census (3,180) and 106 V2 among its 390 strict nulls; it also records 178 V1 at the 100-token ceiling. V2 is not unique to Anthropic.",
            "At the 100-token ceiling the Void subtype shifts to V1 for several models (Opus 5 300/300, Kimi K3 300/300, Fable 5 197/300), while Opus 4.6 remains V2 and the GPT-4 and GPT-5.2 identifiers remain V0. Low-budget controls are visible for most models, with V1 controls on Fable 5 (128/200), Opus 5 (200/200), Kimi K3 (198/200) and Gemini (35/400).",
        ],
    }


# ------------------------------------------------------------ 5. February / October
EMAIL_MEMBERS = {
    "2026-02-06": "gmail-evidence/01_EVIDENCE_SELECTED/EMAIL__20260206__19c34c0d77834e40__opus-4-5-vs-opus-4-6-void-phenomenon/DERIVED/02__BODY.txt",
    "2026-02-10": "gmail-evidence/01_EVIDENCE_SELECTED/EMAIL__20260210__19c4945569479603__cerebral-valley-opus-4-6-hackathon-submission/DERIVED/02__BODY.txt",
    "2026-02-13": "gmail-evidence/01_EVIDENCE_SELECTED/EMAIL__20260213__19c59a9e7ac1b674__re-opus-4-5-vs-opus-4-6-void-phenomenon/DERIVED/02__BODY.txt",
}
CJK = [(0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x3040, 0x30FF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF)]


def is_cjk(ch):
    return any(a <= ord(ch) <= b for a, b in CJK)


def feb_oct():
    archive = {"doi": PSR_DOI, "record": "Rayan Pal Primary Source Record: December 8, 2025 – August 15, 2026", "file": "RAYAN_PAL_PRIMARY_SOURCE_RECORD_2025-12-08_TO_2026-08-15.zip", "zenodo_md5": PSR_MD5}
    bodies = {}
    if PSR_ZIP.exists():
        archive["local_md5_matches_zenodo"] = hashlib.md5(open(PSR_ZIP, "rb").read()).hexdigest() == PSR_MD5
        with zipfile.ZipFile(PSR_ZIP) as z:
            prefix = "RAYAN_PAL_PRIMARY_SOURCE_RECORD_2025-12-08_TO_2026-08-15/"
            manifest = z.read(prefix + "gmail-evidence/SHA256SUMS.txt").decode("utf-8")
            archive["gmail_manifest_sha256"] = hashlib.sha256(manifest.encode()).hexdigest()
            listed = dict(l.split("  ", 1) [::-1] for l in manifest.splitlines() if "  " in l)
            for date, member in EMAIL_MEMBERS.items():
                data = z.read(prefix + member)
                digest = hashlib.sha256(data).hexdigest()
                bodies[date] = {"archive_member": member, "sha256": digest, "listed_in_archive_manifest": listed.get(member.split("gmail-evidence/", 1)[1]) == digest, "text": data.decode("utf-8", "replace")}
    else:
        archive["local_md5_matches_zenodo"] = None
    feb6 = bodies.get("2026-02-06", {}).get("text", "")
    rows = re.findall(r"^(\S) \(([^)]*)\) (VOID|RESPONDS) (VOID|RESPONDS)", feb6, re.M)
    feb_table = [{"input": c, "gloss": g, "cjk_ideograph": is_cjk(c), "opus45": a, "opus46": b} for c, g, a, b in rows]
    remain = [r["input"] for r in feb_table if r["opus46"] == "VOID"]
    code = re.search(r"max_tokens=1", feb6) is not None
    # October experiment 1
    res = SRC / "opus45-opus46-matched-results"
    per = collections.Counter()
    for slot in sorted(glob.glob(str(res / "exp1/attempts/exp1-*"))):
        req = json.loads(open(slot + "/attempt-01/request.bin", "rb").read())
        c = json.load(open(slot + "/attempt-01/classification.json"))
        u = req["messages"][0]["content"]
        if isinstance(u, list):
            u = u[0]["text"]
        per[(c["returned_model"], u, c["class"])] += 1
    chars = sorted({k[1] for k in per})
    oct_table = []
    for ch in chars:
        row = {"input": ch, "cjk_ideograph": is_cjk(ch)}
        for m in ("claude-opus-4-5-20251101", "claude-opus-4-6"):
            row[m] = {k[2]: v for k, v in sorted(per.items()) if k[0] == m and k[1] == ch}
        f = next((r for r in feb_table if r["input"] == ch), None)
        row["february_opus45"] = f["opus45"] if f else None
        row["february_opus46"] = f["opus46"] if f else None
        oct_table.append(row)
    proto = json.loads(git(RUNNER_LOCAL, "show", f"{RUNNER_FROZEN}:protocol.json"))["experiments"]["1"] if RUNNER_LOCAL.exists() else None
    prereg_p4 = [l for l in git(RUNNER_LOCAL, "show", f"{RUNNER_FROZEN}:PREREG.md").splitlines() if l.startswith("P4.")] if RUNNER_LOCAL.exists() else None
    seal = json.load(open(res / "opus45-opus46-matched-prereg-final-runs.seal.json"))
    v1 = lambda m: sum(v for k, v in per.items() if k[0] == m and k[2] == "V1")
    r_ = lambda m: sum(v for k, v in per.items() if k[0] == m and k[2] == "R")
    return {
        "public_archive": archive,
        "february_account": {
            "members": {d: {k: v for k, v in b.items() if k != "text"} for d, b in bodies.items()},
            "earliest_record": "Email dated 2026-02-06 (Pacific), subject Opus 4.5 vs Opus 4.6 (Void Phenomenon), preserved in the public primary-source archive; the 2026-02-10 hackathon email restates it.",
            "method_as_stated": "messages.create(model, messages=[{role: user, content: <input>}], max_tokens=1, temperature=0); VOID if content == '' else RESPONDS",
            "code_block_present": code,
            "inputs": feb_table, "input_count": len(feb_table), "cjk_ideograph_count": sum(1 for r in feb_table if r["cjk_ideograph"]), "non_cjk_symbols": [r["input"] for r in feb_table if not r["cjk_ideograph"]],
            "opus46_changed": sum(1 for r in feb_table if r["opus45"] != r["opus46"]), "opus46_remaining_void": remain,
            "evidence_bound": "The account is an attributed historical statement preserved in a hash-manifested public archive. It carries no provider stop metadata, response ids or raw bodies, so it cannot be classified under the frozen taxonomy and must not be labelled V0, V1 or V2. No count from it is a measurement in this synthesis.",
        },
        "october_replication": {"source": pin(res), "doi": "10.5281/zenodo.23751813", "preregistration_doi": seal.get("preregistration_doi"), "runner": f"{RUNNER_REPO}@{RUNNER_FROZEN}", "protocol_experiment_1": proto, "prereg_prediction_P4": prereg_p4, "completed_at_utc": json.load(open(res / "exp1/completion.json"))["completed_at_utc"], "requests": sum(per.values()), "per_input": oct_table,
            "opus45_V1": v1("claude-opus-4-5-20251101"), "opus45_R": r_("claude-opus-4-5-20251101"), "opus46_V1": v1("claude-opus-4-6"), "opus46_R": r_("claude-opus-4-6"),
            "opus46_inputs_all_V1": [r["input"] for r in oct_table if r["claude-opus-4-6"].get("V1") == 30], "opus46_inputs_split": [[r["input"], r["claude-opus-4-6"]] for r in oct_table if 0 < r["claude-opus-4-6"].get("V1", 0) < 30], "opus45_inputs_not_all_V1": [[r["input"], r["claude-opus-4-5-20251101"]] for r in oct_table if r["claude-opus-4-5-20251101"].get("V1") != 30]},
        "findings": [
            "The historical account is dated 2026-02-06 (restated 2026-02-10); the replication is experiment 1 of the Opus 4.5 versus 4.6 study, preregistered and run on 2026-10-28: 18 inputs (16 CJK ideographs and the two symbols ⊥ and ☯), two models, 30 replicates, max_tokens 1, no system prompt, 1,080 requests.",
            "October outcome under the frozen taxonomy: Opus 4.5 539/540 V1 with one R (正); Opus 4.6 165/540 V1 and 375/540 R. Five inputs are 30/30 V1 on Opus 4.6 (空, 有, 善, 一, ⊥), the same five the February account listed as remaining; ☯ is 15/30 V1 in October where the February account recorded RESPONDS.",
            "February and October are different records with different methods and evidential status and must be reported with their own dates; the February table is quoted as an attributed account, the October table is a hash-chained receipt set classified by the frozen runner.",
        ],
    }


def write_february_excerpt(f):
    acc = f["february_account"]
    excerpt = {
        "record": "February 2026 historical account, measurement excerpt",
        "public_source": {"doi": f["public_archive"]["doi"], "url": "https://zenodo.org/records/21969180", "archive_file": f["public_archive"]["file"], "archive_md5": f["public_archive"]["zenodo_md5"], "gmail_manifest_member": "gmail-evidence/SHA256SUMS.txt", "gmail_manifest_sha256": f["public_archive"].get("gmail_manifest_sha256")},
        "members": acc["members"],
        "earliest_record_date": "2026-02-06",
        "restated_date": "2026-02-10",
        "method_as_stated": acc["method_as_stated"],
        "inputs": acc["inputs"],
        "input_count": acc["input_count"], "cjk_ideograph_count": acc["cjk_ideograph_count"], "non_cjk_symbols": acc["non_cjk_symbols"],
        "opus46_changed": acc["opus46_changed"], "opus46_remaining_void": acc["opus46_remaining_void"],
        "classification": "Not assignable. The account records an empty string under a one-token ceiling with no finish or stop metadata, response id or raw body; it cannot be assigned V0, V1, V2 or VU under the frozen taxonomy. It is quoted as an attributed historical account, not as a measurement.",
        "excluded_from_this_excerpt": "message headers, recipients, addresses and all body text other than the measurement table and the stated method",
    }
    (ROOT / "verification" / "february_2026_account.json").write_text(json.dumps(excerpt, indent=1, ensure_ascii=False), encoding="utf-8")


def main():
    report = {"generated_by": "verification/final_additions_audit.py", "addition_1_door_key": door_key(), "addition_2_prompts": prompts(), "addition_3_taxonomy": taxonomy(), "addition_4_matrix": matrix(), "addition_5_february_october": feb_oct()}
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    write_february_excerpt(report["addition_5_february_october"])
    print("wrote", rel(OUT), "and verification/february_2026_account.json")
    dk = report["addition_1_door_key"]
    print("DOOR-KEY: receipts", dk["receipts"], "| derived==meta", dk["derived_class_equals_meta_native_class"], "| contrasts", dk["contrasts"])
    print("primary embodiment:", report["addition_2_prompts"]["primary_embodiment"])
    m = report["addition_4_matrix"]
    print("opus46 core nulls:", m["opus46_core_nulls"]["classes"], "| V2 models:", m["V2_models"], "| pooled:", m["pooled_controls_all_models"]["N"], m["pooled_controls_all_models"]["Void"])
    f = report["addition_5_february_october"]
    print("archive:", f["public_archive"], "| members:", {d: v["listed_in_archive_manifest"] for d, v in f["february_account"]["members"].items()})
    print("feb inputs", f["february_account"]["input_count"], "cjk", f["february_account"]["cjk_ideograph_count"], "symbols", f["february_account"]["non_cjk_symbols"], "changed", f["february_account"]["opus46_changed"], "remain", f["february_account"]["opus46_remaining_void"])
    o = f["october_replication"]
    print("oct: 4.5 V1", o["opus45_V1"], "R", o["opus45_R"], "| 4.6 V1", o["opus46_V1"], "R", o["opus46_R"], "| split", o["opus46_inputs_split"], "| 4.5 not all V1", o["opus45_inputs_not_all_V1"])
    absolute = [l for l in json.dumps(report).split('"') if l.startswith("/")]
    print("absolute paths in output:", len(absolute))


if __name__ == "__main__":
    main()
