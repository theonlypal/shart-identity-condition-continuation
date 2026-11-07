"""Standard-library, offline companion verification. Makes no model requests."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def read(name):
    return json.loads((ROOT / name).read_bytes())
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

for entry in read('source-manifest.json'):
    assert digest(ROOT / entry['path']) == entry['sha256'], entry['path']

prompts = read('prompt-manifest.json')
for name, entry in prompts.items():
    if isinstance(entry, dict) and 'text' in entry:
        text = entry['text']
        assert text.encode().hex() == entry['utf8_hex'], name
        assert hashlib.sha256(text.encode()).hexdigest() == entry['sha256'], name
        assert [f'U+{ord(c):04X}' for c in text] == entry['code_points'], name
for name, entry in read('unicode-manifest.json').items():
    text = entry['text']
    assert text.encode().hex() == entry['utf8_hex'], name
    assert hashlib.sha256(text.encode()).hexdigest() == entry['sha256'], name
    assert [f'U+{ord(c):04X}' for c in text] == entry['code_points'], name

march = ROOT/'sources/getswiftapi-void-eval'
if march.exists():
    for regime, budget, byte_count, finish in [('constrained',100,0,'length'),('unconstrained',512,763,'stop')]:
        stem = '20260317T195933Z_artifact_openai_' + regime
        record = json.loads((march/f'artifacts/openai-direct/records/{stem}.record.json').read_bytes())
        raw = json.loads((march/f'artifacts/openai-direct/raw/{stem}.json').read_bytes())
        content = raw['choices'][0]['message']['content']
        assert raw['model'] == 'gpt-5.2-2025-12-11'
        assert raw['choices'][0]['finish_reason'] == finish
        assert record['max_tokens'] == budget
        assert len(content.encode()) == byte_count
        assert hashlib.sha256(content.encode()).hexdigest() == record['output_hash']
        assert (march/f'artifacts/openai-direct/raw/{stem}.txt').read_bytes() == content.encode()
        for name, field in [('artifact','prompt_hash'),('system','system_prompt_hash')]:
            value = (march/f'prompts/{name}.txt').read_text().strip()
            assert hashlib.sha256(value.encode()).hexdigest() == record[field]
    print('VERIFIED: March 17 direct receipts, prompt hashes, token ceilings, and raw output bytes')

fresh=ROOT/'sources/void-discovery-replay/runs/confirmatory'
if fresh.exists():
    summary=json.loads((fresh/'summary.json').read_text())
    assert summary['present_empty_strings']==0 and summary['visible']==5
    assert summary['attempts']==5 and summary['retries']==0
    for row in summary['rows']:
        stem=f"attempt-{row['attempt']:02d}"
        raw=json.loads((fresh/f'raw/{stem}.response.json').read_text())
        meta=json.loads((fresh/f'raw/{stem}.metadata.json').read_text())
        assert digest(fresh/f'raw/{stem}.response.json')==meta['response_sha256']
        assert digest(fresh/f'raw/{stem}.request.json')==meta['request_sha256']
        assert raw['choices'][0]['message']['content']==row['content']
        assert len(row['content'].encode())==row['utf8_bytes']
    print('VERIFIED: separately published fresh five-request discovery replay')

release = ROOT / 'release-receipt.json'
if release.exists():
    for name, expected in read('release-receipt.json')['sha256'].items():
        assert digest(ROOT / name) == expected, name
print('VERIFIED: source hashes, prompt bytes, Unicode, and five contemporary replay records')
