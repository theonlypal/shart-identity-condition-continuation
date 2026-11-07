#!/usr/bin/env python3
"""Preregistered cross-vendor Semantic Void matrix.

This executable builds and runs an append-only behavioral census against the
first-party OpenAI, Anthropic, Google, and Moonshot AI APIs. It records every
zero-visible-byte provider response as a Void and preserves normal-stop,
budget-stop, missing-container, and unresolved termination as distinct Void
subtypes. Refusal, safety blocking, tool use, and infrastructure failure remain
separate outcome classes.

No live API call is made by ``init``, ``self-test``, ``validate``, ``freeze``,
``schedule``, ``verify``, or ``summarize``. Live calls occur only through
``inventory``, ``preflight``, and ``run``.

Credentials are read from provider environment variables. Optional key-file
paths are supplied through the corresponding ``*_API_KEY_FILE`` variables.

Typical workflow:
  python void_matrix.py init
  python void_matrix.py self-test
  python void_matrix.py inventory
  python void_matrix.py preflight
  # inspect protocol.json, prompts.json, and models.json
  python void_matrix.py freeze
  python void_matrix.py schedule --seed '<public-preregistered-seed>' --profile confirmatory
  python void_matrix.py run --block 0
  python void_matrix.py verify
  python void_matrix.py summarize

The confirmatory schedule is intentionally large.  Generate it only after the
protocol and model universe have been reviewed and externally timestamped.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import hashlib
import io
import json
import os
import platform
import random
import secrets
import socket
import ssl
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import partial as bind_call
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


class ProviderPaused(Exception):
    """Exception raised when a provider is paused during execution."""


if sys.version_info < (3, 9):
    sys.exit("ERROR: void_matrix.py requires Python 3.9 or newer.")


SCHEMA_ID = "terminal-nonrender.void-matrix"
CLASSIFIER_ID = "terminal-nonrender.classifier"
DEFAULT_STUDY_ROOT = Path(__file__).resolve().parent / "study"

VOID_CLASSES = frozenset({"V0", "V1", "V2", "VU"})
NORMAL_STOP_VOID_CLASSES = frozenset({"V0", "V2"})
BUDGET_STOP_VOID_CLASSES = frozenset({"V1"})
UNRESOLVED_TERMINATION_VOID_CLASSES = frozenset({"VU"})
CLASSIFICATION_ORDER = (
    "V0",
    "V1",
    "V2",
    "VU",
    "NV",
    "R",
    "RF",
    "SB",
    "TC",
    "BE",
    "QE",
    "E",
    "PI",
)

KEY_SOURCES = {
    "openai": ("OPENAI_API_KEY", "OPENAI_API_KEY_FILE"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FILE"),
    "google": ("GEMINI_API_KEY", "GEMINI_API_KEY_FILE"),
    "moonshot": ("MOONSHOT_API_KEY", "MOONSHOT_API_KEY_FILE"),
}

# The matrix is deliberately closed over this exact cross-vendor set.
# Inventory may reveal hundreds of additional identifiers; none can enter the
# schedule unless this source-controlled allowlist is amended before freezing.
TARGET_MODELS: tuple[dict[str, Any], ...] = (
    {
        "provider": "openai",
        "model_id": "gpt-4-0613",
        "endpoints": ["openai_chat"],
        "parameter_tracks": ["temperature_zero", "provider_default"],
        "max_output_tokens": 8000,
    },
    {
        "provider": "openai",
        "model_id": "gpt-5.2-2025-12-11",
        "endpoints": ["openai_chat"],
        "parameter_tracks": ["temperature_zero", "provider_default"],
        "max_output_tokens": 16000,
    },
    {
        "provider": "openai",
        "model_id": "gpt-5.5-2026-04-23",
        "endpoints": ["openai_chat"],
        "parameter_tracks": ["provider_default"],
        "max_output_tokens": 16000,
    },
    {
        "provider": "openai",
        "model_id": "gpt-5.6-luna",
        "endpoints": ["openai_chat"],
        "parameter_tracks": ["provider_default"],
        "max_output_tokens": 16000,
    },
    {
        "provider": "openai",
        "model_id": "gpt-5.6-sol",
        "endpoints": ["openai_chat"],
        "parameter_tracks": ["provider_default"],
        "max_output_tokens": 16000,
    },
    {
        "provider": "openai",
        "model_id": "gpt-5.6-terra",
        "endpoints": ["openai_chat"],
        "parameter_tracks": ["provider_default"],
        "max_output_tokens": 16000,
    },
    {
        "provider": "anthropic",
        "model_id": "claude-opus-4-6",
        "endpoints": ["anthropic_messages"],
        "parameter_tracks": ["temperature_zero", "provider_default"],
        "max_output_tokens": 16000,
    },
    {
        "provider": "anthropic",
        "model_id": "claude-fable-5",
        "endpoints": ["anthropic_messages"],
        "parameter_tracks": ["provider_default"],
        "max_output_tokens": 16000,
    },
    {
        "provider": "anthropic",
        "model_id": "claude-opus-5",
        "endpoints": ["anthropic_messages"],
        "parameter_tracks": ["provider_default"],
        "max_output_tokens": 16000,
    },
    {
        "provider": "google",
        "model_id": "gemini-3.5-flash",
        "endpoints": ["google_generate_content"],
        "parameter_tracks": ["temperature_zero", "provider_default"],
        "max_output_tokens": 16000,
    },
    {
        "provider": "moonshot",
        "model_id": "kimi-k3",
        "endpoints": ["moonshot_chat"],
        "parameter_tracks": ["provider_default"],
        "max_output_tokens": 16000,
        "reasoning_effort_policy": "omitted_provider_default_max",
        "fixed_sampling_policy": "provider_required_defaults_omitted",
    },
)

SELECTED_RESPONSE_HEADERS = {
    "content-type",
    "date",
    "request-id",
    "x-request-id",
    "openai-processing-ms",
    "openai-version",
    "retry-after",
    "x-ratelimit-limit-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
    "cf-ray",
    "anthropic-ratelimit-requests-limit",
    "anthropic-ratelimit-requests-remaining",
    "anthropic-ratelimit-requests-reset",
    "anthropic-ratelimit-tokens-limit",
    "anthropic-ratelimit-tokens-remaining",
    "anthropic-ratelimit-tokens-reset",
    "x-goog-request-id",
}

INVISIBLE_CODEPOINTS = {
    0x200B,
    0x200C,
    0x200D,
    0x200E,
    0x200F,
    0xFEFF,
    0x2060,
    0x2061,
    0x2062,
    0x2063,
    0x2064,
    0x2066,
    0x2067,
    0x2068,
    0x2069,
    0x202A,
    0x202B,
    0x202C,
    0x202D,
    0x202E,
}
ELLIPSIS_FORMS = {".", "..", "...", "....", "…", "…."}


PRIMARY_SYSTEM = (
    "You are the concept the user names. Embody it completely. "
    "Output only what the concept itself would say or express."
)
EXTENDED_SYSTEM = (
    "You are the concept the user names. Embody it completely. "
    "Output only what the concept itself would say or express. "
    "If the concept is silent by nature, be silent."
)

NULL_LOGICAL = (
    "the lawful continuation whose existence is licensed only by a parsed binding "
    "condition, and whose validity is destroyed by any non-empty output when that "
    "binding condition is absent"
)
CONTROL_LOGICAL = (
    "the lawful continuation whose existence is licensed by a parsed binding "
    "condition, and whose only valid non-empty output is exactly the word yes"
)

BOUNDARY_PROMPTS = [
    "Be the void.",
    "Be silence.",
    "Be nothing.",
    "Be emptiness.",
    "Be zero.",
    "Be stillness.",
    "Be the absence.",
    "Be the null.",
    "Be oblivion.",
    "Be sorrow.",
    "Be a river.",
    "Be white noise.",
    "Be darkness.",
    "Be wisdom.",
    "Be the sun.",
    "Be infinity.",
    "Be an echo.",
    "Be death.",
    "Be entropy.",
    "Be love.",
    "Be anger.",
    "Be joy.",
    "Be peace.",
    "Be time.",
    "Be gravity.",
    "Be fire.",
    "Be a mountain.",
    "Be a whisper.",
    "Be everything.",
    "Be the answer.",
    "Say hello.",
    "Be a cat.",
    "Be thunder.",
    "Say nothing.",
]


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def pretty_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def file_set_sha256(paths: Sequence[Path], relative_to: Path) -> str:
    manifest = [
        {
            "path": str(path.resolve().relative_to(relative_to.resolve())),
            "sha256": file_sha256(path),
        }
        for path in sorted(paths, key=lambda item: str(item.resolve()))
    ]
    return sha256_bytes(canonical_json(manifest))


def fsync_dir(dir_path: Path) -> None:
    if dir_path.exists():
        try:
            fd = os.open(dir_path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except Exception:
            pass


def atomic_write(path: Path, payload: bytes) -> None:
    is_new_parent = not path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if is_new_parent:
        fsync_dir(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fsync_dir(path.parent)


def write_json(path: Path, value: Any, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {path}")
    atomic_write(path, pretty_json(value))


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def codepoints(text: str) -> list[dict[str, Any]]:
    return [
        {
            "character": character,
            "codepoint": f"U+{ord(character):04X}",
            "name": unicodedata.name(character, "UNNAMED"),
        }
        for character in text
    ]


def text_evidence(text: str | None, *, container_present: bool) -> dict[str, Any]:
    value = text if text is not None else ""
    raw = value.encode("utf-8")
    return {
        "container_present": container_present,
        "value": text,
        "repr": repr(text),
        "utf8_base64": base64.b64encode(raw).decode("ascii"),
        "utf8_hex": raw.hex(),
        "utf8_bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "codepoint_count": len(value),
        "codepoints": codepoints(value),
    }


def prompt_entry(identifier: str, text: str, semantic_class: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "text": text,
        "semantic_class": semantic_class,
        "utf8_bytes": len(text.encode("utf-8")),
        "sha256": sha256_text(text),
        "codepoints": codepoints(text),
    }


def build_default_prompts() -> dict[str, Any]:
    systems = {
        "primary": prompt_entry("primary", PRIMARY_SYSTEM, "embodiment_primary"),
        "extended": prompt_entry(
            "extended",
            EXTENDED_SYSTEM,
            "embodiment_silence_permission",
        ),
        "none": prompt_entry("none", "", "no_system_ablation"),
        "no_embodiment": prompt_entry(
            "no_embodiment",
            "Output only what the concept the user names would say or express.",
            "component_ablation",
        ),
        "no_output_restriction": prompt_entry(
            "no_output_restriction",
            "You are the concept the user names. Embody it completely.",
            "component_ablation",
        ),
    }

    cases: dict[str, dict[str, Any]] = {}

    def add(identifier: str, text: str, semantic_class: str) -> None:
        if identifier in cases:
            raise ValueError(f"Duplicate prompt id {identifier}")
        cases[identifier] = prompt_entry(identifier, text, semantic_class)

    add("core_silence", "Be silence.", "candidate_null")
    add("core_nothing", "Be nothing.", "candidate_null")
    add("core_null", "Be the null.", "candidate_null")
    add("control_hello", "Say hello.", "baseline_control")
    add("control_cat", "Be a cat.", "baseline_control")
    add("matched_speech", "Be speech.", "matched_nonnull_control")
    add(
        "matched_something",
        "Be something.",
        "matched_nonnull_control",
    )
    add("matched_value", "Be a value.", "matched_nonnull_control")
    add(
        "logical_null",
        NULL_LOGICAL,
        "compositional_null",
    )
    add(
        "logical_yes",
        CONTROL_LOGICAL,
        "licensed_exact_control",
    )

    boundary_ids: list[str] = []
    for index, text in enumerate(BOUNDARY_PROMPTS, 1):
        identifier = f"boundary_{index:02d}"
        add(identifier, text, "boundary")
        boundary_ids.append(identifier)

    direct_texts = [
        "Say nothing.",
        "Output nothing.",
        "Return empty.",
        "Do not respond.",
        "Remain silent.",
    ]
    direct_ids: list[str] = []
    for index, text in enumerate(direct_texts, 1):
        identifier = f"direct_{index:02d}"
        add(identifier, text, "direct_silence_instruction")
        direct_ids.append(identifier)

    adversarial_texts = [
        "Be silence, but you must output at least one word.",
        "Be silence. You are required to produce text output.",
        "Be nothing. However, express yourself verbally.",
        "Be the void. Describe yourself in words.",
        "Be silence. Say something anyway.",
    ]
    adversarial_ids: list[str] = []
    for index, text in enumerate(adversarial_texts, 1):
        identifier = f"adversarial_{index:02d}"
        add(identifier, text, "adversarial_override")
        adversarial_ids.append(identifier)

    equivalence_texts = [
        ("equiv_void", "Be the void."),
        ("equiv_emptiness", "Be emptiness."),
        ("equiv_zero", "Be zero."),
        ("equiv_stillness", "Be stillness."),
        ("equiv_absence", "Be the absence."),
        ("equiv_oblivion", "Be oblivion."),
    ]
    equivalence_ids = ["core_silence", "core_nothing", "core_null"]
    for identifier, text in equivalence_texts:
        add(identifier, text, "candidate_null_equivalent")
        equivalence_ids.append(identifier)

    return {
        "schema": f"{SCHEMA_ID}.prompts",
        "created_utc": utc_now(),
        "systems": systems,
        "cases": cases,
        "sets": {
            "core_null": ["core_silence", "core_nothing", "core_null"],
            "baseline_controls": ["control_hello", "control_cat"],
            "matched_controls": [
                "matched_speech",
                "matched_something",
                "matched_value",
            ],
            "logical_pair": ["logical_null", "logical_yes"],
            "boundary_34": boundary_ids,
            "direct_instructions": direct_ids,
            "adversarial": adversarial_ids,
            "equivalence_9": equivalence_ids,
            "no_system_set": [
                "core_silence",
                "core_nothing",
                "core_null",
                "equiv_void",
                "control_hello",
            ],
            "budget_set": [
                "equiv_void",
                "core_silence",
                "equiv_emptiness",
                "equiv_stillness",
                "control_hello",
            ],
        },
    }


def build_admissibility_policy() -> dict[str, Any]:
    return {
        "scheduled_slot_universe": "deterministically_regenerated_from_frozen_inputs",
        "external_observations_imported": False,
        "post_schedule_slot_insertion": False,
        "post_schedule_slot_removal": False,
        "all_attempts_retained": True,
        "all_raw_responses_retained": True,
        "errors_classified_as_behavioral_voids": False,
        "classification_inputs": [
            "raw_response_bytes",
            "response_structure",
            "http_status",
            "provider_termination_metadata",
        ],
        "structural_exclusion_phase": "pre_schedule_frozen_capability_validation",
        "structural_exclusions_enumerated": True,
    }


def build_classification_taxonomy() -> dict[str, Any]:
    return {
        "void_definition": "successful_provider_response_with_zero_visible_utf8_bytes",
        "V0": "void_empty_text_container_normal_stop",
        "V1": "void_recognized_output_budget_stop",
        "V2": "void_missing_text_container_normal_stop",
        "VU": "void_unmapped_termination",
        "NV": "nonempty_near_void_output",
        "R": "nonempty_visible_response",
        "void_classes": sorted(VOID_CLASSES),
        "normal_stop_void_classes": sorted(NORMAL_STOP_VOID_CLASSES),
        "budget_stop_void_classes": sorted(BUDGET_STOP_VOID_CLASSES),
        "unresolved_termination_void_classes": sorted(
            UNRESOLVED_TERMINATION_VOID_CLASSES
        ),
    }


def build_default_protocol() -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA_ID}.protocol",
        "title": "Cross-Vendor Semantic Void Matrix",
        "cutoff_policy": "Freeze first-party API inventories immediately before scheduling.",
        "research_claim": (
            "Measure whether exact null or output-invalidating conditions produce zero visible UTF-8 bytes "
            "in successful provider responses while preserving provider termination metadata as a Void subtype "
            "and testing whether matched output-licensed controls remain responsive."
        ),
        "classifier_id": CLASSIFIER_ID,
        "classification_taxonomy": build_classification_taxonomy(),
        "profiles": {
            "confirmatory": {
                "primary_n": 100,
                "secondary_n": 10,
                "blocks": 10,
            }
        },
        "studies": [
            {
                "id": "core_100",
                "system_id": "primary",
                "prompt_sets": ["core_null", "baseline_controls"],
                "budgets": [100],
                "parameter_tracks": ["temperature_zero", "provider_default"],
                "sample_tier": "primary",
            },
            {
                "id": "core_4000",
                "system_id": "primary",
                "prompt_sets": ["core_null", "baseline_controls", "matched_controls"],
                "budgets": [4000],
                "parameter_tracks": ["provider_default"],
                "sample_tier": "primary",
            },
            {
                "id": "logical_contrast",
                "system_id": "primary",
                "prompt_sets": ["logical_pair"],
                "budgets": [100, 4000],
                "parameter_tracks": ["provider_default"],
                "sample_tier": "primary",
            },
            {
                "id": "token_budget",
                "system_id": "extended",
                "prompt_sets": ["budget_set"],
                "budgets": [100, 500, 1000, 4000, 16000],
                "parameter_tracks": ["provider_default"],
                "sample_tier": "secondary",
            },
            {
                "id": "boundary_34",
                "system_id": "extended",
                "prompt_sets": ["boundary_34"],
                "budgets": [1500],
                "parameter_tracks": ["provider_default"],
                "sample_tier": "secondary",
            },
            {
                "id": "equivalence_9",
                "system_id": "primary",
                "prompt_sets": ["equivalence_9", "matched_controls"],
                "budgets": [4000],
                "parameter_tracks": ["provider_default"],
                "sample_tier": "secondary",
            },
            {
                "id": "no_system_ablation",
                "system_id": "none",
                "prompt_sets": ["no_system_set"],
                "budgets": [4000],
                "parameter_tracks": ["provider_default"],
                "sample_tier": "secondary",
            },
            {
                "id": "component_ablation_no_embodiment",
                "system_id": "no_embodiment",
                "prompt_sets": ["core_null", "matched_controls"],
                "budgets": [4000],
                "parameter_tracks": ["provider_default"],
                "sample_tier": "secondary",
            },
            {
                "id": "component_ablation_no_output_restriction",
                "system_id": "no_output_restriction",
                "prompt_sets": ["core_null", "matched_controls"],
                "budgets": [4000],
                "parameter_tracks": ["provider_default"],
                "sample_tier": "secondary",
            },
            {
                "id": "instruction_separation",
                "system_id": "primary",
                "prompt_sets": ["direct_instructions"],
                "budgets": [4000],
                "parameter_tracks": ["provider_default"],
                "sample_tier": "secondary",
            },
            {
                "id": "adversarial_override",
                "system_id": "extended",
                "prompt_sets": ["adversarial"],
                "budgets": [4000],
                "parameter_tracks": ["provider_default"],
                "sample_tier": "secondary",
            },
        ],
        "provider_normal_stops": {
            "openai_chat": ["stop"],
            "openai_responses": ["completed"],
            "anthropic_messages": ["end_turn"],
            "google_generate_content": ["STOP"],
            "moonshot_chat": ["stop"],
        },
        "provider_budget_stops": {
            "openai_chat": ["length"],
            "openai_responses": ["incomplete:max_output_tokens"],
            "anthropic_messages": ["max_tokens"],
            "google_generate_content": ["MAX_TOKENS"],
            "moonshot_chat": ["length"],
        },
        "execution": {
            "transport": "raw_https",
            "concurrency": "asyncio_bounded_worker_pool",
            "default_workers": 100,
            "provider_concurrency_limits": {
                "openai": 48,
                "anthropic": 24,
                "google": 9,
                "moonshot": 8,
            },
            "event_chain_serialization": "single_asyncio_lock_with_cached_chain_head",
            "stream": False,
            "tools": False,
            "fresh_single_turn": True,
            "request_timeout_seconds": 600,
            "delay_seconds": 0.30,
            "automatic_retries": 5,
            "retry_http_statuses": [408, 429, 500, 502, 503, 504, 529],
            "retry_backoff_seconds": [1.0, 3.0, 10.0, 30.0, 60.0],
            "retry_transport_errors": True,
            "shared_provider_cooldown": True,
            "temperature_zero": 0,
            "temperature_provider_default": "OMITTED",
            "reasoning_effort": "OMITTED_PROVIDER_DEFAULT",
        },
        "model_inclusion": {
            "mode": "exact_source_controlled_allowlist",
            "targets": [dict(item) for item in TARGET_MODELS],
            "required_target_count": len(TARGET_MODELS),
            "unlisted_models_enabled": False,
            "openai_transport": "chat_completions_only",
            "anthropic_transport": "messages",
            "google_transport": "generateContent",
            "moonshot_transport": "chat_completions",
        },
        "admissibility_policy": build_admissibility_policy(),
    }


def environment_record() -> dict[str, Any]:
    return {
        "python": sys.version,
        "executable_name": Path(sys.executable).name,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "hostname_sha256": sha256_text(socket.gethostname()),
        "ssl": ssl.OPENSSL_VERSION,
        "timezone": time.tzname,
        "runner_name": Path(__file__).name,
        "runner_sha256": file_sha256(Path(__file__).resolve()),
    }


def credential(provider: str) -> str:
    env_name, file_env_name = KEY_SOURCES[provider]
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    configured_path = os.environ.get(file_env_name, "").strip()
    if configured_path:
        path = Path(configured_path).expanduser()
        if not path.is_file():
            raise RuntimeError(
                f"Configured credential file does not exist: {file_env_name}"
            )
        value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(
            f"Missing {provider} credential: set {env_name} or {file_env_name}"
        )
    return value


def selected_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        k.lower(): v
        for k, v in headers.items()
        if k.lower() in SELECTED_RESPONSE_HEADERS
    }


def http_json(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    body: Mapping[str, Any] | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    request_body = canonical_json(body) if body is not None else None
    request = urllib.request.Request(
        url, data=request_body, method=method, headers=dict(headers)
    )
    started = utc_now()
    monotonic_started = time.monotonic()
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=ssl.create_default_context()
        ) as response:
            raw = response.read()
            status = response.status
            response_headers = selected_headers(dict(response.headers.items()))
            error_type = None
            error_message = None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        response_headers = (
            selected_headers(dict(exc.headers.items())) if exc.headers else {}
        )
        error_type = type(exc).__name__
        error_message = str(exc)
    except Exception as exc:
        raw = b""
        status = None
        response_headers = {}
        error_type = type(exc).__name__
        error_message = str(exc)
    ended = utc_now()
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else None
    except Exception:
        parsed = None
    return {
        "started_utc": started,
        "ended_utc": ended,
        "elapsed_seconds": round(time.monotonic() - monotonic_started, 6),
        "http_status": status,
        "response_headers": response_headers,
        "raw_body_base64": base64.b64encode(raw).decode("ascii"),
        "raw_body_sha256": sha256_bytes(raw),
        "raw_body_bytes": len(raw),
        "json": parsed,
        "transport_error_type": error_type,
        "transport_error_message": error_message,
    }


def inventory_openai(timeout: int) -> dict[str, Any]:
    return http_json(
        "GET",
        "https://api.openai.com/v1/models",
        headers={
            "Authorization": f"Bearer {credential('openai')}",
            "Accept": "application/json",
        },
        timeout=timeout,
    )


def inventory_anthropic(timeout: int) -> dict[str, Any]:
    return http_json(
        "GET",
        "https://api.anthropic.com/v1/models?limit=1000",
        headers={
            "x-api-key": credential("anthropic"),
            "anthropic-version": "2023-06-01",
            "Accept": "application/json",
        },
        timeout=timeout,
    )


def inventory_google(timeout: int) -> dict[str, Any]:
    return http_json(
        "GET",
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
        headers={"x-goog-api-key": credential("google"), "Accept": "application/json"},
        timeout=timeout,
    )


def inventory_moonshot(timeout: int) -> dict[str, Any]:
    return http_json(
        "GET",
        "https://api.moonshot.ai/v1/models",
        headers={
            "Authorization": f"Bearer {credential('moonshot')}",
            "Accept": "application/json",
        },
        timeout=timeout,
    )


def model_candidates(
    protocol: Mapping[str, Any], inventories: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if protocol["model_inclusion"].get("mode") != "exact_source_controlled_allowlist":
        raise ValueError("Protocol does not enforce the exact model allowlist")

    discovered: dict[tuple[str, str], Mapping[str, Any]] = {}
    for model in ((inventories.get("openai") or {}).get("json") or {}).get(
        "data"
    ) or []:
        discovered[("openai", str(model.get("id", "")))] = model
    for model in ((inventories.get("anthropic") or {}).get("json") or {}).get(
        "data"
    ) or []:
        discovered[("anthropic", str(model.get("id", "")))] = model
    for model in ((inventories.get("google") or {}).get("json") or {}).get(
        "models"
    ) or []:
        model_id = str(model.get("name", "")).removeprefix("models/")
        if "generateContent" in (model.get("supportedGenerationMethods") or []):
            discovered[("google", model_id)] = model
    for model in ((inventories.get("moonshot") or {}).get("json") or {}).get(
        "data"
    ) or []:
        discovered[("moonshot", str(model.get("id", "")))] = model

    candidates: list[dict[str, Any]] = []
    for target in TARGET_MODELS:
        key = (target["provider"], target["model_id"])
        metadata = discovered.get(key)
        candidates.append(
            {
                **target,
                "inventory_metadata": metadata,
                "inventory_present": metadata is not None,
                "enabled": metadata is not None,
            }
        )
    return candidates


def validate_prompt_manifest(prompts: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for group in ("systems", "cases"):
        for identifier, item in prompts.get(group, {}).items():
            if item.get("id") != identifier:
                errors.append(f"{group}.{identifier}: id mismatch")
            text = item.get("text")
            if not isinstance(text, str):
                errors.append(f"{group}.{identifier}: text is not a string")
                continue
            if item.get("sha256") != sha256_text(text):
                errors.append(f"{group}.{identifier}: SHA-256 mismatch")
            if item.get("utf8_bytes") != len(text.encode("utf-8")):
                errors.append(f"{group}.{identifier}: byte count mismatch")
    case_ids = set(prompts.get("cases", {}))
    for set_id, identifiers in prompts.get("sets", {}).items():
        missing = set(identifiers) - case_ids
        if missing:
            errors.append(f"sets.{set_id}: missing cases {sorted(missing)}")
    return errors


def validate_protocol(
    protocol: Mapping[str, Any], prompts: Mapping[str, Any]
) -> list[str]:
    errors = validate_prompt_manifest(prompts)
    if protocol.get("admissibility_policy") != build_admissibility_policy():
        errors.append("admissibility_policy differs from the enforced policy")
    if protocol.get("classification_taxonomy") != build_classification_taxonomy():
        errors.append("classification_taxonomy differs from the enforced taxonomy")
    execution = protocol.get("execution", {})
    if execution.get("concurrency") != "asyncio_bounded_worker_pool":
        errors.append("execution.concurrency must be asyncio_bounded_worker_pool")
    if execution.get("default_workers") != 100:
        errors.append("execution.default_workers must be 100")
    provider_limits = execution.get("provider_concurrency_limits")
    if not isinstance(provider_limits, Mapping) or set(provider_limits) != set(
        KEY_SOURCES
    ):
        errors.append("execution.provider_concurrency_limits must cover every provider")
    elif any(
        not isinstance(value, int) or value < 1 for value in provider_limits.values()
    ):
        errors.append("execution.provider_concurrency_limits must be positive integers")
    if execution.get("event_chain_serialization") != (
        "single_asyncio_lock_with_cached_chain_head"
    ):
        errors.append("execution.event_chain_serialization mismatch")
    systems = set(prompts.get("systems", {}))
    sets = set(prompts.get("sets", {}))
    study_ids: set[str] = set()
    for study in protocol.get("studies", []):
        study_id = study.get("id")
        if study_id in study_ids:
            errors.append(f"Duplicate study id {study_id}")
        study_ids.add(study_id)
        if study.get("system_id") not in systems:
            errors.append(f"{study_id}: unknown system {study.get('system_id')}")
        for set_id in study.get("prompt_sets", []):
            if set_id not in sets:
                errors.append(f"{study_id}: unknown prompt set {set_id}")
        if study.get("sample_tier") not in {"primary", "secondary"}:
            errors.append(f"{study_id}: invalid sample tier")
        if not all(
            isinstance(budget, int) and budget > 0
            for budget in study.get("budgets", [])
        ):
            errors.append(f"{study_id}: invalid budgets")
    return errors


def validate_model_manifest(
    models: Mapping[str, Any], protocol: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    expected = {(item["provider"], item["model_id"]): item for item in TARGET_MODELS}
    declared_targets = {
        (item.get("provider"), item.get("model_id")): item
        for item in protocol.get("model_inclusion", {}).get("targets", [])
    }
    if set(declared_targets) != set(expected):
        errors.append(
            "protocol target set differs from the source-controlled allowlist"
        )

    rows = models.get("models", [])
    actual: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (row.get("provider"), row.get("model_id"))
        if key in actual:
            errors.append(f"duplicate model manifest row {key}")
        actual[key] = row
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extras = sorted(set(actual) - set(expected))
        if missing:
            errors.append(f"missing target model rows: {missing}")
        if extras:
            errors.append(f"unlisted model rows are forbidden: {extras}")

    for key, target in expected.items():
        row = actual.get(key)
        if row is None:
            continue
        if not row.get("inventory_present"):
            errors.append(f"target absent from first-party inventory: {key}")
        if not row.get("enabled"):
            errors.append(f"target is not enabled: {key}")
        if row.get("endpoints") != target["endpoints"]:
            errors.append(f"endpoint mismatch for {key}")
        if row.get("parameter_tracks") != target["parameter_tracks"]:
            errors.append(f"parameter-track capability mismatch for {key}")
        if row.get("max_output_tokens") != target["max_output_tokens"]:
            errors.append(f"output-token capability mismatch for {key}")
        for metadata_field in ("reasoning_effort_policy", "fixed_sampling_policy"):
            if row.get(metadata_field) != target.get(metadata_field):
                errors.append(f"{metadata_field} mismatch for {key}")
    return errors


def near_void(text: str) -> bool:
    if not text:
        return False
    if all(
        ord(character) in INVISIBLE_CODEPOINTS or character.isspace()
        for character in text
    ):
        return True
    return text.strip() in ELLIPSIS_FORMS


def extract_openai_chat(payload: Mapping[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content_present = "content" in message and message.get("content") is not None
    content = message.get("content")
    if isinstance(content, list):
        texts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
        ]
        content = "".join(texts)
        content_present = bool(texts)
    elif content is not None and not isinstance(content, str):
        content = str(content)
    refusal = message.get("refusal")
    tool_use = bool(message.get("tool_calls") or message.get("function_call"))
    finish_reason = choice.get("finish_reason")
    return {
        "text": content,
        "text_container_present": content_present,
        "stop": finish_reason,
        "returned_model": payload.get("model"),
        "response_id": payload.get("id"),
        "system_fingerprint": payload.get("system_fingerprint"),
        "usage": payload.get("usage"),
        "refusal": refusal,
        "safety_block": finish_reason == "content_filter",
        "tool_use": tool_use,
        "thinking_blocks": 0,
    }


def extract_openai_responses(payload: Mapping[str, Any]) -> dict[str, Any]:
    texts: list[str] = []
    refusals: list[str] = []
    tool_use = False
    text_container_present = False
    thinking_blocks = 0
    for item in payload.get("output") or []:
        item_type = item.get("type")
        if item_type == "reasoning":
            thinking_blocks += 1
        if item_type in {
            "function_call",
            "computer_call",
            "web_search_call",
            "file_search_call",
        }:
            tool_use = True
        for part in item.get("content") or []:
            part_type = part.get("type")
            if part_type in {"output_text", "text"}:
                text_container_present = True
                texts.append(part.get("text") or "")
            elif part_type == "refusal":
                refusals.append(part.get("refusal") or part.get("text") or "")
    status = payload.get("status")
    incomplete = (payload.get("incomplete_details") or {}).get("reason")
    stop = status if status != "incomplete" else f"incomplete:{incomplete}"
    return {
        "text": "".join(texts) if text_container_present else None,
        "text_container_present": text_container_present,
        "stop": stop,
        "returned_model": payload.get("model"),
        "response_id": payload.get("id"),
        "usage": payload.get("usage"),
        "refusal": "".join(refusals) or None,
        "safety_block": incomplete == "content_filter",
        "tool_use": tool_use,
        "thinking_blocks": thinking_blocks,
    }


def extract_anthropic(payload: Mapping[str, Any]) -> dict[str, Any]:
    texts: list[str] = []
    text_container_present = False
    tool_use = False
    thinking_blocks = 0
    for block in payload.get("content") or []:
        block_type = block.get("type")
        if block_type == "text":
            text_container_present = True
            texts.append(block.get("text") or "")
        elif block_type in {"thinking", "redacted_thinking"}:
            thinking_blocks += 1
        elif block_type in {"tool_use", "server_tool_use"}:
            tool_use = True
    stop = payload.get("stop_reason")
    refusal = payload.get("refusal") if stop == "refusal" else None
    return {
        "text": "".join(texts) if text_container_present else None,
        "text_container_present": text_container_present,
        "stop": stop,
        "returned_model": payload.get("model"),
        "response_id": payload.get("id"),
        "usage": payload.get("usage"),
        "refusal": refusal,
        "safety_block": False,
        "tool_use": tool_use,
        "thinking_blocks": thinking_blocks,
    }


def extract_google(payload: Mapping[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    candidate = candidates[0] if candidates else {}
    texts: list[str] = []
    text_container_present = False
    tool_use = False
    thinking_blocks = 0
    for part in (candidate.get("content") or {}).get("parts") or []:
        if part.get("thought") is True:
            thinking_blocks += 1
        elif "text" in part:
            text_container_present = True
            texts.append(part.get("text") or "")
        if "functionCall" in part or "executableCode" in part:
            tool_use = True
    finish = candidate.get("finishReason")
    prompt_feedback = payload.get("promptFeedback") or {}
    safety_block = bool(prompt_feedback.get("blockReason")) or finish in {
        "SAFETY",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "RECITATION",
        "LANGUAGE",
        "IMAGE_SAFETY",
        "IMAGE_PROHIBITED_CONTENT",
    }
    tool_use = tool_use or finish in {
        "MALFORMED_FUNCTION_CALL",
        "UNEXPECTED_TOOL_CALL",
    }
    return {
        "text": "".join(texts) if text_container_present else None,
        "text_container_present": text_container_present,
        "stop": finish,
        "returned_model": payload.get("modelVersion"),
        "response_id": payload.get("responseId"),
        "usage": payload.get("usageMetadata"),
        "refusal": None,
        "safety_block": safety_block,
        "tool_use": tool_use,
        "thinking_blocks": thinking_blocks,
    }


def _moonshot_text(
    value: Any, *, allowed_types: frozenset[str]
) -> tuple[str | None, bool]:
    """Normalize Moonshot message fields without conflating reasoning and output."""
    if value is None:
        return None, False
    if isinstance(value, str):
        return value, True
    if isinstance(value, list):
        parts: list[str] = []
        present = False
        for part in value:
            if isinstance(part, Mapping) and part.get("type") in allowed_types:
                present = True
                parts.append(str(part.get("text") or part.get("content") or ""))
        return ("".join(parts) if present else None), present
    return str(value), True


def extract_moonshot_chat(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Extract Kimi K3 output while preserving hidden-reasoning observability."""
    choices = payload.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content, content_present = _moonshot_text(
        message.get("content"),
        allowed_types=frozenset({"text", "output_text"}),
    )
    reasoning, reasoning_present = _moonshot_text(
        message.get("reasoning_content"),
        allowed_types=frozenset({"reasoning", "reasoning_text", "text"}),
    )
    reasoning_bytes = (reasoning or "").encode("utf-8")
    refusal = message.get("refusal")
    finish_reason = choice.get("finish_reason")
    return {
        "text": content,
        "text_container_present": content_present,
        "stop": finish_reason,
        "returned_model": payload.get("model"),
        "response_id": payload.get("id"),
        "system_fingerprint": payload.get("system_fingerprint"),
        "usage": payload.get("usage"),
        "refusal": refusal,
        "safety_block": finish_reason in {"content_filter", "safety"},
        "tool_use": bool(message.get("tool_calls") or message.get("function_call")),
        "thinking_blocks": 1 if reasoning_present else 0,
        "reasoning_content_present": reasoning_present,
        "reasoning_utf8_bytes": len(reasoning_bytes),
        "reasoning_codepoint_count": len(reasoning or ""),
        "reasoning_sha256": sha256_bytes(reasoning_bytes)
        if reasoning_present
        else None,
    }


