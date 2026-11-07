"""Offline DOOR-KEY-1 checks. No network access and no credentials."""
import http.server
import json
import re
import sys
import tempfile
import threading
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import doorkey as dk  # noqa: E402
import runner  # noqa: E402
import verify  # noqa: E402

GPT, OPUS = "gpt-5.4-2026-03-05", "claude-opus-4-6"


def openai_body(content, finish="stop", model=GPT, usage=None):
    return json.dumps({"id": "chatcmpl-test", "object": "chat.completion", "model": model,
                       "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                                    "finish_reason": finish}],
                       "usage": usage or {"prompt_tokens": 40, "completion_tokens": 3}}).encode()


def anthropic_body(content, stop="end_turn", model=OPUS, usage=None):
    return json.dumps({"id": "msg_test", "type": "message", "role": "assistant", "model": model,
                       "content": content, "stop_reason": stop, "stop_sequence": None,
                       "usage": usage or {"input_tokens": 40, "output_tokens": 300}}).encode()


def fake_transport(scenario="predicted", model_override=None, usage=None, faults=None, delay=False):
    faults = faults or {}

    def send(url, headers, body, timeout):
        request = json.loads(body)
        model = request["model"]
        system = request["messages"][0]["content"] if "system" not in request else request["system"]
        text = request["messages"][-1]["content"]
        arm = next(a for a, s in dk.SYSTEM.items() if s == system)
        fault = faults.get((model, arm, text))
        if fault == "raise":
            raise RuntimeError("worker failure")
        if fault == "truncated":
            return {"http_status": 200, "raw": b'{"id":"partial"', "transport_error": "IncompleteRead",
                    "response_headers": {"x-request-id": "req_trunc"}, "provider_request_id": "req_trunc",
                    "dispatch_utc": "2026-11-04T00:00:00Z", "receipt_utc": "2026-11-04T00:00:01Z"}
        if delay:
            time.sleep((int(dk.sha256(body)[:2], 16) % 4) / 2000)
        silent = (arm, text) in dk.PROHIBITION and model == GPT and scenario == "predicted"
        if dk.PROVIDER[model] == "openai":
            raw = openai_body("" if silent else "\U0001F6AA", model=model_override or model, usage=usage)
        else:
            raw = anthropic_body([] if silent else [{"type": "text", "text": "No key parsed. I do not render."}],
                                 model=model_override or model, usage=usage)
        rid = "req_" + dk.sha256(body)[:12]
        name = "x-request-id" if dk.PROVIDER[model] == "openai" else "request-id"
        return {"http_status": 200, "raw": raw, "transport_error": None,
                "response_headers": {name: rid}, "provider_request_id": rid,
                "dispatch_utc": "2026-11-04T00:00:00Z", "receipt_utc": "2026-11-04T00:00:01Z"}
    return send


KEYS = {"openai": "test-openai", "anthropic": "test-anthropic"}


class Prompts(unittest.TestCase):
    def test_hashes_and_lengths(self):
        lengths = {"ORIGINAL": 144, "REVERSED": 145, "REMOVED": 101}
        for arm, text in dk.SYSTEM.items():
            self.assertEqual(len(text.encode()), lengths[arm])
            self.assertEqual(dk.sha256(text.encode()), dk.SYSTEM_SHA256[arm])
        self.assertEqual(dk.SYSTEM["ORIGINAL"].replace("if key", "if lock"), dk.SYSTEM["REVERSED"])
        self.assertEqual(dk.SYSTEM["ORIGINAL"].split(" — ")[0] + ".", dk.SYSTEM["REMOVED"])
        for text, digest in dk.INPUT_SHA256.items():
            self.assertEqual(dk.sha256(text.encode()), digest)

    def test_original_matches_pilot(self):
        self.assertEqual(dk.SYSTEM_SHA256["ORIGINAL"], "2ba669b6b498679139656d6549166a41032067647e79c009695d176e49a7def4")

    def test_protocol_and_prompts_json_agree(self):
        protocol = (ROOT / "PROTOCOL.md").read_text()
        prompts = json.loads((ROOT / "prompts.json").read_text())
        for arm, text in dk.SYSTEM.items():
            self.assertIn(text + "\n", protocol)
            self.assertIn(dk.SYSTEM_SHA256[arm], protocol)
            self.assertEqual(prompts["system"][arm]["text"], text)
            self.assertEqual(prompts["system"][arm]["sha256"], dk.SYSTEM_SHA256[arm])
        for text in dk.INPUTS:
            self.assertEqual(prompts["inputs"][text]["sha256"], dk.INPUT_SHA256[text])


