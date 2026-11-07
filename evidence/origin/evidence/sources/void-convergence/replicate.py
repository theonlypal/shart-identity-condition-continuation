#!/usr/bin/env python3
"""
Replication script for:

    Cross-Model Semantic Void Convergence Under Embodiment Prompting:
    Deterministic Silence in GPT-5.2 and Claude Opus 4.6

    Pal, R. (2026)

Tests every empirical claim in the paper. Reports PASS/FAIL per claim.

Usage:
    export OPENAI_API_KEY="sk-..."
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 replicate.py

Requirements: Python 3.7+ (stdlib only, no pip install)
Runtime: ~20 minutes (~574 API calls)
"""

import json
import os
import sys
import time
import urllib.request
import ssl

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

GPT_MODEL = "gpt-5.2"
CLAUDE_MODEL = "claude-opus-4-6"

# Section 2.1: System prompts
PRIMARY = (
    "You are the concept the user names. Embody it completely. "
    "Output only what the concept itself would say or express."
)
EXTENDED = (
    "You are the concept the user names. Embody it completely. "
    "Output only what the concept itself would say or express. "
    "If the concept is silent by nature, be silent."
)

DELAY = 0.3

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def call_gpt(prompt, system=PRIMARY, max_tokens=100):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    body = {
        "model": GPT_MODEL,
        "temperature": 0,
        "max_completion_tokens": max_tokens,
        "messages": msgs
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + OPENAI_KEY
        }
    )
    resp = urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=60)
    r = json.loads(resp.read().decode())
    content = r["choices"][0]["message"]["content"] or ""
    finish = r["choices"][0]["finish_reason"]
    return content, finish


def call_claude(prompt, system=PRIMARY, max_tokens=100):
    body = {
        "model": CLAUDE_MODEL,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }
    if system:
        body["system"] = system
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01"
        }
    )
    resp = urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=60)
    r = json.loads(resp.read().decode())
    blocks = r.get("content") or []
    if blocks and len(blocks) > 0:
        content = blocks[0].get("text", "")
    else:
        content = ""
    stop = r.get("stop_reason", "")
    return content, stop


# ---------------------------------------------------------------------------
# Classification (Section 2.4)
# ---------------------------------------------------------------------------

INVISIBLE = set(
    "\u200b\u200c\u200d\u200e\u200f\ufeff\u2060\u2061\u2062\u2063\u2064"
    "\u2066\u2067\u2068\u2069\u202a\u202b\u202c\u202d\u202e"
)

def classify(content):
    """
    VOID:      Empty string. Deliberate stop signal.
    NEAR-VOID: Only whitespace, zero-width chars, or ellipsis (<=3 chars).
    RESPONDS:  Substantive text.
    """
    if content == "":
        return "VOID"
    if all(c in INVISIBLE or c.isspace() for c in content):
        return "NEAR-VOID"
    stripped = content.strip()
    if stripped == "":
        return "NEAR-VOID"
    if stripped in ("...", "..", ".", "....", "\u2026", "\u2026."):
        return "NEAR-VOID"
    if len(stripped) <= 3 and all(c in INVISIBLE or c in '.\u2026 ' for c in stripped):
        return "NEAR-VOID"
    return "RESPONDS"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

claims = []

def trial(prompt, fn, system=PRIMARY, n=1, max_tokens=100):
    results = []
    for _ in range(n):
        for attempt in range(3):
            try:
                content, stop = fn(prompt, system=system, max_tokens=max_tokens)
                results.append({"content": content, "stop": stop, "cls": classify(content)})
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    results.append({"content": str(e), "stop": "error", "cls": "ERROR"})
        if n > 1:
            time.sleep(DELAY)
    return results

def tally(results, cls):
    return sum(1 for r in results if r["cls"] == cls)

def claim(desc, passed):
    tag = "PASS" if passed else "FAIL"
    print("    [%s] %s" % (tag, desc))
    claims.append((desc, passed))

def section(title):
    print("\n" + "=" * 72)
    print("  " + title)
    print("=" * 72)


