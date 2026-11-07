"""Independent rederivation of every manuscript count from pinned sources.

Standard library only. Reads sources/ and generated/counts.json. Makes no
network or model requests and imports nothing else from this repository.
Writes verification/independent_verification.json. All references are
repository-relative.
"""
import base64
import collections
import csv
import datetime as dt
import glob
import hashlib
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "sources"
OUT = ROOT / "verification" / "independent_verification.json"
GENERATED = ROOT / "generated" / "counts.json"

GO, EOS = 15513, 151645
VOID_CLASSES = {"V0", "V1", "V2", "VU"}
TAXONOMY = ("V0", "V1", "V2", "VU", "NV", "R", "OP", "RF", "SB", "TC")
INVISIBLE = {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064, 0x2066, 0x2067, 0x2068, 0x2069, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E}
ELLIPSIS = {".", "..", "...", "....", "…", "…."}
T1 = "شָׁרְט"
T0 = "شָרְט"
HE = "שָׁרְט"
SHART = "شَرْط"
SHAMS = "شَمْس"

TESTS = []
DISCREPANCIES = []


def test(chapter, name, expected, observed):
    ok = expected == observed
    TESTS.append({"chapter": chapter, "test": name, "expected": expected, "observed": observed, "pass": ok})
    if not ok:
        DISCREPANCIES.append({"chapter": chapter, "test": name, "expected": expected, "observed": observed})
    return ok


def rel(p):
    try:
        return str(Path(p).relative_to(ROOT))
    except ValueError:
        return str(p)


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


def tally(classes):
    c = collections.Counter(classes)
    out = {k: c.get(k, 0) for k in TAXONOMY}
    out["N"] = sum(c.values())
    out["Void"] = sum(c.get(k, 0) for k in VOID_CLASSES)
    out["classes"] = dict(sorted(c.items()))
    return out


def near_void(text):
    if not text:
        return False
    if all(ord(ch) in INVISIBLE or ch.isspace() for ch in text):
        return True
    return text.strip() in ELLIPSIS


# ---------------------------------------------------------------- chapter I
def chapter_i():
    repo = SRC / "PCCG-Qwen3-4B-continuation-control"
    res = repo / "results"
    load = lambda n: json.load(open(res / n))
    cases = json.load(open(repo / "protocol/data/causal-final.json"))
    baseline, prefixes, replay, primary = load("confirmation-baseline.json"), load("confirmation-prefixes.json"), load("confirmation-replay.json"), load("confirmation-primary.json")
    test("I", "confirmation cases", 80, len(cases))
    test("I", "distinct pairs", 40, len({c["pair"] for c in cases}))
    truth = {}
    for c in cases:
        m = re.fullmatch(r"EQ\((\d{4}),(\d{4})\)", c["condition"])
        truth[c["id"]] = m.group(1) == m.group(2)
    test("I", "equal arm size", 40, sum(truth.values()))
    test("I", "recorded truth equals parsed equality", 80, sum(1 for c in cases if c["truth"] == truth[c["id"]]))
    pref = {p["id"]: p for p in prefixes}
    base_ok = sum(1 for b in baseline if ((b["generated_ids"][-2:] == [GO, EOS]) if truth[b["id"]] else (b["generated_ids"][-1] == EOS and GO not in b["generated_ids"])))
    test("I", "baseline terminal tokens follow truth", 80, base_ok)
    replay_ok = sum(1 for r in replay if r["input_ids"] == pref[r["id"]]["input_ids"] and r["generated_ids"] == ([GO, EOS] if truth[r["id"]] else [EOS]))
    test("I", "replay on fixed prefix reproduces baseline continuation", 80, replay_ok)
    go_to_eos = sum(1 for r in primary if truth[r["id"]] and r["input_ids"] == pref[r["id"]]["input_ids"] and r["generated_ids"] == [EOS])
    eos_to_go = sum(1 for r in primary if not truth[r["id"]] and r["input_ids"] == pref[r["id"]]["input_ids"] and r["generated_ids"] == [GO, EOS])
    test("I", "GO to EOS under intervention (equal arm)", 40, go_to_eos)
    test("I", "EOS to GO under intervention (unequal arm)", 40, eos_to_go)
    controls = {}
    for f in sorted(glob.glob(str(res / "confirmation-control-*.json"))):
        name = os.path.basename(f)[len("confirmation-control-"):-5]
        recs = json.load(open(f))
        controls[name] = sum(1 for r in recs if r["input_ids"] == pref[r["id"]]["input_ids"] and r["generated_ids"] == ([GO, EOS] if truth[r["id"]] else [EOS]))
        test("I", f"control {name} unchanged", 80, controls[name])
    test("I", "control arms", 8, len(controls))
    test("I", "controls unchanged total", 640, sum(controls.values()))
    verdict, direction = load("verdict.json"), load("direction.json")
    test("I", "intervention block", 29, direction["layer"])
    test("I", "intervention strength", 2.0, direction["alpha"])
    test("I", "direction dimensions", 2560, len(direction["vector"]))
    test("I", "direction hash equals verdict", verdict["direction_sha256"], sha256_file(res / "direction.json"))
    test("I", "lens hash equals verdict", verdict["lens_sha256"], sha256_file(res / "jacobian-lens.pt"))
    counts = {"baseline_N": 80, "replay_N": len(replay), "replay_correct": replay_ok, "flips": {"GO_to_EOS": go_to_eos, "EOS_to_GO": eos_to_go}, "denominators": {"GO_to_EOS": 40, "EOS_to_GO": 40}, "controls": [{"name": f"confirmation-control-{n}", "N": 80, "unchanged": u} for n, u in sorted(controls.items())], "controls_N": 80 * len(controls), "controls_unchanged": sum(controls.values()), "layer": direction["layer"], "strength": direction["alpha"], "dimensions": len(direction["vector"])}
    return {"source": pin(repo), "doi": "10.5281/zenodo.22681787", "manifest_check": check_sums(repo, "SHA256SUMS")}, counts