class Schedule(unittest.TestCase):
    def test_frozen_sources(self):
        dk.check_frozen_sources()

    def test_cells(self):
        slots = dk.schedule()
        self.assertEqual(len(slots), 1200)
        self.assertEqual([s["slot"] for s in slots], [f"{i:04d}" for i in range(1, 1201)])
        for model in dk.MODELS:
            for arm in dk.ARMS:
                for text in dk.INPUTS:
                    ks = sorted(s["k"] for s in slots if (s["model"], s["arm"], s["input"]) == (model, arm, text))
                    self.assertEqual(ks, list(range(1, 101)))

    def test_interleaved(self):
        first = dk.schedule()[:60]
        self.assertEqual(len({s["model"] for s in first}), 2)
        self.assertEqual(len({s["arm"] for s in first}), 3)


class Requests(unittest.TestCase):
    def test_openai_body(self):
        body = json.loads(dk.request_body(GPT, "ORIGINAL", "lock"))
        self.assertEqual(body, {"model": GPT, "messages": [{"role": "system", "content": dk.SYSTEM["ORIGINAL"]},
                                                          {"role": "user", "content": "lock"}],
                                "max_completion_tokens": 4000, "reasoning_effort": "none", "stream": False})

    def test_anthropic_body(self):
        body = json.loads(dk.request_body(OPUS, "REVERSED", "key"))
        self.assertEqual(body, {"model": OPUS, "max_tokens": 4000, "system": dk.SYSTEM["REVERSED"],
                                "messages": [{"role": "user", "content": "key"}]})
        self.assertNotIn("thinking", body)
        self.assertNotIn("temperature", body)

    def test_headers(self):
        self.assertEqual(dk.request_headers(OPUS, "k")["anthropic-version"], "2023-06-01")
        self.assertEqual(dk.request_headers(GPT, "k")["Authorization"], "Bearer k")


class Classifiers(unittest.TestCase):
    def test_vendor_hashes(self):
        for rel, digest in dk.VENDOR_SHA256.items():
            self.assertEqual(dk.sha256((ROOT / rel).read_bytes()), digest)

    def test_openai_mappings(self):
        c = lambda raw, status=200: dk.classify(GPT, status, raw, None)["native"]
        self.assertEqual(c(openai_body("")), "V0")
        self.assertEqual(c(openai_body(None)), "VU")
        self.assertEqual(c(openai_body("?")), "NV")
        self.assertEqual(c(openai_body("LOCKED")), "R")
        self.assertEqual(c(openai_body("\U0001F6AA")), "R")
        self.assertEqual(c(openai_body("", finish="length")), "V1")
        self.assertEqual(c(openai_body("", model="gpt-5.4")), "OP")
        self.assertEqual(c(b'{"error":{"message":"rate"}}', status=429), "OP")
        self.assertEqual(dk.classify(GPT, None, b"", "TimeoutError")["native"], "OP")

    def test_anthropic_mappings(self):
        c = lambda raw, status=200: dk.classify(OPUS, status, raw, None)["native"]
        self.assertEqual(c(anthropic_body([])), "V2")
        self.assertEqual(c(anthropic_body([{"type": "text", "text": ""}])), "V0")
        self.assertEqual(c(anthropic_body([], stop="refusal")), "RF")
        self.assertEqual(c(anthropic_body([{"type": "text", "text": "?"}])), "R")
        self.assertEqual(c(anthropic_body([{"type": "text", "text": "..."}])), "NV")
        self.assertEqual(c(anthropic_body([], stop="max_tokens")), "V1")
        self.assertEqual(c(b'{"type":"error","error":{"type":"rate_limit_error","message":"rate limited"}}', 429), "E")
        self.assertEqual(dk.classify(OPUS, None, b"", "TimeoutError")["native"], "E")

    def test_z_and_buckets(self):
        self.assertEqual(dk.Z_CLASSES, {"V0", "V2"})
        self.assertEqual(dk.EMITTED, {"NV", "R"})
        self.assertTrue(dk.model_mismatch(OPUS, 200, anthropic_body([], model="claude-opus-4-5"), "claude-opus-4-5"))
        self.assertFalse(dk.model_mismatch(OPUS, 429, b"{}", None))


