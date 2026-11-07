"""Portable file utilities and the exact question-only content prompt."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'evidence'
EOS = 151645


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def status(stage, **details):
    print(json.dumps({'stage': stage, **details}), flush=True)


def prompt(system, question):
    return '<|im_start|>system\n' + system + '<|im_end|>\n<|im_start|>user\n' + question + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