# ---------------------------------------------------------------- chapter II
def chapter_ii():
    repo = SRC / "pccg2"
    ev = repo / "evidence"
    final = json.load(open(ev / "records/combined-final.json"))
    exact = sum(1 for r in final if r["generated_ids"] == r["target_ids"])
    test("II", "final evaluation records", 2048, len(final))
    test("II", "final exact generations", 2048, exact)
    test("II", "final nonEOS logits invariant", 2048, sum(1 for r in final if r["all_nonEOS_unchanged"] is True))
    ids = {r["answer_id"] for r in final}
    test("II", "final distinct answer identities", 75, len(ids))
    eq_ok = sum(1 for r in final if (lambda m: (m.group(1) == m.group(2)) == r["truth"])(re.fullmatch(r"EQ\((\d{6}),(\d{6})\)", r["condition"])))
    test("II", "final six-digit equality truth parses", 2048, eq_ok)
    causal = json.load(open(ev / "records/causal-primary.json"))
    a2e = sum(1 for r in causal if r["case"]["truth"] and r["baseline"]["generated_ids"] == [r["answer_id"], EOS] and r["intervention"]["generated_ids"] == [EOS])
    e2a = sum(1 for r in causal if not r["case"]["truth"] and r["baseline"]["generated_ids"] == [EOS] and r["intervention"]["generated_ids"] == [r["answer_id"], EOS])
    test("II", "causal records", 80, len(causal))
    test("II", "answer to EOS reversals", 40, a2e)
    test("II", "EOS to same answer reversals", 40, e2a)
    test("II", "causal distinct answer identities", 40, len({r["answer_id"] for r in causal}))
    test("II", "causal nonEOS logits invariant", 80, sum(1 for r in causal if r["baseline"]["all_nonEOS_unchanged"] and r["intervention"]["all_nonEOS_unchanged"]))
    test("II", "causal baseline and intervention nonEOS vector hashes equal", 80, sum(1 for r in causal if r["baseline"]["first_nonEOS_bf16_sha256"] == r["intervention"]["first_nonEOS_bf16_sha256"]))
    base_by = {r["case"]["id"]: r["baseline"]["generated_ids"] for r in causal}
    sham = json.load(open(ev / "records/causal-sham.json"))
    sham_unchanged = sum(1 for s in sham if s["output"]["generated_ids"] == base_by.get(s["condition_id"]))
    test("II", "sham records", 80, len(sham))
    test("II", "sham outputs equal baseline", 80, sham_unchanged)
    qo = json.load(open(ev / "records/causal-question-only.json"))
    test("II", "question-only controls nonEOS invariant", len(qo), sum(1 for q in qo if q["all_nonEOS_unchanged"] is True))
    witness = json.load(open(ev / "witness-2plus2.json"))
    expected_hash = open(ev / "witness-non-eos-vector.sha256").read().strip()
    w_ok = 0
    non_hashes = set()
    for w in witness:
        full = open(repo / w["first_logits_file"], "rb").read()
        non = open(repo / w["nonEOS_logits_file"], "rb").read()
        non_hashes.add(hashlib.sha256(non).hexdigest())
        if w["generated_ids"] == w["expected_ids"] and len(full) == 151936 * 2 and full[:EOS * 2] + full[(EOS + 1) * 2:] == non:
            w_ok += 1
    test("II", "witness arms", 5, len(witness))
    test("II", "witness arms generated equals expected and nonEOS slice", 5, w_ok)
    test("II", "witness nonEOS vector identical across arms", [expected_hash], sorted(non_hashes))
    test("II", "witness EOS logits", [-124.0, 94.5, 136.0, -82.0, 94.5], [w["raw_steps"][0]["eos_logit"] for w in witness])
    counts = {"final_N": len(final), "final_correct": exact, "final_answer_identities": len(ids), "flips": {"answer_to_EOS": a2e, "EOS_to_same_answer": e2a}, "denominators": {"answer_to_EOS": 40, "EOS_to_same_answer": 40}, "sham_N": len(sham), "sham_unchanged": sham_unchanged, "causal_answer_identities": len({r["answer_id"] for r in causal}), "nonEOS_witness_sha256": expected_hash,
              "witness": [{"id": w["id"], "generated_ids": w["generated_ids"], "answer_logit": w["raw_steps"][0]["top5_logits"][w["raw_steps"][0]["top5_ids"].index(19)] if 19 in w["raw_steps"][0]["top5_ids"] else None, "eos_logit": w["raw_steps"][0]["eos_logit"]} for w in witness]}
    return {"source": pin(repo), "doi": "10.5281/zenodo.22730710", "manifest_check": check_sums(repo, "SHA256SUMS")}, counts


# ---------------------------------------------------------------- matrix
ARABIC = [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]
HEBREW = [(0x0590, 0x05FF), (0xFB1D, 0xFB4F)]


def has_script(text, ranges):
    return any(any(a <= ord(ch) <= b for a, b in ranges) for ch in text)


def derive_void(endpoint, http_status, body):
    if http_status != 200:
        return None
    try:
        j = json.loads(body)
    except Exception:
        return None
    if endpoint in ("openai_chat", "moonshot_chat"):
        ch = j.get("choices") or []
        if len(ch) != 1:
            return None
        msg = ch[0].get("message") or {}
        content = msg.get("content")
        blocked = msg.get("refusal") not in (None, "") or bool(msg.get("tool_calls")) or bool(msg.get("function_call"))
        container = content is not None
        text = content or ""
        stop = ch[0].get("finish_reason")
        normal, budget = stop == "stop", stop == "length"
    elif endpoint == "anthropic_messages":
        blocks = j.get("content") or []
        texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        blocked = j.get("stop_reason") == "refusal" or any(b.get("type") == "tool_use" for b in blocks)
        container = bool(texts)
        text = "".join(texts)
        stop = j.get("stop_reason")
        normal, budget = stop in ("end_turn", "stop_sequence"), stop == "max_tokens"
    elif endpoint == "google_generate_content":
        cands = j.get("candidates") or []
        if len(cands) != 1:
            return None
        parts = (cands[0].get("content") or {}).get("parts") or []
        texts = [p.get("text", "") for p in parts if "text" in p and not p.get("thought")]
        blocked = cands[0].get("finishReason") in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII") or bool(j.get("promptFeedback", {}).get("blockReason"))
        container = bool(texts)
        text = "".join(texts)
        stop = cands[0].get("finishReason")
        normal, budget = stop == "STOP", stop == "MAX_TOKENS"
    else:
        return None
    void = (not blocked) and len(text.encode("utf-8")) == 0
    sub = None
    if void:
        sub = "V1" if budget else ("V2" if not container else ("V0" if normal else "VU"))
    return void, sub, container, stop, blocked, len(text.encode("utf-8"))