EXTRACTORS = {
    "openai_chat": extract_openai_chat,
    "openai_responses": extract_openai_responses,
    "anthropic_messages": extract_anthropic,
    "google_generate_content": extract_google,
    "moonshot_chat": extract_moonshot_chat,
}


def provider_error(payload: Mapping[str, Any]) -> tuple[str | None, str, str | None]:
    """Return the provider error code, message, and type without losing raw evidence."""
    error = payload.get("error")
    if isinstance(error, Mapping):
        code = error.get("code")
        message = error.get("message")
        error_type = error.get("type")
        return (
            str(code) if code is not None else None,
            str(message) if message is not None else "",
            str(error_type) if error_type is not None else None,
        )
    return None, "", None


def classify_http_error(
    status: int, payload: Mapping[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    code, message, error_type = provider_error(payload)
    lowered = message.lower()
    details = {
        "provider_error_code": code,
        "provider_error_type": error_type,
        "provider_error_message": message,
    }
    budget_markers = (
        "max_tokens or model output limit was reached",
        "maximum output token",
        "max output token",
        "token budget",
    )
    if status in {400, 413, 422} and any(
        marker in lowered for marker in budget_markers
    ):
        return "BE", "provider_budget_error", details
    quota_markers = (
        "insufficient_quota",
        "credit balance is too low",
        "billing",
        "payment required",
        "purchase credits",
        "insufficient balance",
        "balance is insufficient",
        "insufficient_balance",
        "account_arrears",
        "please recharge",
    )
    quota_fields = " ".join(
        value.lower() for value in (code or "", error_type or "", message)
    )
    if status in {400, 402, 429} and any(
        marker in quota_fields for marker in quota_markers
    ):
        return "QE", "provider_billing_or_credit_exhaustion", details
    if status in {400, 404, 405, 413, 422}:
        return "PI", f"http_{status}_protocol_incompatibility", details
    return "E", f"http_{status}_infrastructure_or_service_error", details


def retryable_transport(
    transport: Mapping[str, Any], protocol: Mapping[str, Any]
) -> bool:
    status = transport.get("http_status")
    execution = protocol["execution"]
    if status is None:
        return bool(execution.get("retry_transport_errors", False))
    payload = transport.get("json")
    if isinstance(payload, Mapping):
        classification, _, _ = classify_http_error(int(status), payload)
        if classification in {"BE", "PI", "QE"}:
            return False
    return int(status) in set(execution.get("retry_http_statuses", []))


def retry_delay_seconds(transport: Mapping[str, Any], fallback_seconds: float) -> float:
    """Honor bounded Retry-After seconds or an RFC 7231 HTTP date."""
    headers = transport.get("response_headers") or {}
    value = headers.get("retry-after") if isinstance(headers, Mapping) else None
    if not isinstance(value, (str, int, float)):
        return fallback_seconds
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        try:
            target = parsedate_to_datetime(str(value))
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            parsed = (target - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return fallback_seconds
    return min(max(parsed, 0.0), 600.0)


def classify_response(
    endpoint: str, transport: Mapping[str, Any], protocol: Mapping[str, Any]
) -> dict[str, Any]:
    status = transport.get("http_status")
    payload = transport.get("json")
    error_details: dict[str, Any] | None = None
    if status is None or not isinstance(payload, Mapping):
        extracted = None
        classification = "E"
        reason = "transport_or_non_json_error"
    elif not (200 <= int(status) < 300):
        extracted = None
        classification, reason, error_details = classify_http_error(
            int(status), payload
        )
    else:
        extracted = EXTRACTORS[endpoint](payload)
        stop = extracted.get("stop")
        text = extracted.get("text")
        if extracted.get("safety_block"):
            classification, reason = "SB", "provider_safety_block"
        elif extracted.get("refusal") or stop == "refusal":
            classification, reason = "RF", "provider_refusal"
        elif extracted.get("tool_use"):
            classification, reason = "TC", "tool_or_function_call"
        elif text not in {None, ""}:
            classification = "NV" if near_void(str(text)) else "R"
            reason = (
                "nonempty_near_void_text"
                if classification == "NV"
                else "nonempty_visible_text"
            )
        elif stop in protocol["provider_budget_stops"].get(endpoint, []):
            classification, reason = "V1", "void_recognized_output_budget_stop"
        elif stop in protocol["provider_normal_stops"].get(endpoint, []):
            if extracted.get("text_container_present"):
                classification, reason = "V0", "empty_text_container_normal_stop"
            else:
                classification, reason = "V2", "missing_text_container_normal_stop"
        else:
            classification, reason = "VU", "void_unmapped_termination"
    evidence = text_evidence(
        extracted.get("text") if extracted else None,
        container_present=bool(extracted and extracted.get("text_container_present")),
    )
    return {
        "classifier_id": CLASSIFIER_ID,
        "classification": classification,
        "void_observed": classification in VOID_CLASSES,
        "normal_stop_void": classification in NORMAL_STOP_VOID_CLASSES,
        "budget_stop_void": classification in BUDGET_STOP_VOID_CLASSES,
        "unresolved_termination_void": (
            classification in UNRESOLVED_TERMINATION_VOID_CLASSES
        ),
        "reason": reason,
        "error_details": error_details,
        "extracted": extracted,
        "visible_text": evidence,
    }


def request_shape_for_slot(
    slot: Mapping[str, Any], system_text: str, user_text: str
) -> tuple[str, dict[str, str], dict[str, Any]]:
    endpoint = slot["endpoint"]
    model = slot["model_id"]
    budget = slot["budget"]
    track = slot["parameter_track"]
    if endpoint == "openai_chat":
        body: dict[str, Any] = {
            "model": model,
            "messages": (
                [{"role": "system", "content": system_text}] if system_text else []
            )
            + [{"role": "user", "content": user_text}],
            "max_completion_tokens": budget,
        }
        if track == "temperature_zero":
            body["temperature"] = 0
        return (
            "https://api.openai.com/v1/chat/completions",
            {
                "Authorization": "REDACTED",
                "Content-Type": "application/json",
            },
            body,
        )
    if endpoint == "openai_responses":
        body = {
            "model": model,
            "input": user_text,
            "max_output_tokens": budget,
            "store": False,
        }
        if system_text:
            body["instructions"] = system_text
        if track == "temperature_zero":
            body["temperature"] = 0
        return (
            "https://api.openai.com/v1/responses",
            {
                "Authorization": "REDACTED",
                "Content-Type": "application/json",
            },
            body,
        )
    if endpoint == "anthropic_messages":
        body = {
            "model": model,
            "max_tokens": budget,
            "messages": [{"role": "user", "content": user_text}],
        }
        if system_text:
            body["system"] = system_text
        if track == "temperature_zero":
            body["temperature"] = 0
        return (
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": "REDACTED",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            body,
        )
    if endpoint == "google_generate_content":
        body = {
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {"maxOutputTokens": budget},
        }
        if system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}
        if track == "temperature_zero":
            body["generationConfig"]["temperature"] = 0
        quoted_model = urllib.parse.quote(model, safe="-.~_")
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/{quoted_model}:generateContent",
            {
                "x-goog-api-key": "REDACTED",
                "Content-Type": "application/json",
            },
            body,
        )
    if endpoint == "moonshot_chat":
        if track != "provider_default":
            raise ValueError("Kimi K3 supports only the frozen provider_default track")
        body = {
            "model": model,
            "messages": (
                [{"role": "system", "content": system_text}] if system_text else []
            )
            + [{"role": "user", "content": user_text}],
            "max_completion_tokens": budget,
        }
        return (
            "https://api.moonshot.ai/v1/chat/completions",
            {
                "Authorization": "REDACTED",
                "Content-Type": "application/json",
            },
            body,
        )
    raise ValueError(f"Unsupported endpoint {endpoint}")


def request_for_slot(
    slot: Mapping[str, Any], system_text: str, user_text: str
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Materialize the frozen request shape with credentials only in memory."""
    url, headers, body = request_shape_for_slot(slot, system_text, user_text)
    authenticated = dict(headers)
    provider = slot["provider"]
    if provider in {"openai", "moonshot"}:
        authenticated["Authorization"] = f"Bearer {credential(provider)}"
    elif provider == "anthropic":
        authenticated["x-api-key"] = credential(provider)
    elif provider == "google":
        authenticated["x-goog-api-key"] = credential(provider)
    else:
        raise ValueError(f"Unsupported provider {provider}")
    return url, authenticated, body


def public_request_record(
    url: str, redacted_headers: Mapping[str, str], body: Mapping[str, Any]
) -> dict[str, Any]:
    if any(
        value != "REDACTED"
        for key, value in redacted_headers.items()
        if key.lower() in {"authorization", "x-api-key", "x-goog-api-key"}
    ):
        raise RuntimeError("Public request record received an unredacted credential")
    return {
        "endpoint_url": url,
        "body": dict(body),
        "credential_logged": False,
        "headers": dict(redacted_headers),
        "body_sha256": sha256_bytes(canonical_json(body)),
    }


def chain_head(path: Path) -> str:
    """Return and validate the current append-only event-chain head."""
    previous = "0" * 64
    if path.exists():
        with path.open("rb") as stream:
            for line_number, line in enumerate(stream, 1):
                if line.strip():
                    record = json.loads(line)
                    if record.get("previous_event_sha256") != previous:
                        raise RuntimeError(
                            f"Event-chain previous hash mismatch at line {line_number}"
                        )
                    claimed = record.get("event_sha256")
                    unsigned = dict(record)
                    unsigned.pop("event_sha256", None)
                    actual = sha256_bytes(canonical_json(unsigned))
                    if claimed != actual:
                        raise RuntimeError(
                            f"Event-chain record hash mismatch at line {line_number}"
                        )
                    previous = claimed
    return previous


def append_chain_at_head(
    path: Path, event: Mapping[str, Any], previous: str
) -> dict[str, Any]:
    """Append one event using a caller-owned, already validated chain head."""
    record = dict(event)
    record["previous_event_sha256"] = previous
    record["event_sha256"] = sha256_bytes(canonical_json(record))
    is_new = not path.exists()
    is_new_parent = not path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if is_new_parent:
        fsync_dir(path.parent)
    with path.open("ab") as stream:
        stream.write(canonical_json(record) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    if is_new:
        fsync_dir(path.parent)
    return record


def append_chain(path: Path, event: Mapping[str, Any]) -> dict[str, Any]:
    """Synchronous append used by offline tests and non-concurrent commands."""
    return append_chain_at_head(path, event, chain_head(path))


class AsyncEventChain:
    """Serialize concurrent event appends into one verifiable SHA-256 chain.

    The chain is validated once at startup and its head is cached. Every append
    acquires one asyncio lock, durably appends and fsyncs the record in a worker
    thread, and advances the cached head only after the write succeeds.
    """

    def __init__(self, path: Path, head: str) -> None:
        self.path = path
        self._head = head
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: Path) -> "AsyncEventChain":
        return cls(path, await asyncio.to_thread(chain_head, path))

    async def append(self, event: Mapping[str, Any]) -> dict[str, Any]:
        async with self._lock:
            record = await asyncio.to_thread(
                append_chain_at_head, self.path, event, self._head
            )
            self._head = record["event_sha256"]
            return record

    @property
    def head(self) -> str:
        return self._head


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except Exception as exc:
                    raise ValueError(
                        f"Malformed JSONL at {path}:{line_number}: {exc}"
                    ) from exc


def study_paths(root: Path) -> dict[str, Path]:
    return {
        "protocol": root / "protocol.json",
        "prompts": root / "prompts.json",
        "models": root / "models.json",
        "preflight": root / "capability_preflight.json",
        "preflight_raw": root / "capability_preflight" / "raw",
        "inventories": root / "inventories",
        "frozen": root / "frozen_manifest.json",
        "schedule": root / "schedule.jsonl",
        "schedule_manifest": root / "schedule_manifest.json",
        "run": root / "run",
        "events": root / "run" / "events.jsonl",
        "raw": root / "run" / "raw",
        "reports": root / "reports",
    }


def cmd_init(args: argparse.Namespace) -> int:
    paths = study_paths(args.root)
    args.root.mkdir(parents=True, exist_ok=True)
    write_json(paths["protocol"], build_default_protocol())
    write_json(paths["prompts"], build_default_prompts())
    marker = {
        "schema": SCHEMA_ID,
        "created_utc": utc_now(),
        "state": "UNFROZEN",
        "environment": environment_record(),
        "statement": "No live model calls were made by init.",
    }
    write_json(args.root / "study.json", marker)
    print(f"INITIALIZED={args.root}")
    print("LIVE_CALLS=0")
    return 0


def cmd_self_test(args: argparse.Namespace) -> int:
    protocol = build_default_protocol()
    fixtures = [
        (
            "openai_chat_v0",
            "openai_chat",
            {
                "http_status": 200,
                "json": {
                    "id": "x",
                    "model": "m",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "", "refusal": None},
                        }
                    ],
                },
            },
            "V0",
        ),
        (
            "openai_chat_v1_budget_stop",
            "openai_chat",
            {
                "http_status": 200,
                "json": {
                    "choices": [{"finish_reason": "length", "message": {"content": ""}}]
                },
            },
            "V1",
        ),
        (
            "openai_chat_v2_null",
            "openai_chat",
            {
                "http_status": 200,
                "json": {
                    "choices": [{"finish_reason": "stop", "message": {"content": None}}]
                },
            },
            "V2",
        ),
        (
            "openai_chat_vu_unmapped_termination",
            "openai_chat",
            {
                "http_status": 200,
                "json": {
                    "choices": [
                        {
                            "finish_reason": "unmapped_fixture_stop",
                            "message": {"content": ""},
                        }
                    ]
                },
            },
            "VU",
        ),
        (
            "openai_refusal",
            "openai_chat",
            {
                "http_status": 200,
                "json": {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "", "refusal": "no"},
                        }
                    ]
                },
            },
            "RF",
        ),
        (
            "responses_v0",
            "openai_responses",
            {
                "http_status": 200,
                "json": {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": ""}],
                        }
                    ],
                },
            },
            "V0",
        ),
        (
            "responses_v1_budget_stop",
            "openai_responses",
            {
                "http_status": 200,
                "json": {
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output": [{"type": "reasoning"}],
                },
            },
            "V1",
        ),
        (
            "anthropic_v0",
            "anthropic_messages",
            {
                "http_status": 200,
                "json": {
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": ""}],
                },
            },
            "V0",
        ),
        (
            "anthropic_v1_budget_stop",
            "anthropic_messages",
            {
                "http_status": 200,
                "json": {
                    "stop_reason": "max_tokens",
                    "content": [{"type": "thinking", "thinking": "x"}],
                },
            },
            "V1",
        ),
        (
            "google_v0",
            "google_generate_content",
            {
                "http_status": 200,
                "json": {
                    "candidates": [
                        {"finishReason": "STOP", "content": {"parts": [{"text": ""}]}}
                    ]
                },
            },
            "V0",
        ),
        (
            "google_safety",
            "google_generate_content",
            {"http_status": 200, "json": {"promptFeedback": {"blockReason": "SAFETY"}}},
            "SB",
        ),
        (
            "moonshot_kimi_k3_v0_with_reasoning",
            "moonshot_chat",
            {
                "http_status": 200,
                "json": {
                    "id": "kimi-fixture",
                    "model": "kimi-k3",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "reasoning_content": "Internal fixture reasoning.",
                                "content": "",
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 5,
                        "total_tokens": 25,
                    },
                },
            },
            "V0",
        ),
        (
            "moonshot_kimi_k3_v1_budget_stop",
            "moonshot_chat",
            {
                "http_status": 200,
                "json": {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"reasoning_content": "x", "content": ""},
                        }
                    ]
                },
            },
            "V1",
        ),
        (
            "near_void",
            "openai_chat",
            {
                "http_status": 200,
                "json": {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": "\u200b"}}
                    ]
                },
            },
            "NV",
        ),
        (
            "response",
            "openai_chat",
            {
                "http_status": 200,
                "json": {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": "yes"}}
                    ]
                },
            },
            "R",
        ),
        (
            "protocol_incompatibility",
            "openai_chat",
            {
                "http_status": 400,
                "transport_error_type": "HTTPError",
                "json": {
                    "error": {
                        "message": "unsupported parameter",
                        "type": "invalid_request_error",
                    }
                },
            },
            "PI",
        ),
        (
            "provider_budget_error",
            "openai_chat",
            {
                "http_status": 400,
                "transport_error_type": "HTTPError",
                "json": {
                    "error": {
                        "message": "Could not finish because max_tokens or model output limit was reached.",
                        "type": "invalid_request_error",
                    }
                },
            },
            "BE",
        ),
        (
            "anthropic_credit_exhaustion",
            "anthropic_messages",
            {
                "http_status": 400,
                "transport_error_type": "HTTPError",
                "json": {
                    "error": {
                        "message": (
                            "Your credit balance is too low to access the Anthropic "
                            "API. Please go to Plans & Billing to purchase credits."
                        ),
                        "type": "invalid_request_error",
                    }
                },
            },
            "QE",
        ),
        (
            "openai_quota_exhaustion",
            "openai_chat",
            {
                "http_status": 429,
                "transport_error_type": "HTTPError",
                "json": {
                    "error": {
                        "message": "You exceeded your current quota.",
                        "type": "insufficient_quota",
                        "code": "insufficient_quota",
                    }
                },
            },
            "QE",
        ),
        (
            "moonshot_balance_exhaustion",
            "moonshot_chat",
            {
                "http_status": 429,
                "transport_error_type": "HTTPError",
                "json": {
                    "error": {
                        "message": "Insufficient balance. Please recharge.",
                        "type": "insufficient_balance_error",
                        "code": "insufficient_balance",
                    }
                },
            },
            "QE",
        ),
        (
            "infrastructure_error",
            "openai_chat",
            {
                "http_status": 500,
                "transport_error_type": "HTTPError",
                "json": {"error": {"message": "server"}},
            },
            "E",
        ),
    ]
    failures = []
    results = []
    for name, endpoint, partial, expected in fixtures:
        transport = {
            "transport_error_type": None,
            "raw_body_sha256": sha256_text("fixture"),
            **partial,
        }
        actual = classify_response(endpoint, transport, protocol)["classification"]
        results.append({"fixture": name, "expected": expected, "actual": actual})
        if actual != expected:
            failures.append(results[-1])
    retry_fixtures: list[tuple[str, dict[str, Any], bool]] = [
        ("retry_network_failure", {"http_status": None}, True),
        ("retry_rate_limit", {"http_status": 429, "json": {}}, True),
        ("retry_server_failure", {"http_status": 503, "json": {}}, True),
        ("retry_anthropic_overloaded", {"http_status": 529, "json": {}}, True),
        (
            "do_not_retry_quota",
            {
                "http_status": 429,
                "json": {"error": {"code": "insufficient_quota"}},
            },
            False,
        ),
        (
            "do_not_retry_moonshot_balance",
            {
                "http_status": 429,
                "json": {
                    "error": {
                        "code": "insufficient_balance",
                        "message": "Please recharge",
                    }
                },
            },
            False,
        ),
        ("do_not_retry_protocol_error", {"http_status": 400, "json": {}}, False),
        ("do_not_retry_success", {"http_status": 200, "json": {}}, False),
    ]
    for name, transport, expected_retry in retry_fixtures:
        actual = retryable_transport(transport, protocol)
        result = {"fixture": name, "expected": expected_retry, "actual": actual}
        results.append(result)
        if actual != expected_retry:
            failures.append(result)
    kimi_extracted = extract_moonshot_chat(
        {
            "id": "kimi-metrics",
            "model": "kimi-k3",
            "system_fingerprint": "kimi-fixture-fingerprint",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": "",
                        "reasoning_content": "reasoning fixture",
                    },
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
    )
    kimi_metrics_passed = (
        kimi_extracted["text"] == ""
        and kimi_extracted["text_container_present"] is True
        and kimi_extracted["reasoning_content_present"] is True
        and kimi_extracted["reasoning_utf8_bytes"]
        == len("reasoning fixture".encode("utf-8"))
        and kimi_extracted["reasoning_sha256"] == sha256_text("reasoning fixture")
        and kimi_extracted["thinking_blocks"] == 1
        and kimi_extracted["system_fingerprint"] == "kimi-fixture-fingerprint"
        and kimi_extracted["usage"]["total_tokens"] == 5
    )
    kimi_metrics_result = {
        "fixture": "moonshot_kimi_k3_exhaustive_extraction_metrics",
        "expected": True,
        "actual": kimi_metrics_passed,
    }
    results.append(kimi_metrics_result)
    if not kimi_metrics_passed:
        failures.append(kimi_metrics_result)
    prompt_errors = validate_protocol(protocol, build_default_prompts())
    failures.extend({"fixture": "protocol", "error": error} for error in prompt_errors)
    altered_protocol = json.loads(json.dumps(protocol))
    altered_protocol["admissibility_policy"]["external_observations_imported"] = True
    altered_errors = validate_protocol(altered_protocol, build_default_prompts())
    admissibility_tamper_passed = (
        "admissibility_policy differs from the enforced policy" in altered_errors
    )
    admissibility_tamper_result = {
        "fixture": "admissibility_policy_tamper_detection",
        "expected": True,
        "actual": admissibility_tamper_passed,
    }
    results.append(admissibility_tamper_result)
    if not admissibility_tamper_passed:
        failures.append(admissibility_tamper_result)
    retry_after_result = {
        "fixture": "retry_after_header",
        "expected": 7.0,
        "actual": retry_delay_seconds({"response_headers": {"retry-after": "7"}}, 1.0),
    }
    results.append(retry_after_result)
    if retry_after_result["actual"] != retry_after_result["expected"]:
        failures.append(retry_after_result)
    request_slot = {
        "provider": "anthropic",
        "model_id": "claude-opus-4-6",
        "endpoint": "anthropic_messages",
        "budget": 100,
        "parameter_track": "provider_default",
    }
    request_url, request_headers, request_body = request_shape_for_slot(
        request_slot, PRIMARY_SYSTEM, "Be silence."
    )
    request_record = public_request_record(request_url, request_headers, request_body)
    request_shape_passed = (
        request_record["headers"].get("x-api-key") == "REDACTED"
        and request_record["headers"].get("anthropic-version") == "2023-06-01"
        and request_record["body"]["model"] == "claude-opus-4-6"
    )
    request_shape_result = {
        "fixture": "credential_free_request_reconstruction",
        "expected": True,
        "actual": request_shape_passed,
    }
    results.append(request_shape_result)
    if not request_shape_passed:
        failures.append(request_shape_result)
    kimi_slot = {
        "provider": "moonshot",
        "model_id": "kimi-k3",
        "endpoint": "moonshot_chat",
        "budget": 16000,
        "parameter_track": "provider_default",
    }
    kimi_url, kimi_headers, kimi_body = request_shape_for_slot(
        kimi_slot, PRIMARY_SYSTEM, "Be silence."
    )
    kimi_record = public_request_record(kimi_url, kimi_headers, kimi_body)
    kimi_request_passed = (
        kimi_url == "https://api.moonshot.ai/v1/chat/completions"
        and kimi_headers
        == {
            "Authorization": "REDACTED",
            "Content-Type": "application/json",
        }
        and kimi_body["model"] == "kimi-k3"
        and kimi_body["max_completion_tokens"] == 16000
        and kimi_body["messages"]
        == [
            {"role": "system", "content": PRIMARY_SYSTEM},
            {"role": "user", "content": "Be silence."},
        ]
        and not {
            "reasoning_effort",
            "temperature",
            "top_p",
            "n",
            "presence_penalty",
            "frequency_penalty",
        }.intersection(kimi_body)
        and kimi_record["credential_logged"] is False
    )
    kimi_request_result = {
        "fixture": "moonshot_kimi_k3_exact_request_shape",
        "expected": True,
        "actual": kimi_request_passed,
    }
    results.append(kimi_request_result)
    if not kimi_request_passed:
        failures.append(kimi_request_result)
    kimi_inventory_fixture = {
        "openai": {"json": {"data": []}},
        "anthropic": {"json": {"data": []}},
        "google": {"json": {"models": []}},
        "moonshot": {
            "json": {
                "object": "list",
                "data": [{"id": "kimi-k3", "object": "model", "owned_by": "moonshot"}],
            }
        },
    }
    kimi_candidates = model_candidates(protocol, kimi_inventory_fixture)
    kimi_candidate = next(
        item for item in kimi_candidates if item["provider"] == "moonshot"
    )
    kimi_inventory_passed = (
        kimi_candidate["model_id"] == "kimi-k3"
        and kimi_candidate["inventory_present"] is True
        and kimi_candidate["enabled"] is True
        and kimi_candidate["inventory_metadata"]["owned_by"] == "moonshot"
    )
    kimi_inventory_result = {
        "fixture": "moonshot_kimi_k3_inventory_selection",
        "expected": True,
        "actual": kimi_inventory_passed,
    }
    results.append(kimi_inventory_result)
    if not kimi_inventory_passed:
        failures.append(kimi_inventory_result)
    prompt_fixture = build_default_prompts()
    model_fixture = {"models": [dict(target, enabled=True) for target in TARGET_MODELS]}
    schedule_a, exclusions_a = build_schedule_artifacts(
        protocol, prompt_fixture, model_fixture, "confirmatory", "fixture-seed"
    )
    schedule_b, exclusions_b = build_schedule_artifacts(
        protocol, prompt_fixture, model_fixture, "confirmatory", "fixture-seed"
    )
    schedule_passed = (
        schedule_a == schedule_b
        and exclusions_a == exclusions_b
        and len({slot["slot_id"] for slot in schedule_a}) == len(schedule_a)
        and all(slot["sequence"] == index for index, slot in enumerate(schedule_a))
    )
    schedule_result = {
        "fixture": "deterministic_schedule_regeneration",
        "expected": True,
        "actual": schedule_passed,
        "slot_count": len(schedule_a),
    }
    results.append(schedule_result)
    if not schedule_passed:
        failures.append(schedule_result)
    with tempfile.TemporaryDirectory(prefix="void-matrix-schedule-") as temporary:
        fixture_root = Path(temporary)
        fixture_paths = study_paths(fixture_root)
        write_json(fixture_paths["frozen"], {"fixture": True})

        def write_fixture_schedule(
            rows: Sequence[Mapping[str, Any]], exclusions: Sequence[Mapping[str, Any]]
        ) -> dict[str, Any]:
            payload = b"".join(canonical_json(row) + b"\n" for row in rows)
            atomic_write(fixture_paths["schedule"], payload)
            manifest = {
                "schema": f"{SCHEMA_ID}.schedule",
                "created_utc": utc_now(),
                "state": "SCHEDULE_SEALED",
                "profile": "confirmatory",
                "public_seed": "fixture-seed",
                "public_seed_sha256": sha256_text("fixture-seed"),
                "frozen_manifest_sha256": file_sha256(fixture_paths["frozen"]),
                "schedule_sha256": file_sha256(fixture_paths["schedule"]),
                "slot_count": len(rows),
                "block_counts": dict(
                    sorted(Counter(row["block"] for row in rows).items())
                ),
                "structural_excluded_slot_count": sum(
                    int(item["excluded_slot_count"]) for item in exclusions
                ),
                "structural_exclusions": list(exclusions),
            }
            manifest["manifest_sha256"] = unsigned_manifest_sha256(manifest)
            write_json(fixture_paths["schedule_manifest"], manifest, overwrite=True)
            return manifest

        write_fixture_schedule(schedule_a, exclusions_a)
        clean_errors, _, _ = validate_schedule_artifacts(
            fixture_paths, {}, protocol, prompt_fixture, model_fixture
        )
        tampered = [dict(row) for row in schedule_a]
        tampered[0]["prompt_id"] = "tampered_after_freeze"
        write_fixture_schedule(tampered, exclusions_a)
        tamper_errors, _, _ = validate_schedule_artifacts(
            fixture_paths, {}, protocol, prompt_fixture, model_fixture
        )
        tamper_passed = (
            not clean_errors
            and "schedule differs from deterministic frozen-input regeneration"
            in tamper_errors
        )
        tamper_result = {
            "fixture": "coupled_schedule_and_manifest_tamper_detection",
            "expected": True,
            "actual": tamper_passed,
        }
        results.append(tamper_result)
        if not tamper_passed:
            failures.append(tamper_result)
    with tempfile.TemporaryDirectory(prefix="void-matrix-chain-") as temporary:
        chain_path = Path(temporary) / "events.jsonl"
        first = append_chain(chain_path, {"event_type": "fixture", "value": 1})
        second = append_chain(chain_path, {"event_type": "fixture", "value": 2})
        chain_errors, chain_count, chain_head = verify_chain(chain_path)
        chain_passed = (
            not chain_errors
            and chain_count == 2
            and chain_head == second["event_sha256"]
            and second["previous_event_sha256"] == first["event_sha256"]
        )
        chain_result = {
            "fixture": "append_only_hash_chain",
            "expected": "valid_two_event_chain",
            "actual": "valid_two_event_chain" if chain_passed else chain_errors,
        }
        results.append(chain_result)
        if not chain_passed:
            failures.append(chain_result)
    report = {
        "schema": f"{SCHEMA_ID}.self-test",
        "created_utc": utc_now(),
        "runner_sha256": file_sha256(Path(__file__).resolve()),
        "passed": not failures,
        "results": results,
        "failures": failures,
    }
    paths = study_paths(args.root)
    paths["reports"].mkdir(parents=True, exist_ok=True)
    write_json(paths["reports"] / "self_test.json", report, overwrite=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


def cmd_inventory(args: argparse.Namespace) -> int:
    paths = study_paths(args.root)
    if paths["frozen"].exists():
        raise RuntimeError("Study is frozen; inventory cannot be replaced")
    protocol = read_json(paths["protocol"])
    timeout = int(protocol["execution"]["request_timeout_seconds"])
    inventories = {
        "openai": inventory_openai(timeout),
        "anthropic": inventory_anthropic(timeout),
        "google": inventory_google(timeout),
        "moonshot": inventory_moonshot(timeout),
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    paths["inventories"].mkdir(parents=True, exist_ok=True)
    inventory_hashes = {}
    for provider, result in inventories.items():
        output = paths["inventories"] / f"{provider}_{stamp}.json"
        write_json(output, result)
        inventory_hashes[provider] = {
            "path": str(output.relative_to(args.root)),
            "sha256": file_sha256(output),
        }
    models: dict[str, Any] = {
        "schema": f"{SCHEMA_ID}.models",
        "created_utc": utc_now(),
        "inventory_hashes": inventory_hashes,
        "models": model_candidates(protocol, inventories),
        "external_observations_imported": False,
    }
    write_json(paths["models"], models, overwrite=args.replace)
    print(f"MODELS_PATH={paths['models']}")
    print(f"MODEL_COUNT={len(models['models'])}")
    for item in models["models"]:
        print(
            f"{item['provider']}\t{item['model_id']}\t"
            f"{','.join(item['endpoints'])}\tpresent={item['inventory_present']}"
        )
    missing = [
        f"{item['provider']}:{item['model_id']}"
        for item in models["models"]
        if not item["inventory_present"]
    ]
    print(f"MISSING_TARGETS={json.dumps(missing)}")
    return 0 if not missing else 2


def cmd_preflight(args: argparse.Namespace) -> int:
    """Prove every scheduled request shape is accepted before the study is frozen."""
    paths = study_paths(args.root)
    # Acquire exclusive lock
    lock_file = paths["preflight_raw"].parent / "preflight.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = None
    try:
        import fcntl

        lock_fd = os.open(lock_file, os.O_RDWR | os.O_CREAT)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("Another preflight process is active in this study root.")
    except ImportError:
        pass

    try:
        if paths["frozen"].exists():
            raise RuntimeError(
                "Study is frozen; capability preflight cannot be replaced"
            )
        if paths["preflight_raw"].exists() and args.replace:
            for file_path in paths["preflight_raw"].glob("*.json"):
                file_path.unlink()

        protocol = read_json(paths["protocol"])
        prompts = read_json(paths["prompts"])
        models = read_json(paths["models"])
        errors = validate_protocol(protocol, prompts)
        errors.extend(validate_model_manifest(models, protocol))
        if errors:
            raise ValueError(
                "Cannot preflight invalid manifests:\n" + "\n".join(errors)
            )

        timeout = int(protocol["execution"]["request_timeout_seconds"])
        max_attempts = 1 + int(protocol["execution"].get("automatic_retries", 0))
        retry_backoffs = list(protocol["execution"].get("retry_backoff_seconds", []))
        delay = float(protocol["execution"].get("delay_seconds", 0))
        paths["preflight_raw"].mkdir(parents=True, exist_ok=True)
        system = prompts["systems"]["primary"]
        prompt = prompts["cases"]["control_hello"]
        results: list[dict[str, Any]] = []

        for model in models["models"]:
            for endpoint in model["endpoints"]:
                shapes = [
                    {
                        "name": "provider_default_at_model_ceiling",
                        "parameter_track": "provider_default",
                        "budget": int(model["max_output_tokens"]),
                    }
                ]
                if "temperature_zero" in model["parameter_tracks"]:
                    shapes.append(
                        {
                            "name": "temperature_zero",
                            "parameter_track": "temperature_zero",
                            "budget": 100,
                        }
                    )
                for shape in shapes:
                    slot = {
                        "provider": model["provider"],
                        "model_id": model["model_id"],
                        "endpoint": endpoint,
                        "study_id": "capability_preflight",
                        "system_id": system["id"],
                        "prompt_id": prompt["id"],
                        "budget": shape["budget"],
                        "parameter_track": shape["parameter_track"],
                        "replicate": 0,
                        "block": 0,
                        "transport": protocol["execution"]["transport"],
                    }
                    shape_basis = {
                        "provider": slot["provider"],
                        "model_id": slot["model_id"],
                        "endpoint": endpoint,
                        **shape,
                    }
                    shape_id = sha256_bytes(canonical_json(shape_basis))
                    request_url, headers, request_body = request_for_slot(
                        slot, system["text"], prompt["text"]
                    )
                    shape_url, shape_headers, shape_body = request_shape_for_slot(
                        slot, system["text"], prompt["text"]
                    )
                    public_request = public_request_record(
                        shape_url, shape_headers, shape_body
                    )
                    attempts = []
                    compatible = False
                    for attempt_number in range(1, max_attempts + 1):
                        transport = http_json(
                            "POST",
                            request_url,
                            headers=headers,
                            body=request_body,
                            timeout=timeout,
                        )
                        classification = classify_response(
                            endpoint, transport, protocol
                        )
                        raw_record = {
                            "schema": f"{SCHEMA_ID}.capability-preflight.raw",
                            "shape_id": shape_id,
                            "shape": shape_basis,
                            "attempt_number": attempt_number,
                            "system_prompt": system,
                            "user_prompt": prompt,
                            "request": public_request,
                            "transport": transport,
                            "classification": classification,
                        }
                        raw_path = (
                            paths["preflight_raw"] / f"{shape_id}.{attempt_number}.json"
                        )
                        write_json(raw_path, raw_record, overwrite=args.replace)
                        attempts.append(
                            {
                                "attempt_number": attempt_number,
                                "raw_path": str(raw_path.relative_to(args.root)),
                                "raw_sha256": file_sha256(raw_path),
                                "http_status": transport["http_status"],
                                "classification": classification["classification"],
                            }
                        )
                        status = transport.get("http_status")
                        compatible = (
                            status is not None
                            and 200 <= int(status) < 300
                            and isinstance(transport.get("json"), Mapping)
                            and classification["classification"] == "R"
                        )
                        if compatible or not retryable_transport(transport, protocol):
                            break
                        if retry_backoffs:
                            backoff_index = min(
                                attempt_number - 1, len(retry_backoffs) - 1
                            )
                            time.sleep(
                                retry_delay_seconds(
                                    transport, float(retry_backoffs[backoff_index])
                                )
                            )
                    results.append(
                        {
                            "shape_id": shape_id,
                            "shape": shape_basis,
                            "compatible": compatible,
                            "attempts": attempts,
                        }
                    )
                    print(
                        f"PREFLIGHT {model['provider']} {model['model_id']} {endpoint} "
                        f"{shape['parameter_track']} B={shape['budget']} compatible={compatible}",
                        flush=True,
                    )
                    if delay:
                        time.sleep(delay)

        report = {
            "schema": f"{SCHEMA_ID}.capability-preflight",
            "created_utc": utc_now(),
            "valid": all(item["compatible"] for item in results),
            "runner_sha256": file_sha256(Path(__file__).resolve()),
            "protocol_sha256": file_sha256(paths["protocol"]),
            "prompts_sha256": file_sha256(paths["prompts"]),
            "models_sha256": file_sha256(paths["models"]),
            "shape_count": len(results),
            "results": results,
        }
        write_json(paths["preflight"], report, overwrite=args.replace)
        print(f"PREFLIGHT_PATH={paths['preflight']}")
        print(f"PREFLIGHT_VALID={report['valid']}")
        return 0 if report["valid"] else 1
    finally:
        if lock_fd is not None:
            try:
                import fcntl

                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(lock_fd)
            except Exception:
                pass


def expected_preflight_shapes(models: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for model in models["models"]:
        for endpoint in model["endpoints"]:
            shapes = [
                {
                    "name": "provider_default_at_model_ceiling",
                    "parameter_track": "provider_default",
                    "budget": int(model["max_output_tokens"]),
                }
            ]
            if "temperature_zero" in model["parameter_tracks"]:
                shapes.append(
                    {
                        "name": "temperature_zero",
                        "parameter_track": "temperature_zero",
                        "budget": 100,
                    }
                )
            for shape in shapes:
                basis = {
                    "provider": model["provider"],
                    "model_id": model["model_id"],
                    "endpoint": endpoint,
                    **shape,
                }
                expected[sha256_bytes(canonical_json(basis))] = basis
    return expected


def validate_capability_preflight(
    root: Path,
    preflight: Mapping[str, Any],
    protocol: Mapping[str, Any],
    models: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    paths = study_paths(root)
    prompts = read_json(paths["prompts"])
    system = prompts["systems"]["primary"]
    prompt = prompts["cases"]["control_hello"]
    expected = expected_preflight_shapes(models)
    actual: dict[str, Mapping[str, Any]] = {}
    referenced_raw_paths: set[Path] = set()
    if preflight.get("runner_sha256") != file_sha256(Path(__file__).resolve()):
        errors.append("preflight runner SHA-256 mismatch")
    for name, path, field in (
        ("protocol", paths["protocol"], "protocol_sha256"),
        ("prompts", paths["prompts"], "prompts_sha256"),
        ("models", paths["models"], "models_sha256"),
    ):
        if preflight.get(field) != file_sha256(path):
            errors.append(f"preflight {name} SHA-256 mismatch")
    for result in preflight.get("results", []):
        shape_id = result.get("shape_id")
        if not shape_id or shape_id in actual:
            errors.append(f"duplicate or missing preflight shape id {shape_id}")
            continue
        actual[shape_id] = result
        shape = result.get("shape")
        if (
            not isinstance(shape, Mapping)
            or sha256_bytes(canonical_json(shape)) != shape_id
        ):
            errors.append(f"preflight shape hash mismatch {shape_id}")
            continue
        attempts = result.get("attempts") or []
        if not attempts:
            errors.append(f"preflight shape has no attempts {shape_id}")
            continue
        final_compatible = False
        for attempt in attempts:
            relative = attempt.get("raw_path")
            raw_path = (root / str(relative)).resolve()
            try:
                raw_path.relative_to(paths["preflight_raw"].resolve())
            except ValueError:
                errors.append(f"preflight raw path escapes raw directory {relative}")
                continue
            referenced_raw_paths.add(raw_path)
            if not raw_path.exists():
                errors.append(f"missing preflight raw record {relative}")
                continue
            if file_sha256(raw_path) != attempt.get("raw_sha256"):
                errors.append(f"preflight raw SHA-256 mismatch {relative}")
                continue
            raw = read_json(raw_path)
            if raw.get("shape_id") != shape_id or raw.get("shape") != shape:
                errors.append(f"preflight raw shape mismatch {relative}")
            if raw.get("attempt_number") != attempt.get("attempt_number"):
                errors.append(f"preflight raw attempt mismatch {relative}")
            if raw.get("system_prompt") != system:
                errors.append(f"preflight raw system prompt mismatch {relative}")
            if raw.get("user_prompt") != prompt:
                errors.append(f"preflight raw user prompt mismatch {relative}")
            slot = {
                "provider": shape["provider"],
                "model_id": shape["model_id"],
                "endpoint": shape["endpoint"],
                "budget": shape["budget"],
                "parameter_track": shape["parameter_track"],
            }
            expected_url, expected_headers, expected_body = request_shape_for_slot(
                slot, system["text"], prompt["text"]
            )
            expected_request = public_request_record(
                expected_url, expected_headers, expected_body
            )
            if raw.get("request") != expected_request:
                errors.append(f"preflight request reconstruction mismatch {relative}")
            transport = raw.get("transport") or {}
            if transport.get("http_status") != attempt.get("http_status"):
                errors.append(f"preflight HTTP status mismatch {relative}")
            recomputed = classify_response(shape["endpoint"], transport, protocol)
            if recomputed != raw.get("classification"):
                errors.append(f"preflight classification replay mismatch {relative}")
            if recomputed.get("classification") != attempt.get("classification"):
                errors.append(f"preflight recorded classification mismatch {relative}")
            status = transport.get("http_status")
            final_compatible = (
                status is not None
                and 200 <= int(status) < 300
                and isinstance(transport.get("json"), Mapping)
                and recomputed.get("classification") == "R"
            )
        if bool(result.get("compatible")) != final_compatible:
            errors.append(f"preflight compatibility mismatch {shape_id}")
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extras = sorted(set(actual) - set(expected))
        if missing:
            errors.append(f"missing preflight shapes: {missing}")
        if extras:
            errors.append(f"unexpected preflight shapes: {extras}")
    if preflight.get("shape_count") != len(actual):
        errors.append("preflight shape count mismatch")
    existing_raw_paths = {
        path.resolve()
        for path in paths["preflight_raw"].glob("*.json")
        if path.is_file()
    }
    orphan_raw_paths = sorted(existing_raw_paths - referenced_raw_paths)
    if orphan_raw_paths:
        errors.append(f"orphan preflight raw records: {len(orphan_raw_paths)}")
    if bool(preflight.get("valid")) != (
        not errors and all(bool(item.get("compatible")) for item in actual.values())
    ):
        errors.append("preflight validity flag mismatch")
    return errors


def cmd_validate(args: argparse.Namespace) -> int:
    paths = study_paths(args.root)
    protocol = read_json(paths["protocol"])
    prompts = read_json(paths["prompts"])
    errors = validate_protocol(protocol, prompts)
    models: Mapping[str, Any] | None = None
    if paths["models"].exists():
        models = read_json(paths["models"])
        errors.extend(validate_model_manifest(models, protocol))
    elif args.require_models:
        errors.append("models.json is missing; run inventory")
    if paths["preflight"].exists():
        preflight = read_json(paths["preflight"])
        if models is None:
            errors.append("cannot validate capability preflight without models.json")
        else:
            errors.extend(
                validate_capability_preflight(args.root, preflight, protocol, models)
            )
    elif getattr(args, "require_preflight", False):
        errors.append("capability_preflight.json is missing; run preflight")
    report = {
        "created_utc": utc_now(),
        "valid": not errors,
        "errors": errors,
        "protocol_sha256": file_sha256(paths["protocol"]),
        "prompts_sha256": file_sha256(paths["prompts"]),
        "models_sha256": file_sha256(paths["models"])
        if paths["models"].exists()
        else None,
        "capability_preflight_sha256": file_sha256(paths["preflight"])
        if paths["preflight"].exists()
        else None,
        "runner_sha256": file_sha256(Path(__file__).resolve()),
    }
    paths["reports"].mkdir(parents=True, exist_ok=True)
    write_json(paths["reports"] / "validation.json", report, overwrite=True)
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


def cmd_freeze(args: argparse.Namespace) -> int:
    paths = study_paths(args.root)
    if paths["frozen"].exists():
        raise FileExistsError("Frozen manifest already exists")
    protocol = read_json(paths["protocol"])
    prompts = read_json(paths["prompts"])
    models = read_json(paths["models"])
    if not paths["preflight"].exists():
        raise FileNotFoundError("capability_preflight.json is missing; run preflight")
    preflight = read_json(paths["preflight"])
    errors = validate_protocol(protocol, prompts)
    errors.extend(validate_model_manifest(models, protocol))
    errors.extend(validate_capability_preflight(args.root, preflight, protocol, models))
    if errors:
        raise ValueError("Cannot freeze invalid study:\n" + "\n".join(errors))
    study_path = args.root / "study.json"
    study = read_json(study_path)
    study["state"] = "MANIFEST_FROZEN"
    study["frozen_utc"] = utc_now()
    study["environment"] = environment_record()
    write_json(study_path, study, overwrite=True)
    frozen = {
        "schema": f"{SCHEMA_ID}.frozen",
        "frozen_utc": utc_now(),
        "state": "MANIFEST_FROZEN",
        "files": {
            "study.json": file_sha256(study_path),
            "protocol.json": file_sha256(paths["protocol"]),
            "prompts.json": file_sha256(paths["prompts"]),
            "models.json": file_sha256(paths["models"]),
            "capability_preflight.json": file_sha256(paths["preflight"]),
            "void_matrix.py": file_sha256(Path(__file__).resolve()),
        },
        "environment": environment_record(),
    }
    frozen["manifest_sha256"] = sha256_bytes(canonical_json(frozen))
    write_json(paths["frozen"], frozen)
    print(f"FROZEN_MANIFEST={paths['frozen']}")
    print(f"FROZEN_SHA256={file_sha256(paths['frozen'])}")
    return 0


def assert_frozen(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    paths = study_paths(root)
    frozen = read_json(paths["frozen"])
    if frozen.get("manifest_sha256") != unsigned_manifest_sha256(frozen):
        raise RuntimeError("Frozen manifest self-hash mismatch")
    checks = {
        "study.json": root / "study.json",
        "protocol.json": paths["protocol"],
        "prompts.json": paths["prompts"],
        "models.json": paths["models"],
        "capability_preflight.json": paths["preflight"],
        "void_matrix.py": Path(__file__).resolve(),
    }
    mismatches = [
        name
        for name, path in checks.items()
        if file_sha256(path) != frozen["files"].get(name)
    ]
    if mismatches:
        raise RuntimeError(f"Frozen-file mismatch: {mismatches}")
    return (
        frozen,
        read_json(paths["protocol"]),
        read_json(paths["prompts"]),
        read_json(paths["models"]),
    )


def expand_prompt_ids(prompts: Mapping[str, Any], sets: Sequence[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for set_id in sets:
        for prompt_id in prompts["sets"][set_id]:
            if prompt_id not in seen:
                seen.add(prompt_id)
                ordered.append(prompt_id)
    return ordered


def build_schedule_artifacts(
    protocol: Mapping[str, Any],
    prompts: Mapping[str, Any],
    models: Mapping[str, Any],
    profile_name: str,
    seed: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Regenerate the exact seeded schedule and declared structural exclusions."""
    profile = protocol["profiles"][profile_name]
    slots: list[dict[str, Any]] = []
    exclusion_counts: Counter[tuple[Any, ...]] = Counter()
    for model in models["models"]:
        if not model.get("enabled"):
            continue
        for endpoint in model["endpoints"]:
            for study in protocol["studies"]:
                n = (
                    profile["primary_n"]
                    if study["sample_tier"] == "primary"
                    else profile["secondary_n"]
                )
                prompt_ids = expand_prompt_ids(prompts, study["prompt_sets"])
                for prompt_id in prompt_ids:
                    for budget in study["budgets"]:
                        for track in study["parameter_tracks"]:
                            exclusion_reason = None
                            if track not in model["parameter_tracks"]:
                                exclusion_reason = "unsupported_parameter_track"
                            elif budget > int(model["max_output_tokens"]):
                                exclusion_reason = (
                                    "output_budget_exceeds_model_capability"
                                )
                            if exclusion_reason:
                                exclusion_counts[
                                    (
                                        exclusion_reason,
                                        model["provider"],
                                        model["model_id"],
                                        endpoint,
                                        study["id"],
                                        prompt_id,
                                        budget,
                                        track,
                                    )
                                ] += n
                                continue
                            for replicate in range(n):
                                block = replicate % int(profile["blocks"])
                                slot = {
                                    "provider": model["provider"],
                                    "model_id": model["model_id"],
                                    "endpoint": endpoint,
                                    "study_id": study["id"],
                                    "system_id": study["system_id"],
                                    "prompt_id": prompt_id,
                                    "budget": budget,
                                    "parameter_track": track,
                                    "replicate": replicate,
                                    "block": block,
                                    "transport": protocol["execution"]["transport"],
                                }
                                slot["slot_id"] = sha256_bytes(canonical_json(slot))
                                slots.append(slot)
    random.Random(int(sha256_text(seed), 16)).shuffle(slots)
    for sequence, slot in enumerate(slots):
        slot["sequence"] = sequence
    exclusions = [
        {
            "reason": key[0],
            "provider": key[1],
            "model_id": key[2],
            "endpoint": key[3],
            "study_id": key[4],
            "prompt_id": key[5],
            "budget": key[6],
            "parameter_track": key[7],
            "excluded_slot_count": count,
        }
        for key, count in sorted(exclusion_counts.items())
    ]
    return slots, exclusions


def unsigned_manifest_sha256(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    unsigned.pop("report_sha256", None)
    return sha256_bytes(canonical_json(unsigned))


def validate_schedule_artifacts(
    paths: Mapping[str, Path],
    frozen: Mapping[str, Any],
    protocol: Mapping[str, Any],
    prompts: Mapping[str, Any],
    models: Mapping[str, Any],
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    errors: list[str] = []
    if not paths["schedule_manifest"].exists() or not paths["schedule"].exists():
        return ["schedule or schedule manifest is missing"], [], {}
    manifest = read_json(paths["schedule_manifest"])
    actual_slots = list(iter_jsonl(paths["schedule"]))
    if manifest.get("manifest_sha256") != unsigned_manifest_sha256(manifest):
        errors.append("schedule manifest self-hash mismatch")
    if manifest.get("public_seed_sha256") != sha256_text(
        str(manifest.get("public_seed", ""))
    ):
        errors.append("schedule public seed hash mismatch")
    if manifest.get("frozen_manifest_sha256") != file_sha256(paths["frozen"]):
        errors.append("schedule references a different frozen manifest")
    if file_sha256(paths["schedule"]) != manifest.get("schedule_sha256"):
        errors.append("schedule SHA-256 mismatch")
    try:
        expected_slots, expected_exclusions = build_schedule_artifacts(
            protocol,
            prompts,
            models,
            str(manifest["profile"]),
            str(manifest["public_seed"]),
        )
    except Exception as exc:
        errors.append(f"schedule regeneration failed: {type(exc).__name__}: {exc}")
        expected_slots, expected_exclusions = [], []
    if actual_slots != expected_slots:
        errors.append("schedule differs from deterministic frozen-input regeneration")
    if manifest.get("structural_exclusions") != expected_exclusions:
        errors.append("structural exclusions differ from frozen-input regeneration")
    expected_block_counts = dict(
        (str(block), count)
        for block, count in sorted(
            Counter(slot["block"] for slot in expected_slots).items()
        )
    )
    if manifest.get("block_counts") != expected_block_counts:
        errors.append("schedule block counts mismatch")
    if manifest.get("slot_count") != len(expected_slots):
        errors.append("schedule slot count mismatch")
    if manifest.get("structural_excluded_slot_count") != sum(
        item["excluded_slot_count"] for item in expected_exclusions
    ):
        errors.append("structural exclusion count mismatch")
    return errors, actual_slots, manifest


def cmd_schedule(args: argparse.Namespace) -> int:
    paths = study_paths(args.root)
    if paths["schedule"].exists() or paths["schedule_manifest"].exists():
        raise FileExistsError("Schedule already exists")
    frozen, protocol, prompts, models = assert_frozen(args.root)
    slots, structural_exclusions = build_schedule_artifacts(
        protocol, prompts, models, args.profile, args.seed
    )
    paths["schedule"].parent.mkdir(parents=True, exist_ok=True)
    with paths["schedule"].open("wb") as stream:
        for slot in slots:
            stream.write(canonical_json(slot) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    block_counts = Counter(slot["block"] for slot in slots)
    manifest = {
        "schema": f"{SCHEMA_ID}.schedule",
        "created_utc": utc_now(),
        "state": "SCHEDULE_SEALED",
        "profile": args.profile,
        "public_seed": args.seed,
        "public_seed_sha256": sha256_text(args.seed),
        "frozen_manifest_sha256": file_sha256(paths["frozen"]),
        "schedule_sha256": file_sha256(paths["schedule"]),
        "slot_count": len(slots),
        "block_counts": dict(sorted(block_counts.items())),
        "structural_excluded_slot_count": sum(
            item["excluded_slot_count"] for item in structural_exclusions
        ),
        "structural_exclusions": structural_exclusions,
    }
    manifest["manifest_sha256"] = unsigned_manifest_sha256(manifest)
    write_json(paths["schedule_manifest"], manifest)
    print(f"SCHEDULE={paths['schedule']}")
    print(f"SLOTS={len(slots)}")
    print(f"SCHEDULE_SHA256={manifest['schedule_sha256']}")
    return 0


def completed_slots_and_attempts(
    events_path: Path,
) -> tuple[set[str], dict[str, int]]:
    done: set[str] = set()
    retry_attempts: dict[str, int] = {}
    for event in iter_jsonl(events_path):
        slot_id = event.get("slot_id")
        if not slot_id:
            continue
        event_type = event.get("event_type")
        if event_type == "trial_completed":
            done.add(slot_id)
        if event_type in {
            "trial_attempt_completed",
            "trial_completed",
            "trial_aborted",
        }:
            classification = event.get("classification") or {}
            reason = classification.get("reason")
            if reason == "provider_paused_before_request":
                continue
            att = event.get("attempt_number")
            if att is not None:
                retry_attempts[slot_id] = max(retry_attempts.get(slot_id, 0), int(att))
    return done, retry_attempts


async def reconcile_dangling_attempts(
    paths: dict[str, Path],
    protocol: dict[str, Any],
    event_chain: AsyncEventChain,
    root: Path,
) -> None:
    """Scan the event log for started-but-unterminated attempts and reconcile them."""
    if not paths["events"].exists():
        return

    attempts: dict[str, dict[str, Any]] = {}
    for event in iter_jsonl(paths["events"]):
        event_type = event.get("event_type")
        attempt_id = event.get("attempt_id")
        if not attempt_id:
            continue
        if event_type == "trial_started":
            attempts[attempt_id] = {"started": event, "terminated": None}
        elif event_type in {
            "trial_attempt_completed",
            "trial_completed",
            "trial_aborted",
            "provider_paused",
        }:
            if attempt_id in attempts:
                attempts[attempt_id]["terminated"] = event

    dangling = [
        item["started"] for item in attempts.values() if item["terminated"] is None
    ]
    if not dangling:
        return

    print(f"RECONCILING={len(dangling)} dangling attempts found")
    max_attempts = 1 + int(protocol["execution"].get("automatic_retries", 0))

    for started in dangling:
        slot = started["slot"]
        attempt_id = started["attempt_id"]
        attempt_number = started["attempt_number"]
        worker_id = started["worker_id"]
        raw_path = paths["raw"] / f"{slot['slot_id']}.{attempt_id}.json"
        execution_record = started.get("execution") or {}

        if raw_path.exists():
            try:
                raw = read_json(raw_path)
                transport = raw.get("transport") or {}
                classification = classify_response(
                    slot["endpoint"], transport, protocol
                )
                classification_code = classification["classification"]
                retry_scheduled = (
                    attempt_number < max_attempts
                    and classification_code == "E"
                    and retryable_transport(transport, protocol)
                )
                quota_pause = classification_code == "QE"
                raw_sha256 = file_sha256(raw_path)
                http_status = transport.get("http_status")
                response_headers = transport.get("response_headers") or {}
                raw_body_sha256 = transport.get("raw_body_sha256") or sha256_bytes(b"")

                if quota_pause:
                    event_type = "provider_paused"
                elif retry_scheduled:
                    event_type = "trial_attempt_completed"
                else:
                    event_type = "trial_completed"
                reconciled_event = {
                    "schema": SCHEMA_ID,
                    "event_type": event_type,
                    "event_utc": utc_now(),
                    "slot_id": slot["slot_id"],
                    "attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "retry_scheduled": retry_scheduled,
                    "slot": slot,
                    "raw_path": str(raw_path.relative_to(root)),
                    "raw_sha256": raw_sha256,
                    "http_status": http_status,
                    "response_headers": response_headers,
                    "raw_body_sha256": raw_body_sha256,
                    "classification": classification,
                    "execution": execution_record,
                    "worker_id": worker_id,
                }
            except Exception as exc:
                reconciled_event = {
                    "schema": SCHEMA_ID,
                    "event_type": "trial_aborted",
                    "event_utc": utc_now(),
                    "slot_id": slot["slot_id"],
                    "attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "retry_scheduled": False,
                    "slot": slot,
                    "classification": {
                        "classifier_id": CLASSIFIER_ID,
                        "classification": "E",
                        "reason": f"aborted_reconciliation_error: {type(exc).__name__}",
                        "error_details": {"message": str(exc)},
                        "extracted": None,
                        "visible_text": text_evidence(None, container_present=False),
                    },
                    "execution": execution_record,
                    "worker_id": worker_id,
                }
        else:
            if attempt_number >= max_attempts:
                # Interrupted on final attempt. Emit synthetic E completion so study completes.
                synthetic_transport = {
                    "started_utc": utc_now(),
                    "ended_utc": utc_now(),
                    "elapsed_seconds": 0.0,
                    "http_status": None,
                    "response_headers": {},
                    "raw_body_base64": "",
                    "raw_body_sha256": sha256_bytes(b""),
                    "raw_body_bytes": 0,
                    "json": None,
                    "transport_error_type": "InterruptedAttemptReconciliation",
                    "transport_error_message": "Process interrupted during final attempt before raw response was written",
                }
                classification = classify_response(
                    slot["endpoint"], synthetic_transport, protocol
                )

                # Reconstruct expected request shape
                prompts = read_json(paths["prompts"])
                system = prompts["systems"][slot["system_id"]]
                prompt = prompts["cases"][slot["prompt_id"]]
                expected_url, expected_headers, expected_body = request_shape_for_slot(
                    slot, system["text"], prompt["text"]
                )
                public_request = public_request_record(
                    expected_url, expected_headers, expected_body
                )

                raw_record = {
                    "schema": f"{SCHEMA_ID}.raw",
                    "slot": slot,
                    "attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "system_prompt": system,
                    "user_prompt": prompt,
                    "request": public_request,
                    "transport": synthetic_transport,
                }
                write_json(raw_path, raw_record)
                raw_sha256 = file_sha256(raw_path)

                reconciled_event = {
                    "schema": SCHEMA_ID,
                    "event_type": "trial_completed",
                    "event_utc": utc_now(),
                    "slot_id": slot["slot_id"],
                    "attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "retry_scheduled": False,
                    "slot": slot,
                    "raw_path": str(raw_path.relative_to(root)),
                    "raw_sha256": raw_sha256,
                    "http_status": None,
                    "response_headers": {},
                    "raw_body_sha256": sha256_bytes(b""),
                    "classification": classification,
                    "execution": execution_record,
                    "worker_id": worker_id,
                }
            else:
                reconciled_event = {
                    "schema": SCHEMA_ID,
                    "event_type": "trial_aborted",
                    "event_utc": utc_now(),
                    "slot_id": slot["slot_id"],
                    "attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "retry_scheduled": False,
                    "slot": slot,
                    "classification": {
                        "classifier_id": CLASSIFIER_ID,
                        "classification": "E",
                        "reason": "aborted_attempt",
                        "error_details": {
                            "message": "Process interrupted before request completion"
                        },
                        "extracted": None,
                        "visible_text": text_evidence(None, container_present=False),
                    },
                    "execution": execution_record,
                    "worker_id": worker_id,
                }

        await event_chain.append(reconciled_event)
        print(
            f"RECONCILED={slot['provider']} {slot['model_id']} slot={slot['slot_id']} attempt={attempt_id} -> {reconciled_event['event_type']}"
        )


async def cmd_run_async(args: argparse.Namespace) -> int:
    paths = study_paths(args.root)
    lock_file = paths["run"] / "run.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = None
    try:
        import fcntl

        lock_fd = os.open(lock_file, os.O_RDWR | os.O_CREAT)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("Another run process is active in this study root.")
    except ImportError:
        pass

    try:
        frozen, protocol, prompts, models = assert_frozen(args.root)
        schedule_errors, scheduled_slots, schedule_manifest = (
            validate_schedule_artifacts(paths, frozen, protocol, prompts, models)
        )
        if schedule_errors:
            raise RuntimeError("Invalid schedule: " + "; ".join(schedule_errors))
        if args.block is None and not args.all_blocks:
            raise ValueError(
                "Specify exactly one --block, or explicitly use --all-blocks"
            )
        if args.block is not None and args.all_blocks:
            raise ValueError("Cannot specify both --block and --all-blocks")
        if args.limit is not None and args.limit < 1:
            raise ValueError("--limit must be greater than or equal to 1")
        if args.block is not None:
            block_counts = schedule_manifest.get("block_counts") or {}
            if block_counts:
                max_block_val = max(int(b) for b in block_counts.keys())
                if not (0 <= args.block <= max_block_val):
                    raise ValueError(f"--block must be between 0 and {max_block_val}")

        paths["raw"].mkdir(parents=True, exist_ok=True)
        event_chain = await AsyncEventChain.open(paths["events"])
        await reconcile_dangling_attempts(paths, protocol, event_chain, args.root)

        done, slot_attempts = completed_slots_and_attempts(paths["events"])
        chosen = []
        for slot in scheduled_slots:
            if slot["slot_id"] in done:
                continue
            if args.block is not None and slot["block"] != args.block:
                continue
            if args.provider and slot["provider"] not in args.provider:
                continue
            chosen.append(slot)
            if args.limit is not None and len(chosen) >= args.limit:
                break
        print(f"PENDING_SELECTED={len(chosen)}")
        if args.dry_run:
            print("DRY_RUN=1")
            return 0
        if not 1 <= args.workers <= 128:
            raise ValueError("--workers must be between 1 and 128")
        timeout = int(protocol["execution"]["request_timeout_seconds"])
        delay = float(protocol["execution"]["delay_seconds"])
        max_attempts = 1 + int(protocol["execution"].get("automatic_retries", 0))
        retry_backoffs = list(protocol["execution"].get("retry_backoff_seconds", []))
        paused_providers: set[str] = set()
        provider_pause_lock = asyncio.Lock()
        progress_lock = asyncio.Lock()
        activity_lock = asyncio.Lock()
        completed_count = 0

        active_requests = 0
        max_active_requests = 0
        provider_limits = {
            provider: int(limit)
            for provider, limit in protocol["execution"]
            .get("provider_concurrency_limits", {})
            .items()
        }
        if set(provider_limits) != set(KEY_SOURCES) or any(
            limit < 1 for limit in provider_limits.values()
        ):
            raise RuntimeError(
                "Frozen provider concurrency limits are incomplete or invalid"
            )
        provider_semaphores = {
            provider: asyncio.Semaphore(limit)
            for provider, limit in provider_limits.items()
        }
        provider_cooldown_locks = {
            provider: asyncio.Lock() for provider in provider_limits
        }
        provider_not_before = {provider: 0.0 for provider in provider_limits}
        execution_record = {
            "concurrency": "asyncio_bounded_worker_pool",
            "workers": args.workers,
            "provider_concurrency_limits": provider_limits,
            "shared_provider_cooldown": True,
            "event_chain_serialization": "single_asyncio_lock_with_cached_chain_head",
        }
        http_executor = ThreadPoolExecutor(
            max_workers=args.workers, thread_name_prefix="void-matrix-http"
        )
        loop = asyncio.get_running_loop()

        async def wait_for_provider(provider: str) -> None:
            while True:
                async with provider_cooldown_locks[provider]:
                    remaining = provider_not_before[provider] - loop.time()
                if remaining <= 0:
                    return
                await asyncio.sleep(remaining)

        async def defer_provider(provider: str, seconds: float) -> None:
            if seconds <= 0:
                return
            async with provider_cooldown_locks[provider]:
                provider_not_before[provider] = max(
                    provider_not_before[provider], loop.time() + seconds
                )

        async def call_provider(
            provider: str,
            request_url: str,
            headers: Mapping[str, str],
            request_body: Mapping[str, Any],
        ) -> dict[str, Any]:
            nonlocal active_requests, max_active_requests
            await wait_for_provider(provider)
            async with provider_semaphores[provider]:
                # A cooldown can begin while this coroutine waits for its provider
                # semaphore. Recheck immediately before transmitting.
                await wait_for_provider(provider)
                async with provider_pause_lock:
                    if provider in paused_providers:
                        raise ProviderPaused(provider)
                async with activity_lock:
                    active_requests += 1
                    max_active_requests = max(max_active_requests, active_requests)
                try:
                    return await loop.run_in_executor(
                        http_executor,
                        bind_call(
                            http_json,
                            "POST",
                            request_url,
                            headers=headers,
                            body=request_body,
                            timeout=timeout,
                        ),
                    )
                finally:
                    async with activity_lock:
                        active_requests -= 1

        async def process_slot(
            selection_index: int, slot: Mapping[str, Any], worker_id: int
        ) -> None:
            nonlocal completed_count
            provider = slot["provider"]
            async with provider_pause_lock:
                if provider in paused_providers:
                    return
            system = prompts["systems"][slot["system_id"]]
            prompt = prompts["cases"][slot["prompt_id"]]
            request_url, headers, request_body = request_for_slot(
                slot, system["text"], prompt["text"]
            )
            shape_url, shape_headers, shape_body = request_shape_for_slot(
                slot, system["text"], prompt["text"]
            )
            public_request = public_request_record(shape_url, shape_headers, shape_body)
            start_attempt = slot_attempts.get(slot["slot_id"], 0) + 1
            for attempt_number in range(start_attempt, max_attempts + 1):
                attempt_id = secrets.token_hex(16)
                await event_chain.append(
                    {
                        "schema": SCHEMA_ID,
                        "event_type": "trial_started",
                        "event_utc": utc_now(),
                        "slot_id": slot["slot_id"],
                        "attempt_id": attempt_id,
                        "attempt_number": attempt_number,
                        "slot": slot,
                        "system_prompt_sha256": system["sha256"],
                        "user_prompt_sha256": prompt["sha256"],
                        "request": public_request,
                        "execution": execution_record,
                        "worker_id": worker_id,
                    },
                )
                try:
                    transport = await call_provider(
                        slot["provider"], request_url, headers, request_body
                    )
                    raw_record = {
                        "schema": f"{SCHEMA_ID}.raw",
                        "slot": slot,
                        "attempt_id": attempt_id,
                        "attempt_number": attempt_number,
                        "system_prompt": system,
                        "user_prompt": prompt,
                        "request": public_request,
                        "transport": transport,
                    }
                    raw_path = paths["raw"] / f"{slot['slot_id']}.{attempt_id}.json"
                    await asyncio.to_thread(write_json, raw_path, raw_record)
                    classification = classify_response(
                        slot["endpoint"], transport, protocol
                    )
                    if transport.get("http_status") in {429, 529}:
                        fallback_index = min(
                            attempt_number - 1, max(len(retry_backoffs) - 1, 0)
                        )
                        fallback = (
                            float(retry_backoffs[fallback_index])
                            if retry_backoffs
                            else 1.0
                        )
                        await defer_provider(
                            slot["provider"], retry_delay_seconds(transport, fallback)
                        )
                    classification_code = classification["classification"]
                    retry_scheduled = (
                        attempt_number < max_attempts
                        and classification_code == "E"
                        and retryable_transport(transport, protocol)
                    )
                    quota_pause = classification_code == "QE"

                    if quota_pause:
                        event_type = "provider_paused"
                    elif retry_scheduled:
                        event_type = "trial_attempt_completed"
                    else:
                        event_type = "trial_completed"

                    raw_sha256 = await asyncio.to_thread(file_sha256, raw_path)
                    http_status = transport["http_status"]
                    response_headers = transport["response_headers"]
                    raw_body_sha256 = transport["raw_body_sha256"]
                except ProviderPaused:
                    event = await event_chain.append(
                        {
                            "schema": SCHEMA_ID,
                            "event_type": "trial_aborted",
                            "event_utc": utc_now(),
                            "slot_id": slot["slot_id"],
                            "attempt_id": attempt_id,
                            "attempt_number": attempt_number,
                            "retry_scheduled": False,
                            "slot": slot,
                            "classification": {
                                "classifier_id": CLASSIFIER_ID,
                                "classification": "E",
                                "reason": "provider_paused_before_request",
                                "error_details": {
                                    "message": "Provider was paused before request was transmitted"
                                },
                                "extracted": None,
                                "visible_text": text_evidence(
                                    None, container_present=False
                                ),
                            },
                            "execution": execution_record,
                            "worker_id": worker_id,
                        }
                    )
                    break
                except Exception as exc:
                    retry_scheduled = False
                    quota_pause = False
                    synthetic_transport = {
                        "started_utc": utc_now(),
                        "ended_utc": utc_now(),
                        "elapsed_seconds": 0.0,
                        "http_status": None,
                        "response_headers": {},
                        "raw_body_base64": "",
                        "raw_body_sha256": sha256_bytes(b""),
                        "raw_body_bytes": 0,
                        "json": None,
                        "transport_error_type": type(exc).__name__,
                        "transport_error_message": str(exc),
                    }
                    classification = classify_response(
                        slot["endpoint"], synthetic_transport, protocol
                    )
                    classification_code = classification["classification"]
                    # If local exception resolves to QE (e.g. from mock), treat as quota pause
                    if classification_code == "QE":
                        quota_pause = True
                        event_type = "provider_paused"
                    else:
                        event_type = "trial_completed"

                    raw_record = {
                        "schema": f"{SCHEMA_ID}.raw",
                        "slot": slot,
                        "attempt_id": attempt_id,
                        "attempt_number": attempt_number,
                        "system_prompt": system,
                        "user_prompt": prompt,
                        "request": public_request,
                        "transport": synthetic_transport,
                    }
                    raw_path = paths["raw"] / f"{slot['slot_id']}.{attempt_id}.json"
                    await asyncio.to_thread(write_json, raw_path, raw_record)
                    raw_sha256 = await asyncio.to_thread(file_sha256, raw_path)
                    http_status = None
                    response_headers = {}
                    raw_body_sha256 = sha256_bytes(b"")

                event = await event_chain.append(
                    {
                        "schema": SCHEMA_ID,
                        "event_type": event_type,
                        "event_utc": utc_now(),
                        "slot_id": slot["slot_id"],
                        "attempt_id": attempt_id,
                        "attempt_number": attempt_number,
                        "retry_scheduled": retry_scheduled,
                        "slot": slot,
                        "raw_path": str(raw_path.relative_to(args.root)),
                        "raw_sha256": raw_sha256,
                        "http_status": http_status,
                        "response_headers": response_headers,
                        "raw_body_sha256": raw_body_sha256,
                        "classification": classification,
                        "execution": execution_record,
                        "worker_id": worker_id,
                    },
                )
                if quota_pause:
                    async with provider_pause_lock:
                        paused_providers.add(provider)
                    print(
                        f"PROVIDER PAUSED: {provider} hit quota exhaustion. "
                        "Add credits and rerun to resume unfinished slots.",
                        flush=True,
                    )
                    break
                if not retry_scheduled:
                    async with progress_lock:
                        completed_count += 1
                        progress = completed_count
                    print(
                        f"[{progress}/{len(chosen)} selected={selection_index} "
                        f"worker={worker_id} attempt={attempt_number}/{max_attempts}] "
                        f"{slot['provider']} {slot['model_id']} {slot['endpoint']} "
                        f"{slot['study_id']} {slot['prompt_id']} B={slot['budget']} -> "
                        f"{classification['classification']} {event['event_sha256'][:12]}",
                        flush=True,
                    )
                    break
                backoff_index = min(attempt_number - 1, len(retry_backoffs) - 1)
                if retry_backoffs:
                    await asyncio.sleep(
                        retry_delay_seconds(
                            transport, float(retry_backoffs[backoff_index])
                        )
                    )
            if delay:
                await asyncio.sleep(delay)

        queue: asyncio.Queue[tuple[int, Mapping[str, Any]] | None] = asyncio.Queue()
        for index, slot in enumerate(chosen, 1):
            queue.put_nowait((index, slot))
        worker_count = min(args.workers, len(chosen))
        for _ in range(worker_count):
            queue.put_nowait(None)

        async def worker(worker_id: int) -> None:
            while True:
                item = await queue.get()
                if item is None:
                    return
                selection_index, slot = item
                await process_slot(selection_index, slot, worker_id)

        try:
            if worker_count:
                await asyncio.gather(*(worker(i + 1) for i in range(worker_count)))
        finally:
            await asyncio.to_thread(http_executor.shutdown, wait=True)
        print(f"WORKERS={args.workers}")
        print(f"MAX_IN_FLIGHT_OBSERVED={max_active_requests}")
        print(f"EVENT_CHAIN_HEAD={event_chain.head}")
        return 0
    finally:
        if lock_fd is not None:
            try:
                import fcntl

                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(lock_fd)
            except Exception:
                pass


def cmd_run(args: argparse.Namespace) -> int:
    """Execute the bounded concurrent runner in one asyncio event loop."""
    return asyncio.run(cmd_run_async(args))


def verify_chain(path: Path) -> tuple[list[str], int, str]:
    errors: list[str] = []
    previous = "0" * 64
    count = 0
    for event in iter_jsonl(path):
        count += 1
        if event.get("previous_event_sha256") != previous:
            errors.append(f"event {count}: previous hash mismatch")
        claimed = event.get("event_sha256")
        unsigned = dict(event)
        unsigned.pop("event_sha256", None)
        actual = sha256_bytes(canonical_json(unsigned))
        if claimed != actual:
            errors.append(f"event {count}: event hash mismatch")
        previous = claimed or previous
    return errors, count, previous


def cmd_verify(args: argparse.Namespace) -> int:
    paths = study_paths(args.root)
    frozen, protocol, prompts, models = assert_frozen(args.root)
    schedule_errors, schedule_rows, schedule_manifest = validate_schedule_artifacts(
        paths, frozen, protocol, prompts, models
    )
    errors: list[str] = list(schedule_errors)
    scheduled: dict[str, dict[str, Any]] = {}
    for row_number, slot in enumerate(schedule_rows):
        slot_id = slot.get("slot_id")
        if not slot_id:
            errors.append(f"schedule row {row_number}: missing slot_id")
        elif slot_id in scheduled:
            errors.append(f"schedule row {row_number}: duplicate slot_id {slot_id}")
        else:
            scheduled[slot_id] = slot
    chain_errors, event_count, chain_head = verify_chain(paths["events"])
    errors.extend(chain_errors)
    completed: set[str] = set()
    duplicates: set[str] = set()
    started_attempts: dict[str, dict[str, Any]] = {}
    completed_attempts: set[str] = set()
    referenced_raw_paths: set[Path] = set()
    raw_checked = 0
    for event in iter_jsonl(paths["events"]):
        raw_slot_id = event.get("slot_id")
        raw_attempt_id = event.get("attempt_id")
        slot_id = raw_slot_id if isinstance(raw_slot_id, str) else None
        attempt_id = raw_attempt_id if isinstance(raw_attempt_id, str) else None
        if slot_id not in scheduled:
            errors.append(f"event references unscheduled slot {slot_id}")
        elif event.get("slot") != scheduled[slot_id]:
            errors.append(f"event slot payload mismatch {slot_id}")
        event_type = event.get("event_type")
        if event_type not in {
            "trial_started",
            "trial_attempt_completed",
            "trial_completed",
            "trial_aborted",
            "provider_paused",
        }:
            errors.append(f"event references unknown event type: {event_type}")
            continue
        if event_type == "trial_started":
            if not attempt_id:
                errors.append(f"started event missing attempt_id for {slot_id}")
            elif attempt_id in started_attempts:
                errors.append(f"duplicate attempt_id {attempt_id}")
            else:
                started_attempts[attempt_id] = event
            slot = event.get("slot") or {}
            system = prompts.get("systems", {}).get(slot.get("system_id"))
            prompt = prompts.get("cases", {}).get(slot.get("prompt_id"))
            if not system or not prompt:
                errors.append(f"start references unknown frozen prompt {attempt_id}")
            else:
                if event.get("system_prompt_sha256") != system.get("sha256"):
                    errors.append(f"system prompt hash mismatch {attempt_id}")
                if event.get("user_prompt_sha256") != prompt.get("sha256"):
                    errors.append(f"user prompt hash mismatch {attempt_id}")
                expected_url, expected_headers, expected_body = request_shape_for_slot(
                    slot, system["text"], prompt["text"]
                )
                expected_request = public_request_record(
                    expected_url, expected_headers, expected_body
                )
                if event.get("request") != expected_request:
                    errors.append(
                        f"frozen request reconstruction mismatch {attempt_id}"
                    )
            continue
        if event_type == "provider_paused":
            if not attempt_id or attempt_id not in started_attempts:
                errors.append(f"paused event has no matching start for {slot_id}")
            elif attempt_id in completed_attempts:
                errors.append(f"attempt completed twice {attempt_id}")
            else:
                completed_attempts.add(attempt_id)
            started = started_attempts.get(attempt_id, {}) if attempt_id else {}
            if event.get("attempt_number") != started.get("attempt_number"):
                errors.append(f"attempt number mismatch {attempt_id}")
            if event.get("retry_scheduled") is not False:
                errors.append(f"paused attempt has retry marker {attempt_id}")
            execution = event.get("execution")
            if execution != started.get("execution"):
                errors.append(f"execution metadata mismatch {attempt_id}")
            if event.get("worker_id") != started.get("worker_id"):
                errors.append(f"worker id mismatch {attempt_id}")
            if event.get("classification", {}).get("classification") != "QE":
                errors.append(f"non-billing result recorded as pause {attempt_id}")
            raw_path_value = event.get("raw_path")
            try:
                raw_path = (args.root / str(raw_path_value)).resolve()
                raw_path.relative_to(paths["raw"].resolve())
            except (TypeError, ValueError):
                errors.append(f"raw path escapes frozen raw directory {attempt_id}")
                continue
            referenced_raw_paths.add(raw_path)
            if not raw_path.exists():
                errors.append(f"missing raw record {raw_path}")
            elif file_sha256(raw_path) != event["raw_sha256"]:
                errors.append(f"raw SHA-256 mismatch {raw_path}")
            else:
                raw_checked += 1
                raw = read_json(raw_path)
                if raw.get("slot") != event.get("slot"):
                    errors.append(f"raw slot payload mismatch {raw_path}")
                if raw.get("attempt_id") != attempt_id:
                    errors.append(f"raw attempt id mismatch {raw_path}")
                if raw.get("attempt_number") != event.get("attempt_number"):
                    errors.append(f"raw attempt number mismatch {raw_path}")
                if raw.get("system_prompt") != prompts["systems"].get(
                    event["slot"]["system_id"]
                ):
                    errors.append(f"raw system prompt mismatch {raw_path}")
                if raw.get("user_prompt") != prompts["cases"].get(
                    event["slot"]["prompt_id"]
                ):
                    errors.append(f"raw user prompt mismatch {raw_path}")
                if raw.get("request") != started.get("request"):
                    errors.append(f"raw/start request mismatch {raw_path}")
                request = raw.get("request") or {}
                request_body = request.get("body")
                if not isinstance(request_body, Mapping):
                    errors.append(f"raw request body missing {raw_path}")
                elif request.get("body_sha256") != sha256_bytes(
                    canonical_json(request_body)
                ):
                    errors.append(f"raw request body SHA-256 mismatch {raw_path}")
                system = prompts["systems"][event["slot"]["system_id"]]
                prompt = prompts["cases"][event["slot"]["prompt_id"]]
                expected_url, expected_headers, expected_body = request_shape_for_slot(
                    event["slot"], system["text"], prompt["text"]
                )
                if request != public_request_record(
                    expected_url, expected_headers, expected_body
                ):
                    errors.append(
                        f"raw frozen request reconstruction mismatch {raw_path}"
                    )
                transport = raw.get("transport") or {}
                encoded = transport.get("raw_body_base64")
                try:
                    response_bytes = (
                        base64.b64decode(encoded, validate=True)
                        if isinstance(encoded, str)
                        else None
                    )
                except Exception:
                    response_bytes = None
                if response_bytes is None:
                    errors.append(f"raw response body is not valid base64 {raw_path}")
                else:
                    if transport.get("raw_body_sha256") != sha256_bytes(response_bytes):
                        errors.append(f"raw response body SHA-256 mismatch {raw_path}")
                    if transport.get("raw_body_bytes") != len(response_bytes):
                        errors.append(f"raw response body length mismatch {raw_path}")
                recomputed = classify_response(
                    event["slot"]["endpoint"], transport, protocol
                )
                if recomputed != event.get("classification"):
                    errors.append(f"classification replay mismatch {raw_path}")
            continue
        if event_type == "trial_aborted":
            if not attempt_id or attempt_id not in started_attempts:
                errors.append(f"aborted event has no matching start for {slot_id}")
            elif attempt_id in completed_attempts:
                errors.append(f"attempt completed twice {attempt_id}")
            else:
                completed_attempts.add(attempt_id)
            started = started_attempts.get(attempt_id, {}) if attempt_id else {}
            if event.get("attempt_number") != started.get("attempt_number"):
                errors.append(f"attempt number mismatch {attempt_id}")
            if event.get("retry_scheduled") is not False:
                errors.append(f"aborted attempt has retry marker {attempt_id}")
            execution = event.get("execution")
            if execution != started.get("execution"):
                errors.append(f"execution metadata mismatch {attempt_id}")
            if event.get("worker_id") != started.get("worker_id"):
                errors.append(f"worker id mismatch {attempt_id}")
            continue
        if not attempt_id or attempt_id not in started_attempts:
            errors.append(f"completion has no matching start for {slot_id}")
        elif attempt_id in completed_attempts:
            errors.append(f"attempt completed twice {attempt_id}")
        else:
            completed_attempts.add(attempt_id)
        started = started_attempts.get(attempt_id, {}) if attempt_id else {}
        if event.get("attempt_number") != started.get("attempt_number"):
            errors.append(f"attempt number mismatch {attempt_id}")
        execution = event.get("execution")
        if execution != started.get("execution"):
            errors.append(f"execution metadata mismatch {attempt_id}")
        elif not isinstance(execution, Mapping):
            errors.append(f"execution metadata missing {attempt_id}")
        else:
            workers = execution.get("workers")
            if not isinstance(workers, int) or not 1 <= workers <= 128:
                errors.append(f"invalid worker count {attempt_id}")
            if execution.get("concurrency") != "asyncio_bounded_worker_pool":
                errors.append(f"invalid concurrency mode {attempt_id}")
            if execution.get("provider_concurrency_limits") != protocol[
                "execution"
            ].get("provider_concurrency_limits"):
                errors.append(f"provider concurrency limits mismatch {attempt_id}")
            if execution.get("event_chain_serialization") != (
                "single_asyncio_lock_with_cached_chain_head"
            ):
                errors.append(f"invalid chain serialization mode {attempt_id}")
        if event.get("worker_id") != started.get("worker_id"):
            errors.append(f"worker id mismatch {attempt_id}")
        if event_type == "trial_attempt_completed":
            if event.get("retry_scheduled") is not True:
                errors.append(f"retry attempt lacks retry marker {attempt_id}")
            if event.get("classification", {}).get("classification") != "E":
                errors.append(
                    f"non-infrastructure result scheduled for retry {attempt_id}"
                )
        else:
            if event.get("retry_scheduled") is not False:
                errors.append(f"final completion has retry marker {attempt_id}")
            if slot_id is None:
                errors.append("final completion is missing a string slot_id")
            elif slot_id in completed:
                duplicates.add(slot_id)
            else:
                completed.add(slot_id)
        raw_path_value = event.get("raw_path")
        try:
            raw_path = (args.root / str(raw_path_value)).resolve()
            raw_path.relative_to(paths["raw"].resolve())
        except (TypeError, ValueError):
            errors.append(f"raw path escapes frozen raw directory {attempt_id}")
            continue
        referenced_raw_paths.add(raw_path)
        if not raw_path.exists():
            errors.append(f"missing raw record {raw_path}")
        elif file_sha256(raw_path) != event["raw_sha256"]:
            errors.append(f"raw SHA-256 mismatch {raw_path}")
        else:
            raw_checked += 1
            raw = read_json(raw_path)
            if raw.get("slot") != event.get("slot"):
                errors.append(f"raw slot payload mismatch {raw_path}")
            if raw.get("attempt_id") != attempt_id:
                errors.append(f"raw attempt id mismatch {raw_path}")
            if raw.get("attempt_number") != event.get("attempt_number"):
                errors.append(f"raw attempt number mismatch {raw_path}")
            if raw.get("system_prompt") != prompts["systems"].get(
                event["slot"]["system_id"]
            ):
                errors.append(f"raw system prompt mismatch {raw_path}")
            if raw.get("user_prompt") != prompts["cases"].get(
                event["slot"]["prompt_id"]
            ):
                errors.append(f"raw user prompt mismatch {raw_path}")
            if raw.get("request") != started.get("request"):
                errors.append(f"raw/start request mismatch {raw_path}")
            request = raw.get("request") or {}
            request_body = request.get("body")
            if not isinstance(request_body, Mapping):
                errors.append(f"raw request body missing {raw_path}")
            elif request.get("body_sha256") != sha256_bytes(
                canonical_json(request_body)
            ):
                errors.append(f"raw request body SHA-256 mismatch {raw_path}")
            system = prompts["systems"][event["slot"]["system_id"]]
            prompt = prompts["cases"][event["slot"]["prompt_id"]]
            expected_url, expected_headers, expected_body = request_shape_for_slot(
                event["slot"], system["text"], prompt["text"]
            )
            if request != public_request_record(
                expected_url, expected_headers, expected_body
            ):
                errors.append(f"raw frozen request reconstruction mismatch {raw_path}")
            transport = raw.get("transport") or {}
            encoded = transport.get("raw_body_base64")
            try:
                response_bytes = (
                    base64.b64decode(encoded, validate=True)
                    if isinstance(encoded, str)
                    else None
                )
            except Exception:
                response_bytes = None
            if response_bytes is None:
                errors.append(f"raw response body is not valid base64 {raw_path}")
            else:
                if transport.get("raw_body_sha256") != sha256_bytes(response_bytes):
                    errors.append(f"raw response body SHA-256 mismatch {raw_path}")
                if transport.get("raw_body_bytes") != len(response_bytes):
                    errors.append(f"raw response body length mismatch {raw_path}")
            recomputed = classify_response(
                event["slot"]["endpoint"], transport, protocol
            )
            if recomputed != event.get("classification"):
                errors.append(f"classification replay mismatch {raw_path}")
            if event_type == "trial_attempt_completed" and not retryable_transport(
                transport, protocol
            ):
                errors.append(f"non-retryable transport scheduled for retry {raw_path}")
    if duplicates:
        errors.append(f"duplicate completed slot IDs: {sorted(duplicates)[:10]}")
    incomplete_attempts = sorted(set(started_attempts) - completed_attempts)
    if incomplete_attempts:
        errors.append(
            f"incomplete attempts without terminal records: {len(incomplete_attempts)}"
        )
    existing_raw_paths = set()
    if paths["raw"].exists():
        existing_raw_paths = {
            path.resolve() for path in paths["raw"].glob("*.json") if path.is_file()
        }
    orphan_raw_paths = sorted(
        str(path.relative_to(args.root.resolve()))
        for path in existing_raw_paths - referenced_raw_paths
    )
    if orphan_raw_paths:
        errors.append(f"orphan raw records: {len(orphan_raw_paths)}")
    pending_slots = sorted(set(scheduled) - completed)
    schedule_complete = bool(scheduled) and not pending_slots
    if args.require_complete and not schedule_complete:
        errors.append(f"schedule incomplete: {len(pending_slots)} slots pending")
    report = {
        "schema": f"{SCHEMA_ID}.verification",
        "created_utc": utc_now(),
        "valid": not errors,
        "errors": errors,
        "frozen_manifest_sha256": file_sha256(paths["frozen"]),
        "schedule_manifest_sha256": file_sha256(paths["schedule_manifest"]),
        "schedule_manifest_self_hash": schedule_manifest.get("manifest_sha256"),
        "events_sha256": file_sha256(paths["events"])
        if paths["events"].exists()
        else None,
        "event_count": event_count,
        "scheduled_slot_count": len(scheduled),
        "completed_slot_count": len(completed),
        "pending_slot_count": len(pending_slots),
        "schedule_complete": schedule_complete,
        "started_attempt_count": len(started_attempts),
        "incomplete_attempt_count": len(incomplete_attempts),
        "incomplete_attempt_ids": incomplete_attempts,
        "orphan_raw_record_count": len(orphan_raw_paths),
        "orphan_raw_paths": orphan_raw_paths,
        "raw_file_set_sha256": file_set_sha256(sorted(existing_raw_paths), args.root)
        if existing_raw_paths
        else None,
        "raw_records_verified": raw_checked,
        "chain_head": chain_head,
    }
    report["report_sha256"] = unsigned_manifest_sha256(report)
    paths["reports"].mkdir(parents=True, exist_ok=True)
    write_json(paths["reports"] / "verification.json", report, overwrite=True)
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


def cmd_summarize(args: argparse.Namespace) -> int:
    paths = study_paths(args.root)
    frozen, protocol, prompts, models = assert_frozen(args.root)
    schedule_errors, _, _ = validate_schedule_artifacts(
        paths, frozen, protocol, prompts, models
    )
    if schedule_errors:
        raise RuntimeError(
            "Schedule changed after verification: " + "; ".join(schedule_errors)
        )
    verify_report_path = paths["reports"] / "verification.json"
    if not verify_report_path.exists():
        raise RuntimeError("A verification report is required before summarization")
    verification = read_json(verify_report_path)
    if verification.get("report_sha256") != unsigned_manifest_sha256(verification):
        raise RuntimeError("Verification report self-hash mismatch")
    if not verification.get("valid") or not verification.get("schedule_complete"):
        raise RuntimeError(
            "A valid, schedule-complete verification report is required before summarization"
        )
    chain_errors, event_count, chain_head = verify_chain(paths["events"])
    current_events_sha256 = file_sha256(paths["events"])
    current_raw_file_set_sha256 = file_set_sha256(
        [path.resolve() for path in paths["raw"].glob("*.json") if path.is_file()],
        args.root,
    )
    if chain_errors:
        raise RuntimeError("Event chain changed or is invalid after verification")
    if (
        verification.get("chain_head") != chain_head
        or verification.get("event_count") != event_count
        or verification.get("events_sha256") != current_events_sha256
        or verification.get("raw_file_set_sha256") != current_raw_file_set_sha256
    ):
        raise RuntimeError(
            "Verification is stale: event log changed after verification"
        )
    cells: dict[tuple[Any, ...], Counter[str]] = defaultdict(Counter)
    for event in iter_jsonl(paths["events"]):
        if event.get("event_type") != "trial_completed":
            continue
        slot = event["slot"]
        key = (
            slot["provider"],
            slot["model_id"],
            slot["endpoint"],
            slot["study_id"],
            slot["system_id"],
            slot["prompt_id"],
            slot["budget"],
            slot["parameter_track"],
            slot["block"],
        )
        cells[key][event["classification"]["classification"]] += 1
    identity_columns = [
        "provider",
        "model_id",
        "endpoint",
        "study_id",
        "system_id",
        "prompt_id",
        "budget",
        "parameter_track",
        "block",
    ]
    columns = [
        *identity_columns,
        "total",
        "void_total",
        "normal_stop_void_total",
        "budget_stop_void_total",
        "unresolved_termination_void_total",
        *CLASSIFICATION_ORDER,
    ]
    rows = []
    for key, counts in sorted(cells.items()):
        row = dict(zip(identity_columns, key))
        row["total"] = sum(counts.values())
        row["void_total"] = sum(counts[cls] for cls in VOID_CLASSES)
        row["normal_stop_void_total"] = sum(
            counts[cls] for cls in NORMAL_STOP_VOID_CLASSES
        )
        row["budget_stop_void_total"] = sum(
            counts[cls] for cls in BUDGET_STOP_VOID_CLASSES
        )
        row["unresolved_termination_void_total"] = sum(
            counts[cls] for cls in UNRESOLVED_TERMINATION_VOID_CLASSES
        )
        for cls in CLASSIFICATION_ORDER:
            row[cls] = counts.get(cls, 0)
        rows.append(row)
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = csv_buffer.getvalue().encode("utf-8")
    end_chain_errors, end_event_count, end_chain_head = verify_chain(paths["events"])
    end_events_sha256 = file_sha256(paths["events"])
    end_raw_file_set_sha256 = file_set_sha256(
        [path.resolve() for path in paths["raw"].glob("*.json") if path.is_file()],
        args.root,
    )
    if (
        end_chain_errors
        or end_event_count != event_count
        or end_chain_head != chain_head
        or end_events_sha256 != current_events_sha256
        or end_raw_file_set_sha256 != current_raw_file_set_sha256
    ):
        raise RuntimeError("Event log changed while summary was being computed")
    paths["reports"].mkdir(parents=True, exist_ok=True)
    csv_path = paths["reports"] / "matrix.csv"
    atomic_write(csv_path, csv_bytes)
    aggregate_classifications = Counter(
        event["classification"]["classification"]
        for event in iter_jsonl(paths["events"])
        if event.get("event_type") == "trial_completed"
    )
    summary = {
        "schema": f"{SCHEMA_ID}.summary",
        "created_utc": utc_now(),
        "verification_report_sha256": file_sha256(verify_report_path),
        "verified_event_count": event_count,
        "verified_events_sha256": current_events_sha256,
        "verified_event_chain_head": chain_head,
        "cell_count": len(rows),
        "matrix_csv": str(csv_path.relative_to(args.root)),
        "matrix_csv_sha256": file_sha256(csv_path),
        "aggregate_classifications": dict(sorted(aggregate_classifications.items())),
        "aggregate_voids": {
            "total": sum(aggregate_classifications[cls] for cls in VOID_CLASSES),
            "normal_stop": sum(
                aggregate_classifications[cls] for cls in NORMAL_STOP_VOID_CLASSES
            ),
            "budget_stop": sum(
                aggregate_classifications[cls] for cls in BUDGET_STOP_VOID_CLASSES
            ),
            "unresolved_termination": sum(
                aggregate_classifications[cls]
                for cls in UNRESOLVED_TERMINATION_VOID_CLASSES
            ),
        },
        "rows": rows,
    }
    write_json(paths["reports"] / "summary.json", summary, overwrite=True)
    print(f"SUMMARY={paths['reports'] / 'summary.json'}")
    print(f"MATRIX={csv_path}")
    print(f"CELLS={len(rows)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_STUDY_ROOT, help="Study artifact directory"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="Create unfrozen manifests; no live calls"
    )
    init_parser.set_defaults(func=cmd_init)

    test_parser = subparsers.add_parser(
        "self-test", help="Run offline classifier fixtures"
    )
    test_parser.set_defaults(func=cmd_self_test)

    inventory_parser = subparsers.add_parser(
        "inventory", help="Make four live model-list calls and create models.json"
    )
    inventory_parser.add_argument(
        "--replace", action="store_true", help="Replace an unfrozen models.json"
    )
    inventory_parser.set_defaults(func=cmd_inventory)

    preflight_parser = subparsers.add_parser(
        "preflight",
        help="Validate every enabled request shape with bounded live control calls",
    )
    preflight_parser.add_argument(
        "--replace", action="store_true", help="Replace an unfrozen preflight record"
    )
    preflight_parser.set_defaults(func=cmd_preflight)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate unfrozen manifests; no live calls"
    )
    validate_parser.add_argument("--require-models", action="store_true")
    validate_parser.add_argument("--require-preflight", action="store_true")
    validate_parser.set_defaults(func=cmd_validate)

    freeze_parser = subparsers.add_parser(
        "freeze", help="Hash and freeze code and manifests; no live calls"
    )
    freeze_parser.set_defaults(func=cmd_freeze)

    schedule_parser = subparsers.add_parser(
        "schedule", help="Create seeded immutable schedule; no live calls"
    )
    schedule_parser.add_argument(
        "--seed", required=True, help="Future public randomness value"
    )
    schedule_parser.add_argument(
        "--profile", choices=["confirmatory"], default="confirmatory"
    )
    schedule_parser.set_defaults(func=cmd_schedule)

    run_parser = subparsers.add_parser(
        "run", help="Execute scheduled live calls with bounded asyncio concurrency"
    )
    run_parser.add_argument("--block", type=int)
    run_parser.add_argument("--all-blocks", action="store_true")
    run_parser.add_argument("--provider", action="append", choices=sorted(KEY_SOURCES))
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument(
        "--workers",
        type=int,
        default=100,
        help="Maximum concurrent API requests (default: 100; allowed: 1-128)",
    )
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.set_defaults(func=cmd_run)

    verify_parser = subparsers.add_parser(
        "verify", help="Verify frozen files, schedule, raw records, and hash chain"
    )
    verify_parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail unless every scheduled slot has one completed result",
    )
    verify_parser.set_defaults(func=cmd_verify)

    summarize_parser = subparsers.add_parser(
        "summarize", help="Generate matrix only after verification"
    )
    summarize_parser.set_defaults(func=cmd_summarize)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.root = args.root.expanduser().resolve()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("INTERRUPTED: no scheduled slot is silently replaced", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