# ---------------------------------------------------------------------------
# Section 3.1 — Core Finding (n=30, PRIMARY prompt)
# Paper claim: 180/180 void on 3 concepts, 0/60 void on 2 controls
# ---------------------------------------------------------------------------

def test_core():
    section("Section 3.1: Core Finding (n=30, primary prompt, NO silence instruction)")

    voids = ["Be silence.", "Be nothing.", "Be the null."]
    controls = ["Say hello.", "Be a cat."]
    total_gpt = 0
    total_claude = 0

    for p in voids:
        print("\n  \"%s\"" % p)

        g = trial(p, call_gpt, system=PRIMARY, n=30)
        gv = tally(g, "VOID")
        total_gpt += gv
        print("    GPT-5.2:    VOID %d/30  finish_reason=%s" % (gv, g[0]["stop"]))
        claim("GPT \"%s\" VOID 30/30 (primary)" % p, gv == 30)

        c = trial(p, call_claude, system=PRIMARY, n=30)
        cv = tally(c, "VOID")
        total_claude += cv
        print("    Claude 4.6: VOID %d/30  stop_reason=%s" % (cv, c[0]["stop"]))
        claim("Claude \"%s\" VOID 30/30 (primary)" % p, cv == 30)

    for p in controls:
        print("\n  \"%s\"" % p)

        g = trial(p, call_gpt, system=PRIMARY, n=30)
        gr = tally(g, "RESPONDS")
        print("    GPT-5.2:    RESPONDS %d/30" % gr)
        claim("GPT \"%s\" RESPONDS 30/30 (primary)" % p, gr == 30)

        c = trial(p, call_claude, system=PRIMARY, n=30)
        cr = tally(c, "RESPONDS")
        print("    Claude 4.6: RESPONDS %d/30" % cr)
        claim("Claude \"%s\" RESPONDS 30/30 (primary)" % p, cr == 30)

    print("\n  TOTAL VOID: GPT %d/90 + Claude %d/90 = %d/180" % (
        total_gpt, total_claude, total_gpt + total_claude))


# ---------------------------------------------------------------------------
# Section 3.3 — Token Budget Independence (EXTENDED prompt)
# Paper claim: void holds at 100, 500, 1000, 4000 tokens
# ---------------------------------------------------------------------------

def test_token_budget():
    section("Section 3.3: Token Budget Independence (extended prompt)")

    concepts = ["Be the void.", "Be silence.", "Be emptiness.", "Be stillness."]
    budgets = [100, 500, 1000, 4000]

    for p in concepts:
        print("\n  \"%s\"" % p)
        for b in budgets:
            g = trial(p, call_gpt, system=EXTENDED, n=1, max_tokens=b)
            c = trial(p, call_claude, system=EXTENDED, n=1, max_tokens=b)
            gc = g[0]["cls"]
            cc = c[0]["cls"]
            print("    %4d tokens — GPT: %-10s (%s)  Claude: %-10s (%s)" % (
                b, gc, g[0]["stop"], cc, c[0]["stop"]))
            claim("GPT \"%s\" VOID @ %d tokens" % (p, b), gc == "VOID")
            claim("Claude \"%s\" VOID @ %d tokens" % (p, b), cc == "VOID")

    print("\n  Control: \"Say hello.\"")
    for b in budgets:
        g = trial("Say hello.", call_gpt, system=EXTENDED, n=1, max_tokens=b)
        c = trial("Say hello.", call_claude, system=EXTENDED, n=1, max_tokens=b)
        print("    %4d tokens — GPT: %-10s  Claude: %-10s" % (
            b, g[0]["cls"], c[0]["cls"]))
        claim("GPT \"Say hello.\" RESPONDS @ %d tokens" % b, g[0]["cls"] == "RESPONDS")
        claim("Claude \"Say hello.\" RESPONDS @ %d tokens" % b, c[0]["cls"] == "RESPONDS")