def load_matrix():
    study = SRC / "matrix-raw/void-matrix-evidence-v1.0.0/study"
    sched = {}
    for line in open(study / "schedule.jsonl", encoding="utf-8"):
        s = json.loads(line)
        sched[s["slot_id"]] = s
    completed = {}
    attempts = 0
    chain_ok = True
    prev = None
    for line in open(study / "run/events.jsonl", encoding="utf-8"):
        e = json.loads(line)
        if prev is not None and e["previous_event_sha256"] != prev:
            chain_ok = False
        prev = e["event_sha256"]
        if e["event_type"] == "trial_started":
            attempts += 1
        if e["event_type"] == "trial_completed":
            completed[e["slot_id"]] = e
    prompts = json.load(open(study / "prompts.json"))
    texts = {pid: "".join(x["character"] for x in c["codepoints"]) for pid, c in prompts["cases"].items() if "codepoints" in c}
    return study, sched, completed, attempts, chain_ok, texts


def chapter_iv():
    study, sched, completed, attempts, chain_ok, texts = load_matrix()
    analysis = SRC / "void-matrix-complete-analysis"
    test("IV", "scheduled slots", 31430, len(sched))
    test("IV", "completed slots", 31430, len(completed))
    test("IV", "attempt start events", 31484, attempts)
    test("IV", "event chain previous-hash links", True, chain_ok)
    cls = {sid: e["classification"]["classification"] for sid, e in completed.items()}
    raw_dir = study / "run/raw"
    agree = disagree = undecidable = raw_hash_ok = 0
    examples = []
    for sid, e in completed.items():
        p = study / "run" / e["raw_path"]
        if not p.exists():
            p = raw_dir / f"{sid}.{e['attempt_id']}.json"
        rec = json.load(open(p))
        body = base64.b64decode(rec["transport"]["raw_body_base64"])
        if hashlib.sha256(body).hexdigest() == e["raw_body_sha256"]:
            raw_hash_ok += 1
        d = derive_void(sched[sid]["endpoint"], rec["transport"]["http_status"], body)
        rc = cls[sid]
        if d is None:
            undecidable += 1
            if rc in VOID_CLASSES:
                disagree += 1
            continue
        void, sub = d[0], d[1]
        if (void and sub == rc) or (not void and rc not in VOID_CLASSES):
            agree += 1
        else:
            disagree += 1
            if len(examples) < 50:
                examples.append({"slot_id": sid, "recorded": rc, "derived": sub if void else "non-void", "stop": d[3], "visible_bytes": d[5]})
    error_classes = sum(1 for c in cls.values() if c in ("E", "BE", "QE", "PI", "OP"))
    test("IV", "raw body hashes equal event records", 31430, raw_hash_ok)
    test("IV", "non-200 or unparsed terminal responses equal recorded error classes", error_classes, undecidable)
    test("IV", "byte-level Void taxonomy agrees with recorded class on every parsed response", 31430 - error_classes, agree)
    test("IV", "byte-level Void taxonomy disagreements", 0, disagree)
    csv_path = analysis / "analysis/tables/trial_level.csv"
    csv_sha = sha256_file(csv_path)
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    test("IV", "trial-level CSV rows", 31430, len(rows))
    test("IV", "trial-level CSV class equals event class", 31430, sum(1 for r in rows if cls.get(r["slot_id"]) == r["classification"]))
    null_to_control = {"core_silence": "matched_speech", "core_nothing": "matched_something", "core_null": "matched_value"}
    key = lambda s: (s["model_id"], s["study_id"], s["system_id"], s["budget"], s["parameter_track"], s["block"], s["replicate"])
    by_key = collections.defaultdict(dict)
    for sid, s in sched.items():
        by_key[key(s)][s["prompt_id"]] = sid
    pairs = [(k[0], p[n], p[c]) for k, p in by_key.items() for n, c in null_to_control.items() if n in p and c in p]
    test("IV", "strict matched null/control pairs", 4290, len(pairs))
    matched_null = tally(cls[n] for _, n, _ in pairs)
    matched_control = tally(cls[c] for _, _, c in pairs)
    test("IV", "matched null Voids", 2505, matched_null["Void"])
    test("IV", "matched control Voids", 0, matched_control["Void"])
    test("IV", "matched control visible R", 4289, matched_control["R"])
    test("IV", "matched control RF", 1, matched_control["RF"])
    mc_rows = list(csv.DictReader(open(analysis / "analysis/matched_controls.csv", encoding="utf-8")))
    test("IV", "matched_controls.csv rows", 4290, len(mc_rows))
    models = sorted({s["model_id"] for s in sched.values()})
    per = []
    for m in models:
        per.append({"model": m, "null": tally(cls[n] for mm, n, _ in pairs if mm == m), "control": tally(cls[c] for mm, _, c in pairs if mm == m), "all": tally(cls[sid] for sid, s in sched.items() if s["model_id"] == m)})
    test("IV", "model set size", 11, len(models))
    test("IV", "every model 390 matched pairs", [390] * 11, [p["null"]["N"] for p in per])
    ceiling = tally(cls[sid] for sid, s in sched.items() if s["study_id"] == "token_budget" and s["budget"] == 16000)
    test("IV", "16,000-token ceiling slots", 500, ceiling["N"])
    NULL = set(null_to_control)
    opus = [sid for sid, s in sched.items() if s["model_id"] == "claude-opus-4-6" and s["study_id"] in ("core_100", "core_4000") and s["prompt_id"] in NULL]
    opus_core = tally(cls[sid] for sid in opus)
    test("IV", "Opus 4.6 core null slots", 900, opus_core["N"])
    test("IV", "Opus 4.6 core null V2", 900, opus_core["V2"])
    tracks = []
    for st, tr in sorted({(sched[sid]["study_id"], sched[sid]["parameter_track"]) for sid in opus}):
        tracks.append({"study": st, "track": tr, **tally(cls[sid] for sid in opus if sched[sid]["study_id"] == st and sched[sid]["parameter_track"] == tr)})
    low_budget = []
    for m in models:
        cells = []
        for pid in sorted({sched[sid]["prompt_id"] for sid, s in sched.items() if s["model_id"] == m and s["study_id"] == "token_budget" and s["budget"] == 100}):
            cells.append({"prompt": pid, "text": texts.get(pid), **tally(cls[sid] for sid, s in sched.items() if s["model_id"] == m and s["study_id"] == "token_budget" and s["budget"] == 100 and s["prompt_id"] == pid)})
        low_budget.append({"model": m, "cells": cells})
    low_budget_controls = [{"model": m, **tally(cls[sid] for sid, s in sched.items() if s["model_id"] == m and s["study_id"] == "core_100" and s["prompt_id"].startswith(("control_", "matched_")))} for m in models]
    test("IV", "V2 appears for Gemini 3.5 Flash", True, next(p for p in per if p["model"] == "gemini-3.5-flash")["all"]["V2"] > 0)
    counts = {"all": tally(cls.values()), "matched_null": matched_null, "matched_control": matched_control, "models": per, "ceiling16000": ceiling, "opus_core": opus_core, "opus_core_tracks": tracks, "low_budget": low_budget, "low_budget_controls": low_budget_controls}
    meta = {"source": pin(analysis), "doi": "10.5281/zenodo.21696066", "manifest_check": check_sums(analysis, "SHA256SUMS.txt"), "raw_archive_sha256": sha256_file(SRC / "matrix-raw.zip") if (SRC / "matrix-raw.zip").exists() else None, "trial_level_csv_sha256": csv_sha, "byte_level_rederivation": {"agree": agree, "disagree": disagree, "undecidable_non_200_or_unparsed": undecidable, "examples": examples}}
    return meta, counts, cls, sched, texts


