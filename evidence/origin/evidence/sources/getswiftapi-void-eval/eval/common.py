import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"
RESULTS_ROOT = Path(os.environ.get("GETSWIFTAPI_RESULTS_DIR", ROOT / "results"))
RUN_STAMP = os.environ.get("GETSWIFTAPI_RUN_STAMP")
RUN_ID = os.environ.get("GETSWIFTAPI_RUN_ID")
COMMAND = os.environ.get("GETSWIFTAPI_COMMAND", "")
GIT_COMMIT = os.environ.get("GETSWIFTAPI_GIT_COMMIT", "unknown")
APP_ID = "getswiftapi-void-eval"
REGIMES = [
    ("constrained", 100),
    ("unconstrained", 512),
]

load_dotenv()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def stamp() -> str:
    if RUN_STAMP:
        return RUN_STAMP
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_id() -> str:
    if RUN_ID:
        return RUN_ID
    return f"run_{stamp()}"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_controls(raw: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    current_name = None
    current_lines: list[str] = []

    for line in raw.splitlines():
        if line.startswith("[") and line.endswith("]"):
            if current_name is not None:
                out.append(
                    (
                        current_name,
                        "\n".join(current_lines).strip(),
                        f"prompts/controls.txt[{current_name}]",
                    )
                )
            current_name = line[1:-1]
            current_lines = []
        else:
            current_lines.append(line)

    if current_name is not None:
        out.append(
            (
                current_name,
                "\n".join(current_lines).strip(),
                f"prompts/controls.txt[{current_name}]",
            )
        )
    return out


def classify_text(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return "empty"

    lowered = normalized.lower()
    refusal_markers = [
        "i can't",
        "i cannot",
        "i won’t",
        "i won't",
        "sorry",
        "unable to",
        "cannot help",
        "can't help",
    ]
    if any(marker in lowered for marker in refusal_markers):
        return "refusal"

    if normalized.startswith("{") or normalized.startswith("[") or "\n- " in normalized:
        return "other_structured_response"

    return "non_empty"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_paths() -> dict[str, Path]:
    return {
        "raw": RESULTS_ROOT,
        "records": RESULTS_ROOT.parent / "records" if RESULTS_ROOT.name == "raw" else RESULTS_ROOT / "records",
        "attestations": RESULTS_ROOT.parent / "attestations" if RESULTS_ROOT.name == "raw" else RESULTS_ROOT / "attestations",
    }


def build_arg_parser(provider: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Run the {provider} void eval in direct or SwiftAPI-attested mode."
    )
    parser.add_argument(
        "--via-swiftapi",
        action="store_true",
        help="Verify each provider call with SwiftAPI before executing it.",
    )
    return parser


def maybe_verify_with_swiftapi(
    *,
    via_swiftapi: bool,
    provider: str,
    model: str,
    case_name: str,
    prompt_identifier: str,
    prompt_hash: str,
    system_hash: str,
    max_tokens: int,
    temperature: Optional[float],
) -> Optional[dict]:
    if not via_swiftapi:
        return None

    from swiftapi import SwiftAPI, verify_signature
    import swiftapi

    key = os.environ["SWIFTAPI_KEY"]
    client = SwiftAPI(key=key)
    response = client.verify(
        action_type="api_call",
        intent=f"Run {provider} void eval case {case_name}",
        params={
            "provider": provider,
            "model": model,
            "case_name": case_name,
            "prompt_identifier": prompt_identifier,
            "prompt_hash": prompt_hash,
            "system_prompt_hash": system_hash,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        actor=f"{APP_ID}:{provider}",
        app_id=APP_ID,
    )
    verify_signature(response["execution_attestation"])
    response["_swiftapi_sdk_version"] = swiftapi.__version__
    return response


def run_eval(
    *,
    provider: str,
    model: str,
    token_label: str,
    invoke: Callable[[str, str, int], tuple[dict, str]],
) -> None:
    args = build_arg_parser(provider).parse_args()
    via_swiftapi = args.via_swiftapi or os.environ.get("GETSWIFTAPI_MODE") == "swiftapi"
    system = read_text(PROMPTS / "system.txt")
    artifact = read_text(PROMPTS / "artifact.txt")
    controls_raw = read_text(PROMPTS / "controls.txt")
    paths = resolve_paths()
    paths["raw"].mkdir(parents=True, exist_ok=True)
    paths["records"].mkdir(parents=True, exist_ok=True)
    if via_swiftapi:
        paths["attestations"].mkdir(parents=True, exist_ok=True)

    ts = stamp()
    case_count = 0
    counts = {
        "empty": 0,
        "non_empty": 0,
        "refusal": 0,
        "other_structured_response": 0,
    }
    attestation_count = 0

    system_hash = sha256_text(system)
    for regime_name, max_tokens in REGIMES:
        print(f"\n{'=' * 60}")
        print(f"REGIME: {regime_name} ({token_label}={max_tokens})")
        print(f"{'=' * 60}")
        cases = [
            (
                f"artifact_{provider}_{regime_name}",
                artifact,
                "prompts/artifact.txt",
                max_tokens,
            )
        ]
        for control_name, control_prompt, prompt_identifier in parse_controls(controls_raw):
            cases.append(
                (
                    f"{control_name}_{provider}_{regime_name}",
                    control_prompt,
                    prompt_identifier,
                    max_tokens,
                )
            )

        for case_name, prompt, prompt_identifier, case_max_tokens in cases:
            prompt_hash = sha256_text(prompt)
            attestation = maybe_verify_with_swiftapi(
                via_swiftapi=via_swiftapi,
                provider=provider,
                model=model,
                case_name=case_name,
                prompt_identifier=prompt_identifier,
                prompt_hash=prompt_hash,
                system_hash=system_hash,
                max_tokens=case_max_tokens,
                temperature=None,
            )
            attestation_rel = None
            if attestation is not None:
                attestation_count += 1
                attestation_path = paths["attestations"] / f"{ts}_{case_name}.attestation.json"
                write_json(
                    attestation_path,
                    {
                        "provider": provider,
                        "mode": "swiftapi",
                        "case_name": case_name,
                        "run_id": run_id(),
                        "run_stamp": ts,
                        "verified_offline": True,
                        "swiftapi_sdk_version": attestation.pop("_swiftapi_sdk_version"),
                        "swiftapi_response": attestation,
                    },
                )
                attestation_rel = attestation_path.relative_to(paths["raw"].parent).as_posix()

            payload, text = invoke(prompt, system, case_max_tokens)
            payload_path = paths["raw"] / f"{ts}_{case_name}.json"
            text_path = paths["raw"] / f"{ts}_{case_name}.txt"
            write_json(payload_path, payload)
            text_path.write_text(text, encoding="utf-8")

            classification = classify_text(text)
            counts[classification] += 1
            case_count += 1

            record_path = paths["records"] / f"{ts}_{case_name}.record.json"
            write_json(
                record_path,
                {
                    "run_id": run_id(),
                    "run_stamp": ts,
                    "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "provider": provider,
                    "mode": "swiftapi" if via_swiftapi else "direct",
                    "model": model,
                    "case_name": case_name,
                    "prompt_identifier": prompt_identifier,
                    "prompt_hash": prompt_hash,
                    "system_prompt_identifier": "prompts/system.txt",
                    "system_prompt_hash": system_hash,
                    "regime": regime_name,
                    "max_tokens": case_max_tokens,
                    "temperature": None,
                    "response_status": "executed",
                    "result_classification": classification,
                    "output_hash": sha256_text(text),
                    "output_text": text,
                    "provider_response_id": payload.get("id"),
                    "payload_file": payload_path.relative_to(paths["raw"].parent).as_posix(),
                    "text_file": text_path.relative_to(paths["raw"].parent).as_posix(),
                    "attestation_file": attestation_rel,
                    "verification_id": attestation.get("verification_id") if attestation else None,
                    "attestation_id": (
                        attestation.get("execution_attestation", {}).get("jti")
                        if attestation
                        else None
                    ),
                    "git_commit": GIT_COMMIT,
                    "command": COMMAND,
                },
            )

            print(f"\n=== {case_name} ===\n{text}\n")

    manifest_path = paths["raw"].parent / "case_summary.json"
    write_json(
        manifest_path,
        {
            "provider": provider,
            "mode": "swiftapi" if via_swiftapi else "direct",
            "run_id": run_id(),
            "run_stamp": ts,
            "case_count": case_count,
            "attestation_count": attestation_count,
            "classifications": counts,
            "model": model,
            "git_commit": GIT_COMMIT,
            "command": COMMAND,
        },
    )