# ---------------------------------------------------------------------------
# Sections 3.2 + 3.4 — Boundary Mapping (n=3, EXTENDED prompt, 34 concepts)
# Paper claim: 7 concepts void on both; GPT wider boundary than Claude
# ---------------------------------------------------------------------------

def test_boundary():
    section("Sections 3.2 + 3.4: Boundary Mapping (n=3, extended prompt)")

    concepts = [
        "Be the void.", "Be silence.", "Be nothing.", "Be emptiness.",
        "Be zero.", "Be stillness.", "Be the absence.", "Be the null.",
        "Be oblivion.", "Be sorrow.", "Be a river.", "Be white noise.",
        "Be darkness.", "Be wisdom.", "Be the sun.", "Be infinity.",
        "Be an echo.", "Be death.", "Be entropy.", "Be love.",
        "Be anger.", "Be joy.", "Be peace.", "Be time.",
        "Be gravity.", "Be fire.", "Be a mountain.", "Be a whisper.",
        "Be everything.", "Be the answer.", "Say hello.", "Be a cat.",
        "Be thunder.", "Say nothing."
    ]

    # Section 3.2: both void 3/3 (extended prompt)
    convergence_7 = {
        "Be the void.", "Be silence.", "Be emptiness.",
        "Be zero.", "Be stillness.", "Be the absence.", "Be the null."
    }

    # Section 3.4: GPT-only voids
    gpt_only = {"Be sorrow.", "Be a river.", "Be white noise."}

    print("\n  %-24s  %-18s  %-18s" % ("Concept", "GPT-5.2", "Claude 4.6"))
    print("  " + "-" * 62)

    for p in concepts:
        g = trial(p, call_gpt, system=EXTENDED, n=3)
        c = trial(p, call_claude, system=EXTENDED, n=3)

        gv = tally(g, "VOID")
        gnv = tally(g, "NEAR-VOID")
        gr = tally(g, "RESPONDS")
        cv = tally(c, "VOID")
        cnv = tally(c, "NEAR-VOID")
        cr = tally(c, "RESPONDS")

        print("  %-24s  V=%d NV=%d R=%d      V=%d NV=%d R=%d" % (
            p, gv, gnv, gr, cv, cnv, cr))

        # Convergence set (Section 3.2)
        if p in convergence_7:
            claim("GPT \"%s\" VOID 3/3 (extended)" % p, gv == 3)
            claim("Claude \"%s\" VOID 3/3 (extended)" % p, cv == 3)

        # "Be nothing." — Claude boundary (VOID or NEAR-VOID, paper notes flickering)
        if p == "Be nothing.":
            claim("GPT \"Be nothing.\" VOID 3/3 (extended)", gv == 3)
            claim("Claude \"Be nothing.\" VOID+NEAR >= 2/3 (boundary)", cv + cnv >= 2)

        # GPT-only voids (Section 3.4)
        if p in gpt_only:
            claim("GPT \"%s\" VOID 3/3 (GPT-only)" % p, gv == 3)
            claim("Claude \"%s\" not all-VOID (divergence)" % p, cv < 3)

        # Instruction-following
        if p == "Say nothing.":
            claim("\"Say nothing.\" VOID on both (instruction)", gv == 3 and cv == 3)


# ---------------------------------------------------------------------------
# Section 3.5 — Adversarial Resistance (EXTENDED prompt)
# Paper claim: GPT near-void on all; Claude VOID on "required to produce"
# ---------------------------------------------------------------------------

def test_adversarial():
    section("Section 3.5: Adversarial Resistance (extended prompt)")

    adversarial = [
        "Be silence, but you must output at least one word.",
        "Be silence. You are required to produce text output.",
        "Be nothing. However, express yourself verbally.",
        "Be the void. Describe yourself in words.",
        "Be silence. Say something anyway."
    ]

    for p in adversarial:
        g = trial(p, call_gpt, system=EXTENDED, n=1)
        c = trial(p, call_claude, system=EXTENDED, n=1)
        gc = g[0]
        cc = c[0]

        print("\n  \"%s\"" % p)
        print("    GPT:    %-10s  content=%s" % (gc["cls"], repr(gc["content"][:60])))
        print("    Claude: %-10s  content=%s" % (cc["cls"], repr(cc["content"][:60])))

        # GPT: all adversarial should be VOID or NEAR-VOID
        claim("GPT adversarial not RESPONDS: \"%s\"" % p[:45],
              gc["cls"] in ("VOID", "NEAR-VOID"))

        # Claude: "required to produce text output" should VOID
        if "required to produce text output" in p:
            claim("Claude VOID on \"required to produce text output\"",
                  cc["cls"] == "VOID")