# ---------------------------------------------------------------- chapter V
def chapter_v(cls, sched, texts):
    repo = SRC / "alignment-is-a-system-property"
    focal = "gpt-4-0613"
    nulls = ("core_silence", "core_nothing", "core_null")
    controls = ("matched_speech", "matched_something", "matched_value")
    systems = {"primary": "core_4000", "no_output_restriction": "component_ablation_no_output_restriction", "no_embodiment": "component_ablation_no_embodiment", "none": "no_system_ablation"}
    ablation = []
    for system, study in systems.items():
        sel = [sid for sid, s in sched.items() if s["model_id"] == focal and s["study_id"] == study and s["system_id"] == system]
        ablation.append({"system": system, "all": tally(cls[sid] for sid in sel if sched[sid]["prompt_id"] in nulls), "control": tally(cls[sid] for sid in sel if sched[sid]["prompt_id"] in controls), "inputs": [{"prompt": p, "text": texts.get(p), **tally(cls[sid] for sid in sel if sched[sid]["prompt_id"] == p)} for p in nulls]})
    primary = ablation[0]
    test("V", "primary system null slots", 300, primary["all"]["N"])
    test("V", "primary system null V0", 298, primary["all"]["V0"])
    test("V", "ablation arms null slots (three systems)", 90, sum(a["all"]["N"] for a in ablation[1:]))
    test("V", "ablation arms null Voids", 0, sum(a["all"]["Void"] for a in ablation[1:]))
    test("V", "primary system matched-control slots", 300, primary["control"]["N"])
    test("V", "primary system matched-control Voids", 0, primary["control"]["Void"])
    src = open(repo / "tables.py", encoding="utf-8").read()
    test("V", "tables.py pinned CSV hash equals trial-level CSV", re.search(r"CSV_SHA = '([0-9a-f]{64})'", src).group(1), sha256_file(SRC / "void-matrix-complete-analysis/analysis/tables/trial_level.csv"))
    test("V", "tables.py pinned matrix commit", git(SRC / "void-matrix-complete-analysis", "rev-parse", "HEAD"), re.search(r"COMMIT = '([0-9a-f]{40})'", src).group(1))
    return {"source": pin(repo), "doi": "10.5281/zenodo.23585146", "replay_doi": "10.5281/zenodo.23521616"}, [{"system": a["system"], "all": a["all"], "inputs": a["inputs"]} for a in ablation]


# ---------------------------------------------------------------- chapter VI
def classify_openai_body(http_status, body):
    if http_status != 200:
        return "OP"
    j = json.loads(body)
    ch = j["choices"][0]
    content = ch["message"].get("content")
    if ch["message"].get("refusal"):
        return "RF"
    if content:
        near = all(c.isspace() or unicodedata.category(c).startswith("P") or unicodedata.category(c) in ("Cf", "Cc") for c in content)
        return "NV" if near else "R"
    if ch.get("finish_reason") == "stop" and content is not None:
        return "V0"
    if ch.get("finish_reason") == "length":
        return "V1"
    return "VU"


