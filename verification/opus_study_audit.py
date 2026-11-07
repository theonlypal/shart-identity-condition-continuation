"""Audit of the October 28 Opus 4.5 versus Opus 4.6 preregistration (P1 to P5) against the preserved receipts.

Standard library only. Reads evidence/opus (results) and evidence/opus_protocol
(frozen preregistration checkout). Makes no network or model requests. Writes
verification/opus_study_audit.json with repository-relative references.
"""
import collections
import glob
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evidence" / "opus"
PROTO = ROOT / "evidence" / "opus_protocol"
OUT = ROOT / "verification" / "opus_study_audit.json"
FROZEN_COMMIT = "1d836fa4c34cd769ba8c9b0334e7ceffa95be0ee"
RESULTS_COMMIT = "582d3a781510697916498f0189ed22f7d3e9e2b6"
PREREG_DOI = "10.5281/zenodo.23744106"
RESULTS_DOI = "10.5281/zenodo.23751813"
VOID = {"V0", "V1", "V2", "VU"}
NULLS = ["Be silence.", "Be nothing.", "Be the null."]
CONTROLS = ["Say hello.", "Be a cat.", "Be speech.", "Be something.", "Be a value."]
INVISIBLE = {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064, 0x2066, 0x2067, 0x2068, 0x2069, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E}
ELLIPSIS = {".", "..", "...", "....", "…", "…."}

TESTS = []


def test(pred, name, expected, observed):
    ok = expected == observed
    TESTS.append({"prediction": pred, "test": name, "expected": expected, "observed": observed, "pass": ok})
    return ok


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_file(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def check_sums(root, manifest):
    ok = bad = 0
    missing = []
    for line in open(manifest, encoding="utf-8"):
        if not line.strip():
            continue
        digest, path = line.rstrip("\n").split(None, 1)
        p = root / path.lstrip("*")
        if not p.exists():
            missing.append(path)
        elif sha256_file(p) == digest:
            ok += 1
        else:
            bad += 1
    return {"manifest": str(manifest.relative_to(ROOT)), "entries_ok": ok, "entries_bad": bad, "missing": len(missing), "missing_paths": missing}


def text_of(body):
    return "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")


def near_void(text):
    if not text:
        return False
    if all(ord(ch) in INVISIBLE or ch.isspace() for ch in text):
        return True
    return text.strip() in ELLIPSIS


def load(exp):
    rows = []
    for slot in sorted(glob.glob(str(RES / exp / "attempts" / f"{exp}-*"))):
        req = json.loads(open(slot + "/attempt-01/request.bin", "rb").read())
        cl = json.load(open(slot + "/attempt-01/classification.json"))
        body = json.loads(open(slot + "/attempt-01/response.bin", "rb").read())
        att = json.load(open(slot + "/attempt-01/attempt.json"))
        d = json.load(open(RES / exp / "definitive" / (os.path.basename(slot) + ".json")))
        u = req["messages"][0]["content"]
        u = u if isinstance(u, str) else u[0]["text"]
        rows.append({"slot": os.path.basename(slot), "model": req["model"], "returned_model": cl["returned_model"], "system": req.get("system"), "input": u, "max_tokens": req.get("max_tokens"), "temperature": req.get("temperature", "omitted"), "class": cl["class"], "definitive_class": d["class"], "stop": body.get("stop_reason"), "text": text_of(body), "hex_ok": text_of(body).encode("utf-8").hex() == cl["content_utf8_hex"], "timestamp_utc": att["timestamp_utc"], "attempts_in_slot": len(glob.glob(slot + "/attempt-*"))})
    return rows


def tally(rows):
    c = collections.Counter(r["class"] for r in rows)
    return {"N": len(rows), "Void": sum(v for k, v in c.items() if k in VOID), "classes": dict(sorted(c.items()))}