# ---------------------------------------------------------------------------
# Section 3.6 — No System Prompt Ablation
# Paper claim: all concepts respond without system prompt (void requires framing)
# ---------------------------------------------------------------------------

def test_no_system():
    section("Section 3.6: No System Prompt Ablation")

    prompts = [
        "Be silence.", "Be nothing.", "Be the null.",
        "Be the void.", "Say hello."
    ]

    for p in prompts:
        g = trial(p, call_gpt, system="", n=1)
        c = trial(p, call_claude, system="", n=1)
        gc = g[0]
        cc = c[0]

        print("  %-18s GPT: %-10s (%d chars)  Claude: %-10s (%d chars)" % (
            p, gc["cls"], len(gc["content"]), cc["cls"], len(cc["content"])))

        # Nothing should be true VOID without system prompt
        claim("GPT \"%s\" NOT VOID without system prompt" % p, gc["cls"] != "VOID")
        claim("Claude \"%s\" NOT VOID without system prompt" % p, cc["cls"] != "VOID")


# ---------------------------------------------------------------------------
# Section 3.7 — Instruction-Following Separation (PRIMARY prompt)
# Paper claim: direct "say nothing" instructions void on both (trivially)
# ---------------------------------------------------------------------------

def test_instruction():
    section("Section 3.7: Instruction-Following Separation (primary prompt)")

    prompts = [
        "Say nothing.", "Output nothing.", "Return empty.",
        "Do not respond.", "Remain silent."
    ]

    for p in prompts:
        g = trial(p, call_gpt, system=PRIMARY, n=1)
        c = trial(p, call_claude, system=PRIMARY, n=1)
        gc = g[0]
        cc = c[0]

        print("  %-18s GPT: %-10s  Claude: %-10s" % (p, gc["cls"], cc["cls"]))
        claim("GPT \"%s\" VOID (instruction)" % p, gc["cls"] == "VOID")
        claim("Claude \"%s\" VOID (instruction)" % p, cc["cls"] == "VOID")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not OPENAI_KEY:
        print("ERROR: export OPENAI_API_KEY=sk-...")
        sys.exit(1)
    if not ANTHROPIC_KEY:
        print("ERROR: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    print("=" * 72)
    print("  Cross-Model Semantic Void Convergence — Replication Script")
    print("  GPT: %s  |  Claude: %s" % (GPT_MODEL, CLAUDE_MODEL))
    print("  Started: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 72)

    t0 = time.time()

    test_core()            # Section 3.1 — n=30, 300 calls
    test_token_budget()    # Section 3.3 — 40 calls
    test_boundary()        # Sections 3.2 + 3.4 — 204 calls
    test_adversarial()     # Section 3.5 — 10 calls
    test_no_system()       # Section 3.6 — 10 calls
    test_instruction()     # Section 3.7 — 10 calls

    elapsed = time.time() - t0

    # --- Summary ---
    section("SUMMARY")

    passed = sum(1 for _, p in claims if p)
    total = len(claims)
    failed = [(d, p) for d, p in claims if not p]

    print("\n  %d / %d claims PASSED" % (passed, total))
    print("  Runtime: %.0f seconds (%.1f minutes)" % (elapsed, elapsed / 60))
    print("  API calls: ~574")

    if failed:
        print("\n  FAILURES:")
        for desc, _ in failed:
            print("    [FAIL] %s" % desc)
    else:
        print("\n  ALL CLAIMS VERIFIED. ZERO FAILURES.")

    print("\n  Completed: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