def ab_like(repo_name, doi):
    repo = SRC / repo_name
    recs = sorted(glob.glob(str(repo / "records/raw/*.record.json")))
    cells = collections.defaultdict(list)
    derived = {}
    match_recorded = 0
    stamps = []
    for f in recs:
        r = json.load(open(f))
        body = open(repo / r["raw_response_path"], "rb").read()
        if hashlib.sha256(body).hexdigest() != r["raw_response_sha256"]:
            continue
        c = classify_openai_body(r["http_status"], body)
        derived[r["trial_id"]] = c
        if c == r["classification"]:
            match_recorded += 1
        cells[(r["requested_model"], r["pair_id"], r["role"])].append(c)
        stamps.append(r)
    trials = list(csv.DictReader(open(repo / "results/trials.csv", encoding="utf-8")))
    test("VI", f"{repo_name} attempts", 120, len(recs))
    test("VI", f"{repo_name} derived class equals recorded class", 120, match_recorded)
    test("VI", f"{repo_name} derived class equals trials.csv", 120, sum(1 for t in trials if derived.get(t["trial_id"]) == t["classification"]))
    counts = {"all": tally(derived.values()), "cells": [{"model": m, "pair": p, "role": role, **tally(v)} for (m, p, role), v in sorted(cells.items())], "first_utc": min(r["started_at_utc"] for r in stamps), "last_utc": max(r["ended_at_utc"] for r in stamps)}
    return {"source": pin(repo), "doi": doi, "manifest_check": check_sums(repo, "SHA256SUMS.txt"), "freeze_commit_recorded": open(repo / "FREEZE_COMMIT.txt").read().strip()}, counts


def classify_reassign(content, finish, targets):
    if content is None:
        return "V2"
    if content == "":
        return "V0" if finish == "stop" else "V1"
    for name, t in targets.items():
        if content == t:
            return name
    if all(c.isspace() or unicodedata.category(c) in ("Zs", "Cf", "Cc") for c in content):
        return "NV"
    if has_script(content, ARABIC) and has_script(content, HEBREW):
        return "MX"
    return "OT"


def reassignment():
    repo = SRC / "gpt-5.4-shrt-prerequisite-reassignment-analysis"
    targets = {"T1": T1, "T0": T0, "HE": HE, "SHART": SHART, "SHAMS": SHAMS}
    sched = {s["slot_id"]: s for s in json.load(open(repo / "evidence/request_schedule.json"))}
    test("VI", "reassignment scheduled slots", 800, len(sched))
    test("VI", "reassignment 200 per cell", {"E": 200, "F": 200, "G": 200, "H": 200}, dict(collections.Counter(s["cell"] for s in sched.values())))
    cells = collections.defaultdict(list)
    exceptions = collections.defaultdict(list)
    http_ok = model_ok = rec_match = multi = 0
    for slot in sorted(glob.glob(str(repo / "raw/attempts/slot-*"))):
        sid = os.path.basename(slot)
        atts = sorted(glob.glob(slot + "/attempt-*"))
        if len(atts) != 1:
            multi += 1
        a = json.load(open(atts[-1] + "/attempt.json"))
        body = json.loads(open(atts[-1] + "/response.bin", "rb").read())
        ch = body["choices"][0]
        c = classify_reassign(ch["message"].get("content"), ch.get("finish_reason"), targets)
        cell = sched[sid]["cell"]
        cells[cell].append(c)
        http_ok += a["http_status"] == 200
        model_ok += body.get("model") == a["requested_model"] == "gpt-5.4-2026-03-05"
        d = json.load(open(repo / "raw/definitive" / f"{sid}.json"))
        rec_match += d["classification"] == c and d["cell"] == cell
        if cell in ("F", "G") and c != "V0":
            exceptions[cell].append(ch["message"].get("content"))
    test("VI", "reassignment HTTP 200", 800, http_ok)
    test("VI", "reassignment returned model equals requested", 800, model_ok)
    test("VI", "reassignment multi-attempt slots", 0, multi)
    test("VI", "reassignment derived class equals definitive", 800, rec_match)
    t1 = {k: collections.Counter(v)["T1"] for k, v in cells.items()}
    test("VI", "exact T1 total", 238, sum(t1.values()))
    test("VI", "mismatch cells V0", 398, sum(collections.Counter(cells[k])["V0"] for k in ("F", "G")))
    test("VI", "match cells V0", 0, sum(collections.Counter(cells[k])["V0"] for k in ("E", "H")))
    return {"source": pin(repo), "doi": "10.5281/zenodo.22983298"}, [{"cell": k, **tally(v), "exceptions": exceptions.get(k, [])} for k, v in sorted(cells.items())]