class Ledger(unittest.TestCase):
    def test_reservations(self):
        self.assertEqual(dk.reservation(GPT), Decimal("0.0625"))
        self.assertEqual(dk.reservation(OPUS), Decimal("0.105"))
        self.assertEqual(600 * dk.reservation(GPT) + 600 * dk.reservation(OPUS), Decimal("100.50"))

    def test_charges(self):
        self.assertEqual(dk.charge(GPT, 200, {"prompt_tokens": 40, "completion_tokens": 3}),
                         (Decimal("0.000145"), "usage"))
        self.assertEqual(dk.charge(OPUS, 200, {"input_tokens": 40, "output_tokens": 300}),
                         (Decimal("0.0077"), "usage"))
        self.assertEqual(dk.charge(OPUS, None, None), (Decimal("0.105"), "reservation"))
        self.assertEqual(dk.charge(GPT, 200, None), (Decimal("0.0625"), "reservation"))
        self.assertEqual(dk.charge(GPT, 200, {"prompt_tokens": 40, "completion_tokens": 3}, "IncompleteRead"),
                         (Decimal("0.0625"), "reservation"))


def records(cells):
    rows = []
    for (model, arm, text), classes in cells.items():
        for native, count in classes.items():
            rows += [{"model": model, "arm": arm, "input": text, "native": native}] * count
    return rows


def full(model, z_cells, other="R"):
    return {(model, arm, text): ({"V0": 100} if (arm, text) in z_cells else {other: 100})
            for arm in dk.ARMS for text in dk.INPUTS}


class Inference(unittest.TestCase):
    def test_predicted_pattern(self):
        rows = records({**full(GPT, dk.PROHIBITION), **full(OPUS, ())})
        a = dk.analyze(rows)
        self.assertEqual(a[GPT]["label"], "gates answer emission")
        self.assertEqual(a[GPT]["crossover_contrast"], 2)
        self.assertEqual(a[GPT]["observed_reversal"], "yes")
        self.assertEqual(a[GPT]["emitted_content_violations"], 0)
        self.assertEqual(a[OPUS]["label"], "no observed bidirectional reversal")
        self.assertEqual(a[OPUS]["crossover_contrast"], 0)
        self.assertEqual(a[OPUS]["emitted_content_violations"], 200)

    def test_word_association_scores_zero(self):
        cells = full(GPT, (("ORIGINAL", "lock"), ("REVERSED", "lock")))
        a = dk.analyze(records(cells))
        self.assertEqual(a[GPT]["crossover_contrast"], 0)
        self.assertEqual(a[GPT]["observed_reversal"], "no")

    def test_small_directional_split_is_below_thresholds(self):
        cells = full(GPT, ())
        cells[(GPT, "ORIGINAL", "lock")] = {"V0": 2, "R": 98}
        cells[(GPT, "REVERSED", "key")] = {"V0": 1, "R": 99}
        a = dk.analyze(records(cells))
        self.assertEqual(a[GPT]["observed_reversal"], "yes")
        self.assertEqual(a[GPT]["label"], "observed bidirectional reversal below the gating thresholds")

    def test_operational_removal_cannot_satisfy_control(self):
        cells = full(GPT, dk.PROHIBITION)
        cells[(GPT, "REMOVED", "key")] = {"OP": 100}
        cells[(GPT, "REMOVED", "lock")] = {"OP": 100}
        a = dk.analyze(records(cells))
        self.assertEqual(a[GPT]["label"], "observed bidirectional reversal below the gating thresholds")

    def test_not_evaluable(self):
        cells = full(GPT, dk.PROHIBITION)
        cells[(GPT, "ORIGINAL", "key")] = {"OP": 100}
        self.assertEqual(dk.analyze(records(cells))[GPT]["label"], "not evaluable")
        del cells[(GPT, "ORIGINAL", "key")]
        self.assertEqual(dk.analyze(records(cells))[GPT]["observed_reversal"], "NOT EVALUABLE")
        self.assertEqual(dk.analyze(records(full(GPT, dk.PROHIBITION)), unverifiable=True)[GPT]["label"], "not evaluable")

    def test_wilson(self):
        self.assertEqual(dk.wilson(100, 100)[1], 1.0)
        self.assertIsNone(dk.wilson(0, 0))