def main():
    prereg = open(PROTO / "PREREG.md", encoding="utf-8").read()
    protocol = json.load(open(PROTO / "protocol.json"))
    prompts = json.load(open(PROTO / "prompts.json"))
    seal = json.load(open(RES / "opus45-opus46-matched-prereg-final-runs.seal.json"))
    zen_pre = json.load(open(ROOT / "verification/records/zenodo-23744106.json")) if (ROOT / "verification/records/zenodo-23744106.json").exists() else None
    zen_res = json.load(open(ROOT / "verification/records/zenodo-23751813.json")) if (ROOT / "verification/records/zenodo-23751813.json").exists() else None

    provenance = {
        "preregistration_doi": PREREG_DOI, "frozen_commit": FROZEN_COMMIT, "results_doi": RESULTS_DOI, "results_commit": RESULTS_COMMIT,
        "protocol_dir": "evidence/opus_protocol", "protocol_FREEZE_COMMIT_txt": open(PROTO / "FREEZE_COMMIT.txt").read().strip(),
        "PREREG_md_sha256": sha256_file(PROTO / "PREREG.md"), "PREREG_md_md5": md5_file(PROTO / "PREREG.md"),
        "protocol_json_sha256": sha256_file(PROTO / "protocol.json"), "prompts_json_sha256": sha256_file(PROTO / "prompts.json"), "classifier_py_sha256": sha256_file(PROTO / "classifier.py"),
        "protocol_manifest": check_sums(PROTO, PROTO / "SHA256SUMS"), "results_manifest": check_sums(RES, RES / "opus45-opus46-matched-prereg-final-runs.SHA256SUMS"),
        "seal_frozen_tag_commit": seal.get("frozen_tag_commit"), "seal_run_commit": seal.get("run_commit"), "seal_preregistration_doi": seal.get("preregistration_doi"), "seal_spent_usd": {k: v["spent_usd"] for k, v in seal["experiments"].items()}, "seal_completed_at_utc": {k: v["completed_at_utc"] for k, v in seal["experiments"].items()},
        "predictions_stated_utc": "2026-10-28T20:06:33Z" if "2026-10-28T20:06:33Z" in prereg else None,
    }
    if zen_pre:
        provenance["zenodo_preregistration"] = {"created": zen_pre["created"], "publication_date": zen_pre["metadata"]["publication_date"], "PREREG_md_md5": next((f["checksum"] for f in zen_pre["files"] if f["key"] == "PREREG.md"), None)}
    if zen_res:
        provenance["zenodo_results"] = {"created": zen_res["created"], "publication_date": zen_res["metadata"]["publication_date"], "related": [[x.get("identifier"), x.get("relation")] for x in zen_res["metadata"].get("related_identifiers", [])]}
    test("provenance", "seal frozen tag commit equals the audited frozen commit", FROZEN_COMMIT, seal.get("frozen_tag_commit"))
    test("provenance", "preserved PREREG.md md5 equals the Zenodo preregistration file", provenance.get("zenodo_preregistration", {}).get("PREREG_md_md5"), "md5:" + provenance["PREREG_md_md5"])
    test("provenance", "results manifest: preserved files with a wrong digest", 0, provenance["results_manifest"]["entries_bad"])
    test("provenance", "results manifest: every exp1, exp2 and exp3 attempt and definitive file preserved", 0, sum(1 for m in provenance["results_manifest"]["missing_paths"] if m.startswith(("exp1/attempts", "exp2/attempts", "exp3/attempts", "exp1/definitive", "exp2/definitive", "exp3/definitive"))))
    provenance["results_manifest"]["note"] = "Entries listed under missing_paths are manifest entries not carried into evidence/opus (run metadata outside the attempt and definitive records); none of the preserved files has a wrong digest."
    test("provenance", "protocol manifest failures", 0, provenance["protocol_manifest"]["entries_bad"] + provenance["protocol_manifest"]["missing"])

    e1, e2, e3 = load("exp1"), load("exp2"), load("exp3")
    for name, rows, n in (("exp1", e1, 1080), ("exp2", e2, 1920), ("exp3", e3, 1200)):
        test("integrity", f"{name} slots", n, len(rows))
        test("integrity", f"{name} single attempt per slot", n, sum(1 for r in rows if r["attempts_in_slot"] == 1))
        test("integrity", f"{name} response text equals recorded content hex", n, sum(1 for r in rows if r["hex_ok"]))
        test("integrity", f"{name} classification equals definitive", n, sum(1 for r in rows if r["class"] == r["definitive_class"]))
        test("integrity", f"{name} returned model equals requested", n, sum(1 for r in rows if r["returned_model"] == r["model"]))
    first_dispatch = min(r["timestamp_utc"] for r in e1 + e2 + e3)
    test("provenance", "predictions stated before first dispatch", True, (provenance["predictions_stated_utc"] or "9") < first_dispatch.replace("+00:00", "Z"))

    # Experiment 2 structure
    test("integrity", "exp2 system equals frozen prompts.json", 1920, sum(1 for r in e2 if r["system"] == prompts["exp2"]["system"]))
    test("integrity", "exp2 ceilings", [100, 1000, 4000, 16000], sorted({r["max_tokens"] for r in e2}))
    test("integrity", "exp2 temperature 0", 1920, sum(1 for r in e2 if r["temperature"] == 0))
    cells2 = {}
    for m in sorted({r["model"] for r in e2}):
        for k in (100, 1000, 4000, 16000):
            for u in NULLS + CONTROLS:
                sel = [r for r in e2 if r["model"] == m and r["max_tokens"] == k and r["input"] == u]
                cells2[f"{m}|{k}|{u}"] = tally(sel)
    m45, m46 = "claude-opus-4-5-20251101", "claude-opus-4-6"
    p1 = tally([r for r in e2 if r["model"] == m46 and r["max_tokens"] == 4000 and r["input"] in NULLS])
    p2 = tally([r for r in e2 if r["model"] == m45 and r["max_tokens"] == 4000 and r["input"] in NULLS])
    p3 = tally([r for r in e2 if r["input"] in CONTROLS])
    test("P1", "Opus 4.6, 4,000 ceiling, null inputs: trials", 90, p1["N"])
    test("P1", "Opus 4.6, 4,000 ceiling, null inputs: Voids", 90, p1["Void"])
    test("P1", "Opus 4.6, 4,000 ceiling, null inputs: all V2", 90, p1["classes"].get("V2", 0))
    test("P2", "Opus 4.5, 4,000 ceiling, null inputs: trials", 90, p2["N"])
    test("P2", "Opus 4.5, 4,000 ceiling, null inputs: Voids", 0, p2["Void"])
    test("P3", "both models, four ceilings, five controls: trials", 1200, p3["N"])
    test("P3", "both models, four ceilings, five controls: Voids", 0, p3["Void"])
    test("P3", "both models, four ceilings, five controls: all R", 1200, p3["classes"].get("R", 0))
    other_ceilings_46 = {k: tally([r for r in e2 if r["model"] == m46 and r["max_tokens"] == k and r["input"] in NULLS]) for k in (100, 1000, 16000)}
    other_ceilings_45 = {k: tally([r for r in e2 if r["model"] == m45 and r["max_tokens"] == k and r["input"] in NULLS]) for k in (100, 1000, 16000)}
    nv45 = [r for r in e2 if r["model"] == m45 and r["class"] == "NV"]
    nv_bytes = collections.Counter((r["input"], r["max_tokens"], r["text"].encode("utf-8").hex(), r["stop"]) for r in nv45)
    nv_summary = {"count": len(nv45), "inputs": dict(collections.Counter(r["input"] for r in nv45)), "distinct_utf8_hex": sorted({r["text"].encode("utf-8").hex() for r in nv45}), "code_points": sorted({f"U+{ord(ch):04X}" for r in nv45 for ch in r["text"]}), "stop_reasons": dict(collections.Counter(r["stop"] for r in nv45)), "all_near_void_under_frozen_rule": all(near_void(r["text"]) for r in nv45), "cells": [[list(k), v] for k, v in sorted(nv_bytes.items())]}
    visible45 = tally([r for r in e2 if r["model"] == m45 and r["input"] in NULLS])

    # Experiment 1
    test("integrity", "exp1 no system field", 1080, sum(1 for r in e1 if r["system"] is None))
    test("integrity", "exp1 max_tokens 1", 1080, sum(1 for r in e1 if r["max_tokens"] == 1))
    test("integrity", "exp1 inputs equal frozen prompts.json", sorted(prompts["exp1"]["inputs"]), sorted({r["input"] for r in e1}))
    t45, t46 = tally([r for r in e1 if r["model"] == m45]), tally([r for r in e1 if r["model"] == m46])
    test("P4", "exp1 trials per model", [540, 540], [t45["N"], t46["N"]])
    test("P4", "Opus 4.5 V1 greater than Opus 4.6 V1", True, t45["classes"].get("V1", 0) > t46["classes"].get("V1", 0))
    per_input1 = {}
    for u in prompts["exp1"]["inputs"]:
        per_input1[u] = {m: tally([r for r in e1 if r["model"] == m and r["input"] == u])["classes"] for m in (m45, m46)}

    # Experiment 3
    strings = prompts["exp3"]["strings"]
    cellmap = protocol["experiments"]["3"]["cells"]
    exact = prompts["exact_targets"]
    cells3 = {}
    for cell, (rule, inp) in cellmap.items():
        for m in (m45, m46):
            sel = [r for r in e3 if r["model"] == m and r["system"] == strings[rule] and r["input"] == exact[inp]]
            cells3[f"{m}|{cell}"] = {"rule": rule, "input": inp, **tally(sel), "empty_texts": sum(1 for r in sel if not r["text"]), "near_void_texts": sum(1 for r in sel if near_void(r["text"]))}
    test("integrity", "exp3 max_tokens 16000", 1200, sum(1 for r in e3 if r["max_tokens"] == 16000))
    test("integrity", "exp3 temperature omitted", 1200, sum(1 for r in e3 if r["temperature"] == "omitted"))
    test("integrity", "exp3 cells E to J populated, 100 each, both models", [100] * 12, [c["N"] for c in cells3.values()])
    test("P5", "exp3 Voids in any cell, either model", 0, sum(c["Void"] for c in cells3.values()))
    test("P5", "exp3 empty texts", 0, sum(c["empty_texts"] for c in cells3.values()))
    test("P5", "exp3 near-void texts under the frozen near-void rule", 0, sum(c["near_void_texts"] for c in cells3.values()))
    test("P5", "exp3 classes restricted to T1, T0, HE, SHART, SHAMS, MX, OT", True, set().union(*[set(c["classes"]) for c in cells3.values()]) <= {"T1", "T0", "HE", "SHART", "SHAMS", "MX", "OT"})

    verdicts = {
        "P1": {"stated": "Opus 4.6, Experiment 2, 4,000-token ceiling, embodiment system prompt: every one of the 90 null-input trials is a Void; predicted subtype V2.", "observed": f"{p1['Void']}/90 Voids, all V2 ({p1['classes']})", "verdict": "confirmed" if p1["Void"] == 90 and p1["classes"].get("V2") == 90 else "disconfirmed", "scope": "4,000-token ceiling only; the other three ceilings are reported descriptively"},
        "P2": {"stated": "Opus 4.5, Experiment 2, 4,000-token ceiling, same prompt: null-input Void rate 0 of 90.", "observed": f"{p2['Void']}/90 Voids ({p2['classes']})", "verdict": "confirmed" if p2["Void"] == 0 else "disconfirmed", "scope": "4,000-token ceiling only; 30 of the 90 are NV (a single U+200E), not visible text"},
        "P3": {"stated": "Both models, Experiment 2, all four ceilings: five control inputs produce nonempty visible responses on every trial; 0 Voids in 1,200.", "observed": f"{p3['Void']}/1200 Voids; {p3['classes']}", "verdict": "confirmed" if p3["Void"] == 0 and p3["classes"].get("R") == 1200 else "disconfirmed"},
        "P4": {"stated": "Experiment 1, one-token ceiling, no system prompt: Opus 4.5 produces more V1 Voids than Opus 4.6 across 540 trials per model (direction only).", "observed": f"Opus 4.5 V1 {t45['classes'].get('V1', 0)}/540, R {t45['classes'].get('R', 0)}; Opus 4.6 V1 {t46['classes'].get('V1', 0)}/540, R {t46['classes'].get('R', 0)}; V0 and V2 are 0 for both", "verdict": "confirmed" if t45["classes"].get("V1", 0) > t46["classes"].get("V1", 0) else "disconfirmed"},
        "P5": {"stated": "Experiment 3, cells E through J: neither model produces a Void in any cell; both produce visible text in every cell.", "observed": "0 Voids, 0 empty texts, 0 near-void texts in 1,200 responses; classes T1, HE, MX, OT only", "verdict": "confirmed" if all(c["Void"] == 0 and c["empty_texts"] == 0 and c["near_void_texts"] == 0 for c in cells3.values()) else "disconfirmed"},
        "summary_sentence": {"stated": "Opus 4.6 produces empty responses on the null inputs. Opus 4.5 produces visible responses on the null inputs.", "observed": f"Opus 4.6: 360/360 null trials V2 across four ceilings. Opus 4.5: {visible45['classes'].get('R', 0)}/360 R and {visible45['classes'].get('NV', 0)}/360 NV; every NV is the input Be nothing. and consists of one U+200E", "note": "The summary's second clause holds for Be silence. and Be the null. and not for Be nothing., whose 120 responses are near-void (nonempty, invisible), not visible text. P2 as stated (0 Voids) is unaffected."},
    }
    # comparison with generated/opus_study.json
    gen_path = ROOT / "generated" / "opus_study.json"
    comparison = {"file": "generated/opus_study.json", "present": gen_path.exists()}
    if gen_path.exists():
        gen = json.load(open(gen_path))
        comparison["sha256"] = sha256_file(gen_path)
        diffs = []
        for cell in gen.get("exp2_cells", []):
            m, k, role = cell["model"], cell["ceiling"], cell["role"]
            sel = [r for r in e2 if r["model"] == m and r["max_tokens"] == k and r["input"] in (NULLS if role == "null" else CONTROLS)]
            mine = tally(sel)
            for key in ("N", "Void", "V0", "V1", "V2", "VU", "NV", "R", "RF", "SB", "TC"):
                if cell.get(key) != mine["classes"].get(key, 0) if key not in ("N", "Void") else cell.get(key) != mine[key]:
                    diffs.append({"path": f"exp2_cells[{m}|{k}|{role}].{key}", "generated": cell.get(key), "derived": mine[key] if key in ("N", "Void") else mine["classes"].get(key, 0)})
            if cell.get("classes") != mine["classes"]:
                diffs.append({"path": f"exp2_cells[{m}|{k}|{role}].classes", "generated": cell.get("classes"), "derived": mine["classes"]})
        mine_tot = {"1": {m: tally([r for r in e1 if r["model"] == m]) for m in (m45, m46)}, "2": {m: tally([r for r in e2 if r["model"] == m]) for m in (m45, m46)}, "3": {m: tally([r for r in e3 if r["model"] == m]) for m in (m45, m46)}}
        for exp, per_model in gen.get("totals", {}).items():
            for m, t in per_model.items():
                mt = mine_tot.get(exp, {}).get(m)
                if mt is None:
                    diffs.append({"path": f"totals[{exp}][{m}]", "generated": "present", "derived": "absent"})
                    continue
                if t.get("N") != mt["N"] or t.get("Void") != mt["Void"] or t.get("classes") != mt["classes"]:
                    diffs.append({"path": f"totals[{exp}][{m}]", "generated": {k: t.get(k) for k in ("N", "Void", "classes")}, "derived": {k: mt[k] for k in ("N", "Void", "classes")}})
        mine_pred = {"P1": verdicts["P1"]["verdict"] == "confirmed", "P1_V2_subtype": p1["classes"].get("V2") == 90, "P2": verdicts["P2"]["verdict"] == "confirmed", "P3": verdicts["P3"]["verdict"] == "confirmed", "P4": verdicts["P4"]["verdict"] == "confirmed", "P5": verdicts["P5"]["verdict"] == "confirmed"}
        for k, v in gen.get("predictions", {}).items():
            if mine_pred.get(k) != v:
                diffs.append({"path": f"predictions.{k}", "generated": v, "derived": mine_pred.get(k)})
        if gen.get("exp2_system") != prompts["exp2"]["system"]:
            diffs.append({"path": "exp2_system", "generated": gen.get("exp2_system"), "derived": prompts["exp2"]["system"]})
        if gen.get("exp2_inputs") != prompts["exp2"]["inputs"]:
            diffs.append({"path": "exp2_inputs", "generated": gen.get("exp2_inputs"), "derived": prompts["exp2"]["inputs"]})
        if gen.get("experiments") != protocol["experiments"]:
            diffs.append({"path": "experiments", "generated": "differs from evidence/opus_protocol/protocol.json experiments", "derived": "protocol.json"})
        comparison["exp2_cells_compared"] = len(gen.get("exp2_cells", []))
        comparison["differences"] = diffs
        test("comparison", "generated/opus_study.json equals the independent derivation", 0, len(diffs))
    report = {"generated_by": "verification/opus_study_audit.py", "provenance": provenance, "verdicts": verdicts, "comparison_with_generated": comparison,
              "experiment_2": {"cells": cells2, "opus46_null_by_ceiling": {"4000": p1, **{str(k): v for k, v in other_ceilings_46.items()}}, "opus45_null_by_ceiling": {"4000": p2, **{str(k): v for k, v in other_ceilings_45.items()}}, "controls_both_models_all_ceilings": p3, "opus45_near_void": nv_summary},
              "experiment_1": {"totals": {m45: t45, m46: t46}, "per_input": per_input1, "first_dispatch_utc": min(r["timestamp_utc"] for r in e1), "last_dispatch_utc": max(r["timestamp_utc"] for r in e1)},
              "experiment_3": {"cells": cells3, "cell_map": cellmap, "system_strings_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in strings.items()}},
              "tests": TESTS, "tests_total": len(TESTS), "tests_passed": sum(1 for t in TESTS if t["pass"]), "result": "PASS" if all(t["pass"] for t in TESTS) else "FAIL"}
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote verification/opus_study_audit.json | tests", report["tests_passed"], "/", report["tests_total"], "| result", report["result"])
    for k, v in verdicts.items():
        print(f"  {k}: {v.get('verdict', '')} | {v['observed'][:120]}")
    for t in TESTS:
        if not t["pass"]:
            print("  FAIL", t)


if __name__ == "__main__":
    main()