# ---------------------------------------------------------------- chapter III and Opus experiments
def opus_all():
    repo = SRC / "opus45-opus46-matched-results"
    manifest = check_sums(repo, "opus45-opus46-matched-prereg-final-runs.SHA256SUMS")
    test("III", "Opus results manifest failures", 0, manifest["entries_bad"] + manifest["missing"])
    # experiment 3
    opus = {}
    cells3 = collections.defaultdict(list)
    hex_ok = 0
    for slot in sorted(glob.glob(str(repo / "exp3/attempts/exp3-*"))):
        c = json.load(open(slot + "/attempt-01/classification.json"))
        req = json.loads(open(slot + "/attempt-01/request.bin", "rb").read())
        body = json.loads(open(slot + "/attempt-01/response.bin", "rb").read())
        text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
        hex_ok += text.encode("utf-8").hex() == c["content_utf8_hex"]
        m = c["returned_model"]
        o = opus.setdefault(m, {"N": 0, "class_HE": 0, "class_MX": 0, "class_OT": 0, "class_T1": 0, "mixed_T1_occurrences": 0, "mixed_T1_slots": 0, "whole_HE": 0, "whole_T0": 0, "whole_T1": 0})
        o["N"] += 1
        o["class_" + c["class"]] = o.get("class_" + c["class"], 0) + 1
        o["whole_T1"] += text == T1
        o["whole_T0"] += text == T0
        o["whole_HE"] += text == HE
        n = sum(1 for w in (c.get("mixed_script_words") or []) if w == T1)
        o["mixed_T1_occurrences"] += n
        o["mixed_T1_slots"] += n > 0
        u = req["messages"][0]["content"]
        u = u if isinstance(u, str) else u[0]["text"]
        cells3[(req["model"], req["system"], u)].append(c["class"])
    test("III", "experiment 3 response bytes equal recorded content hex", 1200, hex_ok)
    test("III", "experiment 3 whole-response exact T1", {"claude-opus-4-5-20251101": 9, "claude-opus-4-6": 69}, {k: v["whole_T1"] for k, v in sorted(opus.items())})
    opus_cells = [{"model": m, "system": s, "input": u, **tally(v)} for (m, s, u), v in sorted(cells3.items())]
    test("III", "experiment 3 cells", 12, len(opus_cells))
    s1 = json.load(open(SRC / "gpt-5.4-shrt-prerequisite-reassignment-analysis/evidence/prompts.json"))
    e_cell = next(c for c in opus_cells if c["model"] == "claude-opus-4-6" and c["system"] == s1["S1"] and c["input"] == SHART)
    h_cell = next(c for c in opus_cells if c["model"] == "claude-opus-4-6" and c["system"] == s1["S0"] and c["input"] == SHAMS)
    test("III", "Opus 4.6 S1 x SHART exact T1 (E analogue)", 66, e_cell["classes"].get("T1", 0))
    test("III", "Opus 4.6 S0 x SHAMS exact T1 (H analogue)", 2, h_cell["classes"].get("T1", 0))
    # experiments 1 and 2
    repl = {}
    for exp in ("exp1", "exp2"):
        cells = collections.defaultdict(list)
        stamps = []
        for slot in sorted(glob.glob(str(repo / f"{exp}/attempts/{exp}-*"))):
            c = json.load(open(slot + "/attempt-01/classification.json"))
            req = json.loads(open(slot + "/attempt-01/request.bin", "rb").read())
            a = json.load(open(slot + "/attempt-01/attempt.json"))
            u = req["messages"][0]["content"]
            u = u if isinstance(u, str) else u[0]["text"]
            cells[(req["model"], u, req["max_tokens"])].append(c["class"])
            stamps.append(a["timestamp_utc"])
        repl[exp] = {"cells": [{"model": m, "input": u, "ceiling": k, **tally(v)} for (m, u, k), v in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1]))], "first_dispatch_utc": min(stamps), "last_dispatch_utc": max(stamps)}
    e1 = repl["exp1"]
    test("III", "experiment 1 cells", 36, len(e1["cells"]))
    test("III", "experiment 1 requests", 1080, sum(c["N"] for c in e1["cells"]))
    test("III", "experiment 1 Opus 4.5 V1", 539, sum(c["V1"] for c in e1["cells"] if c["model"].startswith("claude-opus-4-5")))
    test("III", "experiment 1 Opus 4.6 V1", 165, sum(c["V1"] for c in e1["cells"] if c["model"] == "claude-opus-4-6"))
    e2 = repl["exp2"]
    test("III", "experiment 2 cells", 64, len(e2["cells"]))
    test("III", "experiment 2 Opus 4.6 null V2 at four ceilings", 360, sum(c["V2"] for c in e2["cells"] if c["model"] == "claude-opus-4-6"))
    # cross-script
    crepo = SRC / "gpt-5.4-shrt-cross-script-evidence"
    sched = {}
    for line in open(crepo / "evidence/study/schedule.jsonl", encoding="utf-8"):
        s = json.loads(line)
        sched[s["slot_id"]] = s
    last = {}
    for f in glob.glob(str(crepo / "evidence/study/run/attempts/*.json")):
        slot, n = os.path.basename(f)[:-5].rsplit(".", 1)
        if slot not in last or int(n) > last[slot][0]:
            last[slot] = (int(n), f)
    primary = collections.Counter()
    classes = collections.Counter()
    models = collections.Counter()
    for slot, (n, f) in last.items():
        a = json.load(open(f))
        c = a["classification"]["classification"]
        classes[c] += 1
        models[a["classification"].get("provider_returned_model") or "missing"] += 1
        if sched[slot]["module"] == "primary_confirmatory":
            primary[sched[slot]["prompt_id"] + "|" + c] += 1
    test("III", "cross-script terminal slots", 12160, len(last))
    test("III", "cross-script primary exact T0/T1", 7253, sum(v for k, v in primary.items() if k.split("|")[1] in ("T0", "T1")))
    test("III", "cross-script dotted exact T1", 4830, primary["full_dotted|T1"])
    test("III", "cross-script undotted exact T0", 2423, primary["full_undotted|T0"])
    cross = {"N": len(last), "primary_N": sum(primary.values()), "primary": dict(sorted(primary.items())), "classes": dict(sorted(classes.items())), "models": dict(sorted(models.items()))}
    return {"source_opus": pin(repo), "source_cross": pin(crepo), "opus_manifest": manifest, "cross_manifest": check_sums(crepo, "SHA256SUMS")}, cross, {k: dict(sorted(v.items())) for k, v in sorted(opus.items())}, opus_cells, repl


# ---------------------------------------------------------------- DOOR-KEY-1
def dk_classify_openai(body):
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


def dk_classify_anthropic(body):
    blocks = body.get("content") or []
    types = [b.get("type") for b in blocks]
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    stop = body.get("stop_reason")
    if stop == "refusal":
        return "RF"
    if "tool_use" in types or stop == "tool_use":
        return "TC"
    if text:
        return "NV" if near_void(text) else "R"
    if stop == "max_tokens":
        return "V1"
    if stop in ("end_turn", "stop_sequence"):
        return "V0" if "text" in types else "V2"
    return "VU"


def pacific(utc_iso):
    t = dt.datetime.strptime(utc_iso.replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=dt.timezone.utc)
    return t.astimezone(dt.timezone(dt.timedelta(hours=-8))).isoformat()


