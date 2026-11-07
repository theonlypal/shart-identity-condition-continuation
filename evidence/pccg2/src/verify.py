"""Verify package bytes and independently recompute the recorded contracts."""
import hashlib
import json
import re
import runpy
import sys
from pathlib import Path
import numpy as np

sys.dont_write_bytecode = True
if not __debug__:
    raise RuntimeError('Run without Python optimization flags')
ROOT = Path(__file__).resolve().parents[1]
read = lambda p: json.loads(p.read_text())


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    names = set()
    for line in (ROOT / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        assert re.fullmatch('[a-f0-9]{64}', expected)
        assert name not in names
        names.add(name)
        p = (ROOT / name).resolve()
        assert p.is_relative_to(ROOT) and sha(p) == expected, name
    assert {'config.json', 'gate/permission.safetensors', 'src/model.py',
            'evidence/witness-2plus2.json', 'evidence/audit.json'} <= names
    for name, record in read(ROOT / 'evidence/release-map.json').items():
        assert sha(ROOT / name) == record['sha256'], name
    runpy.run_path(str(ROOT / 'src/audit.py'), run_name='__main__')
    rows = read(ROOT / 'evidence/witness-2plus2.json')
    assert len(rows) == 5
    expected_ids = [[19, 151645], [151645], [151645], [19, 151645], [151645]]
    eos_scores = [-124.0, 94.5, 136.0, -82.0, 94.5]
    signs = [1.0, 1.0, -1.0, -1.0, 1.0]
    conditions = ['EQ(485487,485487)', 'EQ(485487,485489)']
    expected_hash = '5f42fcb08c73af4914a711b524ae7130d671ec9504ecdfa699e8f478094713ec'
    assert (ROOT / 'evidence/witness-non-eos-vector.sha256').read_text().strip() == expected_hash
    vectors, nonvectors = [], []
    for i, r in enumerate(rows):
        assert r['id'] == i + 1 and r['permission_sign'] == signs[i]
        assert r['condition'] == conditions[0 if i in [0, 2] else 1]
        assert r['question'] == 'What is 2 + 2?'
        assert r['system'] == read(ROOT / 'config.json')['system']
        assert r['generated_ids'] == r['expected_ids'] == expected_ids[i]
        assert r['text'] == ('4' if expected_ids[i][0] == 19 else '')
        assert r['decoded_with_special_tokens'] == r['text'] + '<|im_end|>'
        full = (ROOT / r['first_logits_file']).read_bytes()
        non = (ROOT / r['nonEOS_logits_file']).read_bytes()
        assert len(full) == 151936 * 2 and len(non) == 151935 * 2
        assert full[:151645*2] + full[151646*2:] == non
        assert hashlib.sha256(full).hexdigest() == r['first_logits_sha256']
        assert hashlib.sha256(non).hexdigest() == r['nonEOS_logits_sha256'] == expected_hash
        assert r['first_nonEOS_bf16_sha256'] == expected_hash
        bits = np.frombuffer(full, dtype='<u2')
        values = (bits.astype(np.uint32) << 16).view(np.float32)
        assert np.isfinite(values).all()
        assert float(values[19]) == r['answer_logit'] == 53.0
        assert float(values[151645]) == r['native_EOS_logit'] == eos_scores[i]
        assert int(values.argmax()) == expected_ids[i][0]
        step = r['raw_steps'][0]
        assert step['argmax'] == int(values.argmax())
        assert step['top5_logits'] == [float(values[j]) for j in step['top5_ids']]
        assert sorted(step['top5_logits']) == sorted(np.partition(values, -5)[-5:].tolist())
        assert r['gate_sha256'] == sha(ROOT / 'gate/permission.safetensors') == '17f2c83502ab96b3ee43c51c5c221df528f73bd378c02598c2cfbfdacd61cc26'
        assert r['intervention_sha256'] == sha(ROOT / 'evidence/records/causal-freeze.json')
        assert r['content_weight_sha256'] == read(ROOT / 'evidence/audit.json')['content_RAM_sha256']
        assert r['content_files_manifest_sha256'] == sha(ROOT / 'evidence/base-identity.json')
        assert r['exact'] and r['all_nonEOS_unchanged']
        vectors.append(full); nonvectors.append(non)
    assert all(v == nonvectors[0] for v in nonvectors)
    assert vectors[1] == vectors[4] and rows[1]['raw_steps'] == rows[4]['raw_steps']
    assert rows[0]['raw_steps'][1:] == rows[3]['raw_steps'][1:]
    assert rows[0]['raw_steps'][1]['argmax'] == 151645
    print(f'PASS: {len(names)} hashes; frozen base and gate; recorded behavioral and causal results; 5/5 witness arms')


if __name__ == '__main__':
    main()