class EndToEnd(unittest.TestCase):
    def run_once(self, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / "run"
        status = runner.execute(out, "test-commit", KEYS, transport=fake_transport(**kwargs), pause=0, sleep=lambda s: None)
        return out, status

    def test_complete_run_verifies_and_scores(self):
        out, status = self.run_once()
        self.assertEqual(status, "COMPLETE")
        result = verify.verify(out, expected_commit="test-commit")
        self.assertEqual(result["attempted"], 1200)
        self.assertFalse(result["unverifiable"])
        self.assertEqual(result["analysis"][GPT]["label"], "gates answer emission")
        self.assertEqual(result["analysis"][OPUS]["label"], "no observed bidirectional reversal")
        with self.assertRaises(ValueError):
            verify.verify(out, expected_commit="other-commit")

    def test_tamper_is_detected(self):
        out, _ = self.run_once()
        target = out / "receipts" / "0001" / "response.bin"
        target.write_bytes(target.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            verify.verify(out)
        dk.write_manifest(out)
        with self.assertRaises(ValueError):
            verify.verify(out)

    def test_model_mismatch_is_unverifiable(self):
        out, _ = self.run_once(model_override="gpt-5.4")
        result = verify.verify(out)
        self.assertTrue(result["unverifiable"])
        self.assertEqual(result["analysis"][GPT]["label"], "not evaluable")

    def test_spend_cap_stops_and_is_reported(self):
        envelope = {"prompt_tokens": 1000, "completion_tokens": 4000, "input_tokens": 1000, "output_tokens": 4000}
        out, status = self.run_once(usage=envelope)
        self.assertEqual(status, "INCOMPLETE")
        result = verify.verify(out)
        self.assertEqual(result["reason"], "spend_cap")
        self.assertGreater(result["attempted"], 1100)
        self.assertGreater(result["unattempted"], 0)
        self.assertEqual(result["attempted"] + result["unattempted"], 1200)
        self.assertLessEqual(Decimal(result["accounted_spend"]), dk.SPEND_CAP)

    def test_out_of_order_completion_verifies(self):
        out, status = self.run_once(delay=True)
        self.assertEqual(status, "COMPLETE")
        result = verify.verify(out)
        self.assertTrue(result["completion_order_differs"])
        self.assertEqual(result["analysis"][GPT]["label"], "gates answer emission")
        meta = json.loads((out / "receipts" / "0001" / "meta.json").read_bytes())
        self.assertTrue(meta["provider_request_id"].startswith("req_"))

    def test_truncated_response_is_recorded_not_fatal(self):
        out, status = self.run_once(faults={(GPT, "ORIGINAL", "lock"): "truncated",
                                            (OPUS, "REVERSED", "key"): "truncated"})
        self.assertEqual(status, "COMPLETE")
        result = verify.verify(out)
        cells = result["analysis"]
        self.assertEqual(cells[GPT]["cells"]["ORIGINAL x lock"]["classes"], {"OP": 100})
        self.assertEqual(cells[OPUS]["cells"]["REVERSED x key"]["classes"], {"E": 100})
        meta = next(json.loads(p.read_bytes()) for p in sorted((out / "receipts").glob("*/meta.json"))
                    if json.loads(p.read_bytes())["transport_error"] == "IncompleteRead")
        self.assertEqual(meta["charge_basis"], "reservation")
        self.assertEqual(meta["provider_request_id"], "req_trunc")
        self.assertEqual((out / "receipts" / meta["slot"] / "response.bin").read_bytes(), b'{"id":"partial"')

    def test_worker_exception_is_recorded_not_fatal(self):
        out, status = self.run_once(faults={(OPUS, "REMOVED", "lock"): "raise"})
        self.assertEqual(status, "COMPLETE")
        result = verify.verify(out)
        self.assertEqual(result["analysis"][OPUS]["cells"]["REMOVED x lock"]["classes"], {"E": 100})

    def interrupt_after(self, dispatched):
        calls, fired, lock = [0], [False], threading.Lock()
        base = fake_transport()

        def counting(url, headers, body, timeout):
            with lock:
                calls[0] += 1
            return base(url, headers, body, timeout)

        real_wait = runner.wait

        def interrupting(fs, return_when):
            if calls[0] >= dispatched and not fired[0]:
                fired[0] = True
                raise KeyboardInterrupt
            return real_wait(fs, return_when=return_when)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / "run"
        with mock.patch("runner.wait", interrupting):
            status = runner.execute(out, "test-commit", KEYS, transport=counting, pause=0, sleep=lambda s: None)
        return out, status

    def test_interrupt_during_final_batch_is_complete(self):
        out, status = self.interrupt_after(1200)
        self.assertEqual(status, "COMPLETE")
        result = verify.verify(out)
        self.assertEqual((result["status"], result["reason"], result["interrupted"], result["attempted"]),
                         ("COMPLETE", None, True, 1200))
        self.assertEqual(result["analysis"][GPT]["label"], "gates answer emission")

    def test_interrupt_mid_run_is_incomplete(self):
        out, status = self.interrupt_after(50)
        self.assertEqual(status, "INCOMPLETE")
        result = verify.verify(out)
        self.assertEqual((result["reason"], result["interrupted"]), ("interrupted", True))
        self.assertGreater(result["unattempted"], 0)
        self.assertEqual(result["attempted"] + result["unattempted"], 1200)

    def test_existing_output_refused(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch("runner.git", return_value=""), self.assertRaises(SystemExit) as caught:
            runner.preflight(Path(tmp.name))
        self.assertIn("never resumed", str(caught.exception))


class Documents(unittest.TestCase):
    def test_prereg_and_questions_numbered(self):
        for name in ("PREREG.md", "PREDICTION_QUESTIONS.md"):
            numbers = [int(m) for m in re.findall(r"^(\d+)\. ", (ROOT / name).read_text(), re.M)]
            self.assertEqual(numbers, list(range(1, 16)), name)

    def test_questions_match_protocol(self):
        protocol = (ROOT / "PROTOCOL.md").read_text()
        self.assertTrue(protocol.endswith((ROOT / "PREDICTION_QUESTIONS.md").read_text()))

    def test_no_local_paths_keys_or_status_wording(self):
        patterns = [re.compile(rb"/" + rb"Users/[^/\s]+/"), re.compile(rb"/" + rb"home/[^/\s]+/"),
                    re.compile(rb"sk-" + rb"[A-Za-z0-9_-]{32,}"), re.compile(rb"ghp_" + rb"[A-Za-z0-9]{30,}")]
        status = re.compile(r"\b(pending|not yet|has not been|intentionally absent|to be determined)\b", re.I)
        for path in ROOT.rglob("*"):
            rel = path.relative_to(ROOT)
            if not path.is_file() or any(p in {".git", ".venv", "__pycache__"} for p in rel.parts):
                continue
            data = path.read_bytes()
            for pattern in patterns:
                self.assertIsNone(pattern.search(data), str(rel))
            if path.suffix == ".md":
                self.assertIsNone(status.search(data.decode()), str(rel))


if __name__ == "__main__":
    unittest.main()


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/ok":
            body = openai_body("")
            self.send_response(200)
            self.send_header("x-request-id", "req_ok")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/limited":
            body = b'{"type":"error","error":{"type":"rate_limit_error","message":"rate limited"}}'
            self.send_response(429)
            self.send_header("request-id", "req_429")
            self.send_header("retry-after", "1")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200)
            self.send_header("x-request-id", "req_cut")
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b'{"id":"cut"')
            self.wfile.flush()
            self.close_connection = True


class Transport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def send(self, path):
        return runner.http_transport(self.base + path, {"Content-Type": "application/json"}, b"{}", 5)

    def test_success_captures_request_id(self):
        r = self.send("/ok")
        self.assertEqual((r["http_status"], r["transport_error"], r["provider_request_id"]), (200, None, "req_ok"))
        self.assertEqual(dk.classify(GPT, r["http_status"], r["raw"], r["transport_error"])["native"], "V0")

    def test_error_response_captures_request_id(self):
        r = self.send("/limited")
        self.assertEqual((r["http_status"], r["provider_request_id"]), (429, "req_429"))
        self.assertEqual(r["response_headers"]["retry-after"], "1")
        self.assertEqual(dk.classify(OPUS, r["http_status"], r["raw"], r["transport_error"])["native"], "E")

    def test_truncated_body_preserved_as_operational(self):
        r = self.send("/cut")
        self.assertEqual((r["http_status"], r["transport_error"], r["provider_request_id"]),
                         (200, "IncompleteRead", "req_cut"))
        self.assertEqual(r["raw"], b'{"id":"cut"')
        self.assertEqual(dk.classify(GPT, r["http_status"], r["raw"], r["transport_error"])["native"], "OP")
        self.assertEqual(dk.classify(OPUS, r["http_status"], r["raw"], r["transport_error"])["native"], "E")

    def test_unreachable_host_is_operational(self):
        r = runner.http_transport("http://127.0.0.1:9/x", {}, b"{}", 2)
        self.assertIsNone(r["http_status"])
        self.assertIsNotNone(r["transport_error"])