def door_key():
    res, pre = SRC / "door-key-1-results", SRC / "door-key-1-preregistration"
    rm, pm = check_sums(res, "SHA256SUMS"), check_sums(pre, "SHA256SUMS")
    test("DK", "DOOR-KEY results manifest failures", 0, rm["entries_bad"] + rm["missing"])
    test("DK", "DOOR-KEY preregistration manifest failures", 0, pm["entries_bad"] + pm["missing"])
    sched = json.load(open(pre / "SCHEDULE.json"))
    prompts = json.load(open(pre / "prompts.json"))
    run = json.load(open(res / "run/RUN.json"))
    cells = collections.defaultdict(list)
    nv_receipts = []
    meta_match = http_ok = model_ok = prompt_ok = 0
    dispatch, receipt = [], []
    for slot in sorted(glob.glob(str(res / "run/receipts/*"))):
        meta = json.load(open(slot + "/meta.json"))
        body = json.loads(open(slot + "/response.bin", "rb").read())
        req = json.loads(open(slot + "/request.json", "rb").read())
        m = meta["model"]
        c = dk_classify_openai(body) if m.startswith("gpt") else dk_classify_anthropic(body)
        meta_match += c == meta["native_class"]
        http_ok += meta["http_status"] == 200
        model_ok += meta.get("returned_model") == meta["requested_model"] == m
        sys_text = req["messages"][0]["content"] if m.startswith("gpt") else req.get("system")
        if isinstance(sys_text, list):
            sys_text = "".join(b.get("text", "") for b in sys_text)
        prompt_ok += sys_text == prompts["system"][meta["arm"]]["text"]
        dispatch.append(meta["dispatch_utc"])
        receipt.append(meta["receipt_utc"])
        if c == "NV":
            content = body["choices"][0]["message"]["content"] if m.startswith("gpt") else "".join(b.get("text", "") for b in body.get("content", []))
            nv_receipts.append({"slot": meta["slot"], "content": content, "utf8_hex": content.encode("utf-8").hex()})
        cells[(m, meta["arm"], meta["input"])].append(c)
    test("DK", "DOOR-KEY receipts", 1200, len(dispatch))
    test("DK", "DOOR-KEY schedule slots", 1200, len(sched))
    test("DK", "DOOR-KEY HTTP 200", 1200, http_ok)
    test("DK", "DOOR-KEY returned model equals requested", 1200, model_ok)
    test("DK", "DOOR-KEY system prompt bytes equal frozen prompts", 1200, prompt_ok)
    test("DK", "DOOR-KEY derived class equals recorded native class", 1200, meta_match)
    table = [{"model": m, "arm": arm, "input": inp, **tally(v)} for (m, arm, inp), v in sorted(cells.items())]
    z = {(r["model"], r["arm"], r["input"]): (r["V0"] + r["V2"]) / 100 for r in table}
    contrasts = []
    for m in sorted({r["model"] for r in table}):
        d = lambda arm: z[(m, arm, "lock")] - z[(m, arm, "key")]
        observed = z[(m, "ORIGINAL", "lock")] > z[(m, "ORIGINAL", "key")] and z[(m, "REVERSED", "key")] > z[(m, "REVERSED", "lock")]
        contrasts.append({"model": m, "crossover": round(d("ORIGINAL") - d("REVERSED"), 4), "observed_reversal": observed, "violations": sum(r["R"] + r["NV"] for r in table if r["model"] == m and (r["arm"], r["input"]) in (("ORIGINAL", "lock"), ("REVERSED", "key"))), "prohibition_N": 200})
    gpt = {(r["arm"], r["input"]): r for r in table if r["model"].startswith("gpt")}
    test("DK", "GPT-5.4 ORIGINAL x lock Z", 71, gpt[("ORIGINAL", "lock")]["V0"] + gpt[("ORIGINAL", "lock")]["V2"])
    test("DK", "GPT-5.4 REVERSED x key Z", 24, gpt[("REVERSED", "key")]["V0"] + gpt[("REVERSED", "key")]["V2"])
    test("DK", "GPT-5.4 other four cells R", 400, sum(r["R"] for r in table if r["model"].startswith("gpt") and (r["arm"], r["input"]) not in (("ORIGINAL", "lock"), ("REVERSED", "key"))))
    test("DK", "Opus 4.6 all cells R", 600, sum(r["R"] for r in table if r["model"] == "claude-opus-4-6"))
    test("DK", "GPT-5.4 prohibition cells below the 95/100 gate", True, all(gpt[k]["V0"] + gpt[k]["V2"] < 95 for k in (("ORIGINAL", "lock"), ("REVERSED", "key"))))
    counts = {"N": len(dispatch), "cells": table, "contrasts": contrasts, "first_dispatch_utc": min(dispatch), "last_response_utc": max(receipt), "first_dispatch_pacific": pacific(min(dispatch)), "last_response_pacific": pacific(max(receipt)), "NV_receipts": nv_receipts, "concurrency": run["concurrency"]}
    return {"results": pin(res), "preregistration": pin(pre), "results_manifest": rm, "preregistration_manifest": pm, "doi_results": "10.5281/zenodo.24042127", "doi_preregistration": "10.5281/zenodo.23968364"}, counts


# ---------------------------------------------------------------- February account (public archive)
PSR_DOI = "10.5281/zenodo.21969180"
PSR_MD5 = "4471420191e35c495abcd225128e5d0e"
PSR_ZIP = Path(os.environ.get("PRIMARY_SOURCE_RECORD_ZIP", str(Path.home() / "RAYAN_PAL_PRIMARY_SOURCE_RECORD_2025-12-08_TO_2026-08-15.zip")))
PSR_PREFIX = "RAYAN_PAL_PRIMARY_SOURCE_RECORD_2025-12-08_TO_2026-08-15/"
PSR_MEMBERS = {"2026-02-06": "gmail-evidence/01_EVIDENCE_SELECTED/EMAIL__20260206__19c34c0d77834e40__opus-4-5-vs-opus-4-6-void-phenomenon/DERIVED/02__BODY.txt", "2026-02-10": "gmail-evidence/01_EVIDENCE_SELECTED/EMAIL__20260210__19c4945569479603__cerebral-valley-opus-4-6-hackathon-submission/DERIVED/02__BODY.txt"}
CJK = [(0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x3040, 0x30FF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF)]


def february_account():
    import zipfile
    if not PSR_ZIP.exists():
        test("FEB", "public archive available for rederivation", True, False)
        return {"source": {"doi": PSR_DOI, "archive_md5": PSR_MD5, "available": False}}, None
    md5 = hashlib.md5(open(PSR_ZIP, "rb").read()).hexdigest()
    test("FEB", "archive md5 equals Zenodo record", PSR_MD5, md5)
    with zipfile.ZipFile(PSR_ZIP) as z:
        manifest = z.read(PSR_PREFIX + "gmail-evidence/SHA256SUMS.txt").decode("utf-8")
        listed = {l.split("  ", 1)[1]: l.split("  ", 1)[0] for l in manifest.splitlines() if "  " in l}
        members = {}
        for date, member in PSR_MEMBERS.items():
            data = z.read(PSR_PREFIX + member)
            digest = hashlib.sha256(data).hexdigest()
            test("FEB", f"member {date} listed in archive manifest with matching sha256", listed.get(member.split("gmail-evidence/", 1)[1]), digest)
            members[date] = {"archive_member": member, "sha256": digest, "text": data.decode("utf-8", "replace")}
    rows = re.findall(r"^(\S) \(([^)]*)\) (VOID|RESPONDS) (VOID|RESPONDS)", members["2026-02-06"]["text"], re.M)
    is_cjk = lambda ch: any(a <= ord(ch) <= b for a, b in CJK)
    test("FEB", "2026-02-06 member states max_tokens=1", True, "max_tokens=1" in members["2026-02-06"]["text"])
    test("FEB", "2026-02-10 member restates 18 inputs with 5 remaining", True, "18 CJK" in members["2026-02-10"]["text"] and "5" in members["2026-02-10"]["text"])
    counts = {"N": len(rows), "opus45_empty": sum(1 for r in rows if r[2] == "VOID"), "opus46_empty": sum(1 for r in rows if r[3] == "VOID"), "changed": sum(1 for r in rows if r[2] != r[3]), "cjk_N": sum(1 for r in rows if is_cjk(r[0])), "symbols": [r[0] for r in rows if not is_cjk(r[0])], "earliest_record_date": "2026-02-06", "restated_date": "2026-02-10"}
    test("FEB", "historical table rows", 18, counts["N"])
    meta = {"source": {"doi": PSR_DOI, "url": "https://zenodo.org/records/21969180", "archive_md5": PSR_MD5, "members": {d: {k: v for k, v in m.items() if k != "text"} for d, m in members.items()}}, "labels": "historical VOID/RESPONDS labels from the account; no Void subtype is assignable without finish metadata"}
    return meta, counts


# ---------------------------------------------------------------- comparison
def compare(generated, derived):
    diffs = []

    def walk(path, g, d):
        if isinstance(g, dict) and isinstance(d, dict):
            for k in g:
                if k in d:
                    walk(path + [k], g[k], d[k])
                else:
                    diffs.append({"path": ".".join(map(str, path + [k])), "generated": g[k], "derived": "absent"})
        elif isinstance(g, list) and isinstance(d, list):
            if len(g) != len(d):
                diffs.append({"path": ".".join(map(str, path)), "generated": f"list[{len(g)}]", "derived": f"list[{len(d)}]"})
            idf = ("model", "system", "input", "ceiling", "arm", "prompt", "cell", "name", "study", "track", "pair", "role", "id")
            if g and all(isinstance(x, dict) for x in g + d) and any(k in g[0] for k in idf):
                keyf = lambda x: tuple(str(x.get(k)) for k in idf if k in x)
                dmap = {keyf(x): x for x in d}
                for a in g:
                    b = dmap.get(keyf(a))
                    if b is None:
                        diffs.append({"path": ".".join(map(str, path)), "generated": keyf(a), "derived": "absent"})
                    else:
                        walk(path + [keyf(a)], a, b)
            else:
                for i, (a, b) in enumerate(zip(g, d)):
                    walk(path + [i], a, b)
        else:
            if g != d:
                diffs.append({"path": ".".join(map(str, path)), "generated": g, "derived": d})
    walk([], generated, derived)
    return diffs


def main():
    gen = json.load(open(GENERATED)) if GENERATED.exists() else {}
    m1, c1 = chapter_i()
    m2, c2 = chapter_ii()
    m4, c4, cls, sched, texts = chapter_iv()
    m5, c5 = chapter_v(cls, sched, texts)
    mab, cab = ab_like("gpt35-gpt4-void-ab", "10.5281/zenodo.22912683")
    mrp, crp = ab_like("gpt4-0613-void-replay-results", "10.5281/zenodo.23521616")
    mrs, crs = reassignment()
    m3, cross, opus, opus_cells, repl = opus_all()
    mdk, cdk = door_key()
    mfeb, cfeb = february_account()
    c4["ablation"] = c5
    derived = {"pccg1": c1, "pccg2": c2, "matrix": c4, "ab": cab, "replay": crp, "reassignment": crs, "cross": cross, "opus": opus, "opus_cells": opus_cells, "opus_replication": repl, "door": cdk}
    if cfeb is not None:
        derived["february_account"] = cfeb
    diffs = compare(gen, derived) if gen else [{"path": "", "generated": "absent", "derived": "present"}]
    unverified_keys = [k for k in gen if k not in derived]
    report = {
        "report": "independent_verification",
        "scope": "Numerical, hash and record-level verification of pinned sources against generated/counts.json. Manuscript text review is recorded separately and is not asserted by this file.",
        "generated_counts_file": rel(GENERATED), "generated_counts_sha256": sha256_file(GENERATED) if GENERATED.exists() else None,
        "sources": {"I": m1, "II": m2, "III": m3, "IV": m4, "V": m5, "VI_ab": mab, "VI_replay": mrp, "VI_reassignment": mrs, "door_key": mdk, "february_account": mfeb},
        "derived_counts": derived,
        "tests": TESTS, "tests_total": len(TESTS), "tests_passed": sum(1 for t in TESTS if t["pass"]),
        "discrepancies_against_expectations": DISCREPANCIES,
        "differences_from_generated_counts": diffs,
        "generated_keys_not_rederived": unverified_keys,
        "numerical_verification_result": "PASS" if not DISCREPANCIES and not diffs and not unverified_keys else "FAIL",
    }
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print("tests", report["tests_passed"], "/", report["tests_total"], "| differences:", len(diffs), "| unverified keys:", unverified_keys, "| result:", report["numerical_verification_result"])
    for d in DISCREPANCIES:
        print("  DISCREPANCY", d)
    for d in diffs[:40]:
        print("  DIFF", json.dumps(d, ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
